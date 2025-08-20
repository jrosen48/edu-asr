#!/usr/bin/env python3
"""Batch transcription pipeline using WhisperX."""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        import yaml
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except ImportError:
        print("Warning: pyyaml not installed, using default config")
        return {}


def get_disk_free_gb(path: str) -> float:
    """Get free disk space in GB for the given path."""
    stat = shutil.disk_usage(path)
    return stat.free / (1024**3)


def wait_for_disk_space(scratch_dir: str, min_free_gb: float, check_interval_s: int = 30, max_wait_min: int = 60):
    """Wait until sufficient disk space is available."""
    max_wait_seconds = max_wait_min * 60
    waited_seconds = 0
    
    while waited_seconds < max_wait_seconds:
        free_gb = get_disk_free_gb(scratch_dir)
        if free_gb >= min_free_gb:
            return
        
        print(f"Insufficient disk space: {free_gb:.1f}GB available, {min_free_gb}GB required. Waiting...")
        time.sleep(check_interval_s)
        waited_seconds += check_interval_s
    
    raise RuntimeError(f"Insufficient disk space after waiting {max_wait_min} minutes")


def list_remote_files(rclone_remote: str, remote_path: str, include_ext: str) -> List[str]:
    """List files on remote that match the extension filter."""
    # Convert include_ext to rclone include filters (case-insensitive)
    extensions = [ext.strip().lower() for ext in include_ext.split(',')]
    include_filters = []
    for ext in extensions:
        if not ext.startswith('.'):
            ext = '.' + ext
        # Add both lowercase and uppercase variants for rclone
        include_filters.extend(['--include', f'*{ext}'])
        include_filters.extend(['--include', f'*{ext.upper()}'])
        # Also add common mixed case variants
        if len(ext) > 1:
            include_filters.extend(['--include', f'*{ext[0].upper() + ext[1:].lower()}'])
    
    cmd = ['rclone', 'lsf', f'{rclone_remote}:{remote_path}', '--recursive'] + include_filters
    
    print(f"Listing files from {rclone_remote}:{remote_path}")
    print(f"Extensions to match (case-insensitive): {', '.join(extensions)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Warning: rclone list failed: {result.stderr}")
        return []
    
    # Parse the file list
    files = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    return files


def sync_single_file(rclone_remote: str, remote_file_path: str, local_dir: str) -> Optional[str]:
    """Sync a single file from remote using rclone."""
    local_path = Path(local_dir)
    local_path.mkdir(parents=True, exist_ok=True)
    
    # Get just the filename from the remote path
    filename = Path(remote_file_path).name
    local_file_path = local_path / filename
    
    cmd = ['rclone', 'copyto', f'{rclone_remote}:{remote_file_path}', str(local_file_path)]
    
    print(f"Syncing {remote_file_path} to {local_file_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Warning: rclone failed to sync {remote_file_path}: {result.stderr}")
        return None
    
    return str(local_file_path)


def sync_from_remote(rclone_remote: str, remote_path: str, local_dir: str, include_ext: str) -> List[str]:
    """Sync files from remote using rclone (legacy bulk sync - now returns list of remote files)."""
    return list_remote_files(rclone_remote, remote_path, include_ext)


def find_local_files(input_dir: str, include_ext: str) -> List[str]:
    """Find local files matching the extension filter (case-insensitive)."""
    extensions = [ext.strip().lower() for ext in include_ext.split(',')]
    print(f"Extensions to match (case-insensitive): {', '.join(extensions)}")
    input_path = Path(input_dir)
    files = []
    
    # Get all files and filter by extension case-insensitively
    all_files = list(input_path.glob('**/*'))
    
    for file_path in all_files:
        if file_path.is_file():
            file_ext = file_path.suffix.lower()
            for ext in extensions:
                if not ext.startswith('.'):
                    ext = '.' + ext
                if file_ext == ext:
                    files.append(file_path)
                    break
    
    return [str(f) for f in files]


def is_already_processed(audio_file: str, output_dir: str) -> bool:
    """Check if file has already been processed."""
    audio_path = Path(audio_file)
    done_file = Path(output_dir) / f"{audio_path.stem}.done"
    return done_file.exists()


