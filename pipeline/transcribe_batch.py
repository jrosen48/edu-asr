#!/usr/bin/env python3
"""
Option-2 pipeline: rclone Download -> Transcribe -> Delete, with:
- resume via .done sidecars
- disk guard (--min-free-gb) with optional waiting
- run log CSV (--run-log)
"""
import argparse, json, os, sys, subprocess, tempfile, uuid, shutil, time, warnings, csv, datetime
from pathlib import Path
import yaml
import webvtt, pysrt

# Deferred import so argument errors are fast
import whisperx

def run(cmd, check=True):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr}")
    return p

def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def ensure_wav(input_path, sr=16000):
    out = Path(tempfile.gettempdir()) / f"asr_{uuid.uuid4().hex}.wav"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_path), "-ac", "1", "-ar", str(sr), str(out)]
    run(cmd)
    return str(out)

def format_timestamp(seconds: float):
    h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"

def segments_to_srt(segments, out_srt):
    subs = pysrt.SubRipFile()
    for i, seg in enumerate(segments, 1):
        start = seg["start"]; end = seg["end"]
        text = seg.get("text","").strip()
        spk = seg.get("speaker", None)
        if spk: text = f"[{spk}] {text}"
        item = pysrt.SubRipItem(
            index=i,
            start=pysrt.SubRipTime.from_ordinal(int(start*1000)),
            end=pysrt.SubRipTime.from_ordinal(int(end*1000)),
            text=text
        )
        subs.append(item)
    subs.save(out_srt, encoding="utf-8")

def segments_to_vtt(segments, out_vtt):
    vtt = webvtt.WebVTT()
    for seg in segments:
        start = format_timestamp(seg["start"]).replace('.', ',')
        end = format_timestamp(seg["end"]).replace('.', ',')
        text = seg.get("text","").strip()
        spk = seg.get("speaker", None)
        if spk: text = f"[{spk}] {text}"
        vtt.captions.append(webvtt.Caption(start, end, text))
    vtt.save(out_vtt)

def write_txt(segments, out_txt):
    with open(out_txt, "w", encoding="utf-8") as f:
        last_spk = None
        for seg in segments:
            spk = seg.get("speaker", "UNK")
            if spk != last_spk:
                f.write(f"\n{spk}:\n")
                last_spk = spk
            f.write(seg.get("text","").strip()+" ")
        f.write("\n")

def has_all_outputs(stem, out_dir):
    exts = [".json",".srt",".vtt",".txt",".done"]
    return all((Path(out_dir)/f"{stem}{e}").exists() for e in exts)

def mark_done(stem, out_dir):
    Path(out_dir, f"{stem}.done").write_text("")

def disk_free_gb(path):
    usage = shutil.disk_usage(path)
    return usage.free / (1024**3)

def ffprobe_duration_seconds(media_path):
    try:
        p = run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","format=duration","-of","default=nw=1:nk=1", str(media_path)], check=False)
        if p.returncode==0:
            return float(p.stdout.strip())
    except Exception:
        pass
    return None

