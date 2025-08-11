#!/usr/bin/env python3
"""
Compute simple descriptive stats from transcript JSONs and optional run_log.csv.
Writes: stats_summary.csv, per_file_stats.csv, per_speaker_stats.csv
"""
import argparse, json, pandas as pd
from pathlib import Path

def load_transcripts(dir_path):
    rows = []
    for jf in sorted(Path(dir_path).glob("*.json")):
        data = json.loads(jf.read_text())
        file_path = data.get("file", jf.stem)
        segs = data.get("segments", [])
        for s in segs:
            rows.append({
                "file": file_path,
                "speaker": s.get("speaker"),
                "start_s": float(s.get("start", 0.0)),
                "end_s": float(s.get("end", 0.0)),
                "text": s.get("text","").strip()
            })
    return pd.DataFrame(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts-dir", required=True)
    ap.add_argument("--run-log", help="Optional run_log.csv to augment durations")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    df = load_transcripts(args.transcripts_dir)
    if df.empty:
        print("No transcripts found.")
        return

    df["words"] = df["text"].str.split().map(len)
    # per-file duration from segments (max end_s)
    file_dur = df.groupby("file")["end_s"].max().rename("duration_s")
    per_file = df.groupby("file").agg(segments=("text","count"),
                                      words=("words","sum")).join(file_dur).reset_index()
    per_file["wpm_est"] = per_file.apply(lambda r: (r["words"]/ (r["duration_s"]/60.0)) if r["duration_s"]>0 else None, axis=1)

    # If run_log is present, join duration_s if available
    if args.run_log and Path(args.run_log).exists():
        rl = pd.read_csv(args.run_log)
        rl = rl[["filename","duration_s"]].copy()
        rl = rl.dropna()
        rl["duration_s"] = pd.to_numeric(rl["duration_s"], errors="coerce")
        # naive filename match (users often keep original names); if path mismatch, this may not align perfectly
        per_file = per_file.merge(rl, left_on=per_file["file"].map(lambda p: Path(p).name), right_on="filename", how="left", suffixes=("","_ffprobe"))
        per_file["duration_s_final"] = per_file["duration_s_ffprobe"].fillna(per_file["duration_s"])
        per_file.drop(columns=["key_0","filename","duration_s","duration_s_ffprobe"], inplace=True, errors="ignore")
        per_file.rename(columns={"duration_s_final":"duration_s"}, inplace=True)

    # per-speaker
    spk = df.dropna(subset=["speaker"]).copy()
    per_speaker = spk.groupby("speaker").agg(
        segments=("text","count"),
        words=("words","sum"),
        speaking_time_s=("end_s", "sum")  # approximate (overestimates if overlapping turns)
    ).reset_index()
    per_speaker["wpm_est"] = per_speaker.apply(lambda r: (r["words"]/ (r["speaking_time_s"]/60.0)) if r["speaking_time_s"]>0 else None, axis=1)

    # overall
    total_files = per_file.shape[0]
    total_segments = int(df.shape[0])
    total_words = int(df["words"].sum())
    total_duration_h = per_file["duration_s"].fillna(0).sum()/3600.0
    overall_wpm = (total_words/(per_file["duration_s"].sum()/60.0)) if per_file["duration_s"].sum() > 0 else None

    summary = pd.DataFrame([{
        "total_files": total_files,
        "total_segments": total_segments,
        "total_words": total_words,
        "total_duration_hours": round(total_duration_h, 3),
        "overall_wpm_est": round(overall_wpm, 1) if overall_wpm else ""
    }])

    # write
    summary.to_csv(out_dir/"stats_summary.csv", index=False)
    per_file.to_csv(out_dir/"per_file_stats.csv", index=False)
    per_speaker.to_csv(out_dir/"per_speaker_stats.csv", index=False)

    print("Wrote:", out_dir/"stats_summary.csv")
    print("Wrote:", out_dir/"per_file_stats.csv")
    print("Wrote:", out_dir/"per_speaker_stats.csv")

if __name__ == "__main__":
    main()