def is_already_processed_remote(remote_file_path: str, output_dir: str) -> bool:
    """Check if remote file has already been processed."""
    filename = Path(remote_file_path).name
    audio_path = Path(filename)
    done_file = Path(output_dir) / f"{audio_path.stem}.done"
    return done_file.exists()


def mark_as_processed(audio_file: str, output_dir: str):
    """Mark file as processed by creating a .done file."""
    audio_path = Path(audio_file)
    done_file = Path(output_dir) / f"{audio_path.stem}.done"
    done_file.touch()


def get_hf_token(config: Dict[str, Any]) -> Optional[str]:
    """Get Hugging Face token from environment or config."""
    # First try environment variable
    hf_token_env = config.get('hf_token_env', 'HF_TOKEN')
    token = os.environ.get(hf_token_env)
    if token:
        return token.strip()
    
    # Try loading from user profile
    try:
        hf_token_file = Path.home() / ".eduasr" / "hf_token"
        if hf_token_file.exists():
            token = hf_token_file.read_text().strip()
            if token:
                return token
    except Exception:
        pass
    
    # Try loading from local project file
    try:
        local_hf_file = Path("hf")
        if local_hf_file.exists():
            token = local_hf_file.read_text().strip()
            if token:
                return token
    except Exception:
        pass
    
    return None


def load_diarization_model(config: Dict[str, Any], device: str = "cpu"):
    """Load pyannote diarization model."""
    try:
        from pyannote.audio import Pipeline
        
        # Get HF token
        hf_token = get_hf_token(config)
        if not hf_token:
            raise ValueError("Hugging Face token required for diarization. Set HF_TOKEN environment variable or save token to ~/.eduasr/hf_token")
        
        print("Loading diarization model...")
        diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
        
        # Move to specified device
        if device != "cpu":
            try:
                diarization_pipeline = diarization_pipeline.to(device)
            except Exception as e:
                print(f"Warning: Could not move diarization model to {device}, using CPU: {e}")
                device = "cpu"
        
        return diarization_pipeline
        
    except ImportError as e:
        raise ImportError(f"pyannote.audio not available: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load diarization model: {e}")


def perform_diarization(audio_file: str, diarization_pipeline, config: Dict[str, Any]) -> Dict[str, Any]:
    """Perform speaker diarization on audio file."""
    try:
        print("Performing speaker diarization...")
        
        # Run diarization
        diarization = diarization_pipeline(audio_file)
        
        # Convert to list of speaker segments
        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                'start': turn.start,
                'end': turn.end,
                'speaker': speaker
            })
        
        # Sort by start time
        speaker_segments.sort(key=lambda x: x['start'])
        
        print(f"Found {len(set(seg['speaker'] for seg in speaker_segments))} speakers")
        
        return {
            'segments': speaker_segments,
            'speakers': list(set(seg['speaker'] for seg in speaker_segments))
        }
        
    except Exception as e:
        print(f"Warning: Diarization failed: {e}")
        return {'segments': [], 'speakers': []}


def assign_speakers_to_segments(transcription_segments: List[Dict], speaker_segments: List[Dict]) -> List[Dict]:
    """Assign speakers to transcription segments based on temporal overlap."""
    result_segments = []
    
    for trans_seg in transcription_segments:
        trans_start = trans_seg['start']
        trans_end = trans_seg['end']
        trans_mid = (trans_start + trans_end) / 2
        
        # Find the speaker segment that contains the midpoint of the transcription segment
        assigned_speaker = "SPEAKER_UNKNOWN"
        best_overlap = 0
        
        for speaker_seg in speaker_segments:
            speaker_start = speaker_seg['start']
            speaker_end = speaker_seg['end']
            
            # Calculate overlap
            overlap_start = max(trans_start, speaker_start)
            overlap_end = min(trans_end, speaker_end)
            overlap_duration = max(0, overlap_end - overlap_start)
            
            if overlap_duration > best_overlap:
                best_overlap = overlap_duration
                assigned_speaker = speaker_seg['speaker']
        
        # Create new segment with speaker information
        new_segment = trans_seg.copy()
        new_segment['speaker'] = assigned_speaker
        result_segments.append(new_segment)
    
    return result_segments