def log_row(run_log, header, rowdict):
    new = not Path(run_log).exists()
    with open(run_log, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if new: w.writeheader()
        w.writerow(rowdict)

def transcribe_one(local_media, cfg, out_dir):
    device = cfg.get("device","cpu")
    compute_type = cfg.get("compute_type","int8")
    model_size = cfg.get("model_size","medium.en")
    language = cfg.get("language","en")
    vad = cfg.get("vad", True)
    diarization = cfg.get("diarization", True)
    diar_backend = cfg.get("diarization_backend","pyannote")
    min_spk = cfg.get("min_speaker_count", None)
    max_spk = cfg.get("max_speaker_count", None)
    seg_max = cfg.get("segment_max_duration_s", 300)
    hf_token_env = cfg.get("hf_token_env","HF_TOKEN")

    asr_model = whisperx.load_model(model_size, device, compute_type=compute_type, language=language if language else None)

    align_model, metadata = None, None
    try:
        align_model, metadata = whisperx.load_align_model(language_code=language if language else "en", device=device)
    except Exception as e:
        warnings.warn(f"Alignment model load failed (continuing without): {e}")

    stem = Path(local_media).stem
    out_json = Path(out_dir)/f"{stem}.json"
    out_srt  = Path(out_dir)/f"{stem}.srt"
    out_vtt  = Path(out_dir)/f"{stem}.vtt"
    out_txt  = Path(out_dir)/f"{stem}.txt"

    wav = ensure_wav(local_media)
    try:
        audio = whisperx.load_audio(wav)
        result = asr_model.transcribe(audio, vad=vad, chunk_size=seg_max)
        if align_model is not None:
            try:
                result = whisperx.align(result["segments"], align_model, metadata, audio, device=device, return_char_alignments=False)
            except Exception as e:
                warnings.warn(f"Alignment failed (continuing): {e}")

        if diarization:
            diar_segments = None
            if diar_backend == "pyannote":
                from whisperx.diarize import DiarizationPipeline
                hf_token = os.environ.get(hf_token_env)
                if not hf_token:
                    raise RuntimeError(f"Missing Hugging Face token in env var {hf_token_env}.")
                pipeline = DiarizationPipeline(use_auth_token=hf_token, device=device)
                diarize_segments = pipeline(wav)
                diar_segments = [{"start": float(turn.start), "end": float(turn.end), "speaker": str(spk)}
                                 for (turn, _, spk) in diarize_segments.itertracks(yield_label=True)]
            else:
                import librosa
                from sklearn.cluster import AgglomerativeClustering
                from sklearn.preprocessing import normalize
                from whisperx.embedding import AudioEncoder
                y, sr = librosa.load(wav, sr=16000, mono=True)
                win = int(1.5*sr); hop = int(0.75*sr)
                frames, times = [], []
                for i in range(0, len(y)-win, hop):
                    frames.append(y[i:i+win]); times.append((i/sr, (i+win)/sr))
                enc = AudioEncoder(device="cpu")
                embs = normalize(enc.embed(frames))
                n_clusters = min_spk or 2
                if max_spk and max_spk > n_clusters: n_clusters = max_spk
                labels = AgglomerativeClustering(n_clusters=n_clusters).fit_predict(embs)
                diar_segments = []
                cur_spk=None; cur_start=None
                for (st,en), lab in zip(times, labels):
                    spk=f"SPEAKER_{lab}"
                    if cur_spk is None:
                        cur_spk,cur_start=spk,st
                    elif spk!=cur_spk:
                        diar_segments.append({"start":float(cur_start),"end":float(st),"speaker":cur_spk})
                        cur_spk,cur_start=spk,st
                if cur_spk is not None:
                    diar_segments.append({"start":float(cur_start),"end":float(times[-1][1]),"speaker":cur_spk})

            if diar_segments:
                result = whisperx.assign_word_speakers(diar_segments, result)

        segments = [{
            "id": seg.get("id"),
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg.get("text","").strip(),
            "speaker": seg.get("speaker", None)
        } for seg in result["segments"]]

        with open(out_json, "w", encoding="utf-8") as f:
            json.dump({"file": str(local_media), "segments": segments}, f, ensure_ascii=False, indent=2)
        segments_to_srt(segments, str(out_srt))
        segments_to_vtt(segments, str(out_vtt))
        write_txt(segments, str(out_txt))
        return True, len(segments)
    finally:
        try: os.remove(wav)
        except Exception: pass

def list_remote_files(remote, path):
    proc = run(["rclone", "lsjson", f"{remote}:{path}", "--files-only", "--recursive"], check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"rclone lsjson failed:\n{proc.stderr}")
    items = json.loads(proc.stdout)
    out = []
    for it in items:
        if not it.get("IsDir", False):
            out.append({
                "Path": it.get("Path") or it.get("Name"),
                "Name": it.get("Name") or Path(it.get("Path","")).name,
                "Size": it.get("Size", 0),
                "ModTime": it.get("ModTime", "")
            })
    out.sort(key=lambda d: (d["ModTime"], d["Name"]))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rclone-remote", help="rclone remote name (e.g., mysharepoint)")
    ap.add_argument("--remote-path", help="path inside remote (e.g., sites/<Site>/Shared Documents/Folder)")
    ap.add_argument("--input_dir", help="local folder of media files (alternative to rclone mode)")
    ap.add_argument("--scratch-dir", default="/tmp/asr_scratch")
    ap.add_argument("--include-ext", default=".mov,.mp4,.m4a,.wav")
    ap.add_argument("--max-files", type=int, default=0, help="limit files this run (0 = no limit)")
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--min-free-gb", type=float, default=5.0, help="pause if scratch free space below this")
    ap.add_argument("--wait-if-low-disk", action="store_true", help="wait for space to free instead of exiting")
    ap.add_argument("--check-interval-s", type=int, default=30, help="when waiting, check disk free every N seconds")
    ap.add_argument("--max-wait-min", type=int, default=120, help="max minutes to wait for disk space")
    ap.add_argument("--run-log", help="CSV path for run log; defaults to <output_dir>/run_log.csv")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(args.scratch_dir); scratch.mkdir(parents=True, exist_ok=True)
    run_log = args.run_log or str(out_dir / "run_log.csv")
    allowed = set([e.strip().lower() if e.strip().startswith(".") else "."+e.strip().lower()
                   for e in args.include_ext.split(",") if e.strip()])

    header = ["timestamp","filename","remote_path","size_bytes","duration_s","success","wall_time_s",
              "segments","model","device","compute","diar_backend","error"]

    processed = 0

    # Remote or local mode
    if args.rclone-remote or args.remote-path:
        if not (args.rclone-remote and args.remote-path):
            print("Error: both --rclone-remote and --remote-path are required for rclone mode.", file=sys.stderr)
            sys.exit(2)

    if args.rclone-remote and args.remote-path:
        remote = args.rclone-remote
        rpath = args.remote-path
        print(f"[remote] Listing: {remote}:{rpath}")
        items = list_remote_files(remote, rpath)
        print(f"[remote] {len(items)} total entries")

        for it in items:
            rel = it["Path"]; name = it["Name"]; size = it.get("Size",0)
            ext = Path(name).suffix.lower()
            if ext not in allowed: continue
            stem = Path(name).stem
            if has_all_outputs(stem, out_dir):
                print(f"[skip-done] {name}")
                continue

            # Disk guard loop
            waited_s = 0
            while True:
                free = disk_free_gb(scratch)
                need = (size/(1024**3)) + 2.0  # file size + 2 GB buffer for temp WAV
                if free >= max(args.min-free-gb, need):
                    break
                msg = f"[disk-guard] Free={free:.2f} GiB, Need≈{max(args.min-free-gb, need):.2f} GiB. "
                if args.wait_if_low_disk:
                    print(msg + f"Waiting {args.check_interval_s}s...")
                    time.sleep(args.check_interval_s)
                    waited_s += args.check_interval_s
                    if waited_s > args.max_wait_min*60:
                        print("[disk-guard] Timed out waiting for space.")
                        sys.exit(3)
                else:
                    print(msg + "Exiting (use --wait-if-low-disk to pause instead).")
                    sys.exit(3)

            local_target = scratch / name
            local_target.parent.mkdir(parents=True, exist_ok=True)
            src = f"{remote}:{rpath}/{rel}"

            print(f"[copy] {name} ({size} bytes) -> {local_target}")
            t0 = time.time()
            cp = run(["rclone", "copyto", src, str(local_target),
                      "--transfers", "1", "--checkers", "1",
                      "--retries", "3", "--low-level-retries", "10"], check=False)
            if cp.returncode != 0:
                print(f"[warn] copy failed, skipping: {name}\n{cp.stderr}")
                log_row(run_log, header, {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "filename": name, "remote_path": rel, "size_bytes": size,
                    "duration_s": "", "success": False, "wall_time_s": time.time()-t0,
                    "segments": "", "model": cfg.get("model_size"), "device": cfg.get("device"),
                    "compute": cfg.get("compute_type"), "diar_backend": cfg.get("diarization_backend"),
                    "error": f"copy_failed: {cp.stderr[:200]}"
                })
                continue

            # Transcribe
            ok = False; seg_count = ""
            try:
                dur = ffprobe_duration_seconds(local_target)
                t1 = time.time()
                ok, seg_count = transcribe_one(str(local_target), cfg, out_dir)
                wall = time.time()-t1
                log_row(run_log, header, {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "filename": name, "remote_path": rel, "size_bytes": size,
                    "duration_s": f"{dur:.3f}" if dur else "",
                    "success": True, "wall_time_s": f"{wall:.1f}",
                    "segments": seg_count, "model": cfg.get("model_size"), "device": cfg.get("device"),
                    "compute": cfg.get("compute_type"), "diar_backend": cfg.get("diarization_backend"),
                    "error": ""
                })
            except Exception as e:
                wall = time.time()-t1 if 't1' in locals() else time.time()-t0
                log_row(run_log, header, {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "filename": name, "remote_path": rel, "size_bytes": size,
                    "duration_s": "", "success": False, "wall_time_s": f"{wall:.1f}",
                    "segments": "", "model": cfg.get("model_size"), "device": cfg.get("device"),
                    "compute": cfg.get("compute_type"), "diar_backend": cfg.get("diarization_backend"),
                    "error": str(e)[:200]
                })
                print(f"[error] transcription failed for {name}: {e}")
            finally:
                try: os.remove(local_target)
                except Exception: pass

            if ok:
                mark_done(stem, out_dir)
                processed += 1
                print(f"[done] {name}")
            else:
                print(f"[failed] {name}")

            if args.max_files and processed >= args.max_files:
                print(f"[limit] Reached --max-files={args.max_files}. Stopping.")
                break
    else:
        # Local folder mode
        if not args.input_dir:
            print("Error: provide --input_dir for local mode, or --rclone-remote and --remote-path for rclone mode.", file=sys.stderr)
            sys.exit(2)
        files = [p for p in Path(args.input_dir).glob('**/*') if p.suffix.lower() in allowed]
        files.sort()
        for fp in files:
            stem = fp.stem
            if has_all_outputs(stem, out_dir):
                print(f"[skip-done] {fp.name}")
                continue
            try:
                t1=time.time()
                ok, seg_count = transcribe_one(str(fp), cfg, out_dir)
                wall = time.time()-t1
                log_row(run_log, header, {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "filename": fp.name, "remote_path": str(fp), "size_bytes": fp.stat().st_size,
                    "duration_s": "", "success": ok, "wall_time_s": f"{wall:.1f}",
                    "segments": seg_count if ok else "", "model": cfg.get("model_size"), "device": cfg.get("device"),
                    "compute": cfg.get("compute_type"), "diar_backend": cfg.get("diarization_backend"),
                    "error": "" if ok else "transcription_failed"
                })
            except Exception as e:
                print(f"[error] transcription failed for {fp.name}: {e}")
            if ok:
                mark_done(stem, out_dir)
                processed += 1
                print(f"[done] {fp.name}")
            if args.max_files and processed >= args.max_files:
                print(f"[limit] Reached --max-files={args.max_files}. Stopping.")
                break

    print(f"[summary] processed={processed}")

if __name__ == "__main__":
    main()
