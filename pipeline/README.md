# EDU ASR Pipeline (Option 2) — Download → Transcribe → Delete

This pipeline processes classroom videos from **SharePoint/OneDrive** (or a local folder) with a **bounded disk footprint**:

1) Copy **one file at a time** to a scratch directory (via `rclone copyto`)  
2) Transcribe + diarize with **WhisperX**  
3) Write JSON/SRT/VTT/TXT, mark a `.done` sidecar, **delete** the local movie  
4) Move on to the next file

It includes:
- **Disk guard** `--min-free-gb` (pauses if free space is low)
- **Run log** `--run-log` CSV (file metadata + timings + success/failure)
- **Resume** (skips files that already have `.done` in `output_dir`)
- **Batch control** `--max-files`

## Prereqs
- macOS with Python 3.11 (Conda recommended)
- `ffmpeg` (Homebrew: `brew install ffmpeg`)
- `rclone` (Homebrew: `brew install rclone`) and a configured OneDrive/SharePoint remote (`rclone config`)
- Hugging Face token (if using pyannote diarization):
  - Request access to `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`
  - `export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx`

## Install
```bash
conda create -n edu-asr python=3.11 -y
conda activate edu-asr
pip install -r requirements.txt
```

## Run (SharePoint/OneDrive)
```bash
python transcribe_batch.py   --rclone-remote "mysharepoint"   --remote-path "sites/<SiteName>/Shared Documents/PD Weekend"   --scratch-dir "/Volumes/SCRATCH/asr"   --output_dir "/path/to/out"   --config config.yaml   --min-free-gb 10   --max-files 5   --run-log "/path/to/out/run_log.csv"
```

## Run (Local folder)
```bash
python transcribe_batch.py   --input_dir "/path/to/mov_folder"   --output_dir "/path/to/out"   --config config.yaml
```

## Outputs
- `{basename}.json` — segments with timestamps + speaker labels
- `{basename}.srt` — subtitles with `[SPEAKER_X]` prefixes
- `{basename}.vtt`
- `{basename}.txt` — readable transcript with speaker turns
- `{basename}.done` — empty sidecar marking successful completion

## Stats
After you have transcripts, run:
```bash
python stats_transcripts.py   --transcripts-dir "/path/to/out"   --run-log "/path/to/out/run_log.csv"   --out-dir "/path/to/out"
```
This writes `stats_summary.csv`, `per_file_stats.csv`, and `per_speaker_stats.csv`.