def transcribe_file(audio_file: str, output_dir: str, config: Dict[str, Any], model, model_a=None, metadata=None, diarization_pipeline=None) -> Dict[str, Any]:
    """Transcribe a single audio file."""
    import whisperx
    
    audio_path = Path(audio_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing: {audio_file}")
    
    # Load audio
    audio = whisperx.load_audio(audio_file)
    
    # Transcribe
    result = model.transcribe(audio, batch_size=config.get('batch_size', 8))
    
    # Align if model_a is available
    if model_a is not None:
        result = whisperx.align(result["segments"], model_a, metadata, audio, device="cpu", return_char_alignments=False)
    
    # Diarization if enabled
    if config.get('diarization', False) and config.get('diarization_backend') == 'pyannote' and diarization_pipeline is not None:
        try:
            diarization_result = perform_diarization(audio_file, diarization_pipeline, config)
            if diarization_result['segments']:
                # Assign speakers to transcription segments
                result["segments"] = assign_speakers_to_segments(result["segments"], diarization_result['segments'])
                result["speakers"] = diarization_result['speakers']
                print(f"Diarization complete: {len(diarization_result['speakers'])} speakers identified")
            else:
                print("Warning: Diarization found no speakers")
        except Exception as e:
            print(f"Warning: Diarization failed: {e}")
            # Continue without diarization
    elif config.get('diarization', False) and diarization_pipeline is None:
        print("Note: Diarization requested but model not loaded")
    
    # Write outputs
    base_name = audio_path.stem
    
    if config.get('write_json', True):
        json_file = output_path / f"{base_name}.json"
        with open(json_file, 'w') as f:
            json.dump(result, f, indent=2)
    
    if config.get('write_srt', True):
        srt_file = output_path / f"{base_name}.srt"
        write_srt(result, srt_file)
    
    if config.get('write_vtt', True):
        vtt_file = output_path / f"{base_name}.vtt"
        write_vtt(result, vtt_file)
    
    if config.get('write_txt', True):
        txt_file = output_path / f"{base_name}.txt"
        write_txt(result, txt_file)
    
    return {
        'file': audio_file,
        'duration': len(audio) / 16000,  # Approximate duration
        'segments': len(result.get('segments', [])),
        'status': 'success'
    }


def write_srt(result: Dict, output_file: Path):
    """Write SRT subtitle file."""
    with open(output_file, 'w') as f:
        for i, segment in enumerate(result.get('segments', []), 1):
            start = format_time(segment['start'])
            end = format_time(segment['end'])
            text = segment['text'].strip()
            
            # Add speaker label if available
            if 'speaker' in segment and segment['speaker']:
                speaker_label = segment['speaker']
                text = f"[{speaker_label}] {text}"
            
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def write_vtt(result: Dict, output_file: Path):
    """Write VTT subtitle file."""
    with open(output_file, 'w') as f:
        f.write("WEBVTT\n\n")
        for segment in result.get('segments', []):
            start = format_time_vtt(segment['start'])
            end = format_time_vtt(segment['end'])
            text = segment['text'].strip()
            
            # Add speaker label if available
            if 'speaker' in segment and segment['speaker']:
                speaker_label = segment['speaker']
                text = f"[{speaker_label}] {text}"
            
            f.write(f"{start} --> {end}\n{text}\n\n")


def write_txt(result: Dict, output_file: Path):
    """Write plain text file."""
    with open(output_file, 'w') as f:
        current_speaker = None
        for segment in result.get('segments', []):
            text = segment['text'].strip()
            
            # Add speaker label if it changes
            if 'speaker' in segment and segment['speaker']:
                if segment['speaker'] != current_speaker:
                    current_speaker = segment['speaker']
                    f.write(f"\n\n[{current_speaker}]\n")
            
            f.write(text + ' ')


def write_csv(result: Dict, output_file: Path):
    """Write CSV file with timestamps, speaker, and text columns."""
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow(['start_time', 'end_time', 'speaker', 'text'])
        
        # Write segments
        for segment in result.get('segments', []):
            start_time = segment.get('start', 0)
            end_time = segment.get('end', 0)
            speaker = segment.get('speaker')
            text = segment.get('text', '').strip()
            
            # Handle None values safely
            if start_time is None:
                start_time = 0
            if end_time is None:
                end_time = 0
            if speaker is None:
                speaker = 'N/A'
            
            writer.writerow([start_time, end_time, speaker, text])


def format_time(seconds: float) -> str:
    """Format time for SRT format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')


def format_time_vtt(seconds: float) -> str:
    """Format time for VTT format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def export_json_to_csv(json_file: Path, csv_file: Path = None):
    """Export a single JSON transcript file to CSV format."""
    import json
    
    if csv_file is None:
        csv_file = json_file.with_suffix('.csv')
    
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        write_csv(data, csv_file)
        print(f"✅ Exported {json_file.name} -> {csv_file.name}")
        return True
        
    except Exception as e:
        print(f"❌ Error exporting {json_file.name}: {e}")
        return False


def batch_export_csv(output_dir: str, force: bool = False):
    """Export all JSON transcript files in a directory to CSV format."""
    output_path = Path(output_dir)
    
    if not output_path.exists():
        print(f"❌ Output directory '{output_dir}' does not exist")
        return
    
    json_files = list(output_path.glob("*.json"))
    if not json_files:
        print(f"❌ No JSON transcript files found in '{output_dir}'")
        return
    
    print(f"🔄 Found {len(json_files)} JSON transcript files")
    
    exported_count = 0
    skipped_count = 0
    error_count = 0
    
    for json_file in json_files:
        csv_file = json_file.with_suffix('.csv')
        
        # Skip if CSV already exists and not forcing
        if csv_file.exists() and not force:
            print(f"⏭️  Skipping {json_file.name} (CSV already exists, use --force to overwrite)")
            skipped_count += 1
            continue
        
        if export_json_to_csv(json_file, csv_file):
            exported_count += 1
        else:
            error_count += 1
    
    print(f"\n📊 CSV Export Summary:")
    print(f"   ✅ Exported: {exported_count}")
    print(f"   ⏭️  Skipped: {skipped_count}")
    print(f"   ❌ Errors: {error_count}")
    
    if exported_count > 0:
        print(f"\n💡 CSV files are ready for Excel/Google Sheets with columns:")
        print(f"   • start_time: Segment start time in seconds")
        print(f"   • end_time: Segment end time in seconds") 
        print(f"   • speaker: Speaker ID (N/A if no diarization)")
        print(f"   • text: Transcript text")


def cleanup_file(file_path: str):
    """Remove a file after processing."""
    try:
        os.remove(file_path)
        print(f"Cleaned up: {file_path}")
    except OSError as e:
        print(f"Warning: Could not clean up {file_path}: {e}")


def log_run(run_log_path: str, stats: Dict[str, Any]):
    """Log run statistics to CSV file."""
    log_path = Path(run_log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    file_exists = log_path.exists()
    
    with open(log_path, 'a', newline='') as f:
        fieldnames = ['timestamp', 'files_processed', 'total_duration', 'success_count', 'error_count']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        writer.writerow(stats)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Batch transcribe audio files")
    parser.add_argument("--rclone_remote", help="Rclone remote name")
    parser.add_argument("--remote_path", help="Remote path to sync from")
    parser.add_argument("--input_dir", help="Local input directory")
    parser.add_argument("--scratch_dir", help="Scratch directory for temporary files")
    parser.add_argument("--include_ext", default=".mp3,.wav,.m4a,.mp4,.mov", help="File extensions to include")
    parser.add_argument("--max_files", type=int, help="Maximum number of files to process")
    parser.add_argument("--output_dir", required=True, help="Output directory for transcripts")
    parser.add_argument("--config", help="Config file path")
    parser.add_argument("--model", help="Whisper model to use (overrides config)")
    parser.add_argument("--force", action="store_true", help="Force reprocessing of existing files")
    parser.add_argument("--min_free_gb", type=float, default=5.0, help="Minimum free disk space in GB")
    parser.add_argument("--wait_if_low_disk", action="store_true", help="Wait if disk space is low")
    parser.add_argument("--check_interval_s", type=int, default=30, help="Disk check interval in seconds")
    parser.add_argument("--max_wait_min", type=int, default=60, help="Maximum wait time in minutes")
    parser.add_argument("--run_log", help="Run log file path")
    
    args = parser.parse_args()
    
    # Load config
    config = {}
    if args.config and Path(args.config).exists():
        config = load_config(args.config)
    
    # Override config with command line args
    if args.model:
        config['model_size'] = args.model
    
    # Set defaults
    model_size = config.get('model_size', 'base.en')
    device = config.get('device', 'cpu')
    compute_type = config.get('compute_type', 'int8')
    
    # Check disk space if required
    scratch_dir = args.scratch_dir or args.output_dir
    if args.wait_if_low_disk and get_disk_free_gb(scratch_dir) < args.min_free_gb:
        wait_for_disk_space(scratch_dir, args.min_free_gb, args.check_interval_s, args.max_wait_min)
    
    # Get list of files to process
    files_to_process = []
    remote_files = []
    is_remote_processing = False
    
    if args.rclone_remote and args.remote_path:
        # List remote files
        if not args.scratch_dir:
            raise ValueError("--scratch-dir is required when using rclone")
        is_remote_processing = True
        all_remote_files = list_remote_files(args.rclone_remote, args.remote_path, args.include_ext)
        
        print(f"\n📋 Found {len(all_remote_files)} matching files on remote:")
        for i, f in enumerate(all_remote_files, 1):
            print(f"  {i:3d}. {f}")
        
        # Filter already processed files by checking output directory
        if not args.force:
            already_processed = [f for f in all_remote_files if is_already_processed_remote(f, args.output_dir)]
            remote_files = [f for f in all_remote_files if not is_already_processed_remote(f, args.output_dir)]
            
            if already_processed:
                print(f"\n✅ Skipping {len(already_processed)} already processed files:")
                for i, f in enumerate(already_processed, 1):
                    print(f"  {i:3d}. {f} (found {Path(args.output_dir) / f'{Path(f).stem}.done'})")
        else:
            remote_files = all_remote_files
            print(f"\n🔄 Force mode: will re-process all files")
        
        # For remote files, we process the list directly
        files_to_process = remote_files
    elif args.input_dir:
        # Use local files
        all_local_files = find_local_files(args.input_dir, args.include_ext)
        
        print(f"\n📋 Found {len(all_local_files)} matching files in {args.input_dir}:")
        for i, f in enumerate(all_local_files, 1):
            print(f"  {i:3d}. {f}")
        
        # Filter already processed files
        if not args.force:
            already_processed = [f for f in all_local_files if is_already_processed(f, args.output_dir)]
            files_to_process = [f for f in all_local_files if not is_already_processed(f, args.output_dir)]
            
            if already_processed:
                print(f"\n✅ Skipping {len(already_processed)} already processed files:")
                for i, f in enumerate(already_processed, 1):
                    print(f"  {i:3d}. {Path(f).name}")
        else:
            files_to_process = all_local_files
            print(f"\n🔄 Force mode: will re-process all files")
            
    elif args.scratch_dir:
        # Use files in scratch directory
        all_scratch_files = find_local_files(args.scratch_dir, args.include_ext)
        
        print(f"\n📋 Found {len(all_scratch_files)} matching files in {args.scratch_dir}:")
        for i, f in enumerate(all_scratch_files, 1):
            print(f"  {i:3d}. {f}")
        
        # Filter already processed files
        if not args.force:
            already_processed = [f for f in all_scratch_files if is_already_processed(f, args.output_dir)]
            files_to_process = [f for f in all_scratch_files if not is_already_processed(f, args.output_dir)]
            
            if already_processed:
                print(f"\n✅ Skipping {len(already_processed)} already processed files:")
                for i, f in enumerate(already_processed, 1):
                    print(f"  {i:3d}. {Path(f).name}")
        else:
            files_to_process = all_scratch_files
            print(f"\n🔄 Force mode: will re-process all files")
    else:
        raise ValueError("Must specify either --rclone-remote/--remote-path, --input_dir, or --scratch-dir")
    
    # Limit number of files
    original_count = len(files_to_process)
    if args.max_files and len(files_to_process) > args.max_files:
        files_to_process = files_to_process[:args.max_files]
        print(f"\n⚠️  Limited to first {args.max_files} files (from {original_count} total)")
    
    if not files_to_process:
        print("\n❌ No files to process")
        return 0
    
    print(f"\n🎯 Will transcribe {len(files_to_process)} files:")
    for i, f in enumerate(files_to_process, 1):
        if is_remote_processing:
            print(f"  {i:3d}. {f} (will download first)")
        else:
            print(f"  {i:3d}. {Path(f).name}")
    
    print(f"\n🚀 Starting transcription...")
    
    # Load models
    try:
        import whisperx
        import torch
        from tqdm import tqdm
    except ImportError as e:
        print(f"Error: Required packages not installed: {e}")
        print("Please install with: pip install -r requirements.txt")
        return 1
    
    print("Loading Whisper model...")
    model = whisperx.load_model(model_size, device, compute_type=compute_type)
    
    # Load alignment model if needed
    model_a = None
    metadata = None
    if config.get('language'):
        try:
            model_a, metadata = whisperx.load_align_model(language_code=config['language'], device=device)
        except Exception as e:
            print(f"Warning: Could not load alignment model: {e}")
    
    # Load diarization model if needed
    diarization_pipeline = None
    if config.get('diarization', False) and config.get('diarization_backend') == 'pyannote':
        try:
            diarization_pipeline = load_diarization_model(config, device)
        except Exception as e:
            print(f"Warning: Could not load diarization model: {e}")
            print("Continuing without diarization...")
    
    # Process files
    stats = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'files_processed': 0,
        'total_duration': 0,
        'success_count': 0,
        'error_count': 0
    }
    
    for file_ref in tqdm(files_to_process, desc="Transcribing"):
        local_file_path = None
        try:
            # Check disk space before processing each file
            if args.wait_if_low_disk and get_disk_free_gb(scratch_dir) < args.min_free_gb:
                wait_for_disk_space(scratch_dir, args.min_free_gb, args.check_interval_s, args.max_wait_min)
            
            if is_remote_processing:
                # file_ref is a remote path, sync it first
                print(f"Syncing {file_ref}...")
                local_file_path = sync_single_file(args.rclone_remote, 
                                                 f"{args.remote_path}/{file_ref}", 
                                                 args.scratch_dir)
                if not local_file_path:
                    print(f"Failed to sync {file_ref}, skipping...")
                    stats['error_count'] += 1
                    continue
                
                # Use the local file path for processing
                process_file_path = local_file_path
            else:
                # file_ref is already a local path
                process_file_path = file_ref
                local_file_path = file_ref
            
            result = transcribe_file(process_file_path, args.output_dir, config, model, model_a, metadata, diarization_pipeline)
            
            stats['files_processed'] += 1
            stats['total_duration'] += result['duration']
            stats['success_count'] += 1
            
            # Mark as processed (use original reference for consistent naming)
            if is_remote_processing:
                # For remote files, create done file based on original remote filename
                filename = Path(file_ref).name
                audio_path = Path(filename)
                done_file = Path(args.output_dir) / f"{audio_path.stem}.done"
                done_file.touch()
            else:
                mark_as_processed(process_file_path, args.output_dir)
            
            # Clean up local file if it was synced from remote
            if is_remote_processing and local_file_path:
                print(f"Cleaning up {local_file_path}")
                cleanup_file(local_file_path)
                
        except Exception as e:
            print(f"Error processing {file_ref}: {e}")
            stats['error_count'] += 1
            # Clean up local file even on error if it was synced
            if is_remote_processing and local_file_path:
                cleanup_file(local_file_path)
    
    # Log run statistics
    if args.run_log:
        log_run(args.run_log, stats)
    
    print(f"\nCompleted: {stats['success_count']} successful, {stats['error_count']} errors")
    print(f"Total duration processed: {stats['total_duration']:.1f} seconds")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
