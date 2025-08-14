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


def transcribe_file(audio_file: str, output_dir: str, config: Dict[str, Any], model, model_a=None, metadata=None) -> Dict[str, Any]:
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
    if config.get('diarization', False) and config.get('diarization_backend') == 'pyannote':
        # This would require additional setup for pyannote models
        print("Note: Diarization not implemented in this version")
    
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
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def write_vtt(result: Dict, output_file: Path):
    """Write VTT subtitle file."""
    with open(output_file, 'w') as f:
        f.write("WEBVTT\n\n")
        for segment in result.get('segments', []):
            start = format_time_vtt(segment['start'])
            end = format_time_vtt(segment['end'])
            text = segment['text'].strip()
            f.write(f"{start} --> {end}\n{text}\n\n")


def write_txt(result: Dict, output_file: Path):
    """Write plain text file."""
    with open(output_file, 'w') as f:
        for segment in result.get('segments', []):
            f.write(segment['text'].strip() + ' ')


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
            
            result = transcribe_file(process_file_path, args.output_dir, config, model, model_a, metadata)
            
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
