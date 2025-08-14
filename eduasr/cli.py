#!/usr/bin/env python3
"""Unified command-line interface for EDU ASR."""

import argparse
import sys
from pathlib import Path
from . import transcribe_batch
from .db import TranscriptDB, print_search_results, print_kwic_results, format_time


def create_parser():
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        description="EDU ASR unified command-line interface",
        prog="eduasr"
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        required=True
    )
    
    # Transcribe subcommand
    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Batch transcribe audio files"
    )
    
    # Add all transcribe arguments
    transcribe_parser.add_argument("--rclone-remote", help="Rclone remote name")
    transcribe_parser.add_argument("--remote-path", help="Remote path to sync from")
    transcribe_parser.add_argument("--input_dir", help="Local input directory")
    transcribe_parser.add_argument("--scratch-dir", help="Scratch directory for temporary files")
    transcribe_parser.add_argument("--include-ext", help="File extensions to include (comma-separated)")
    transcribe_parser.add_argument("--max-files", type=int, help="Maximum number of files to process")
    transcribe_parser.add_argument("--output_dir", required=True, help="Output directory for transcripts")
    transcribe_parser.add_argument("--config", help="Config file path")
    transcribe_parser.add_argument(
        "--model",
        choices=["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large", "large-v1", "large-v2", "large-v3"],
        help="Whisper model to use"
    )
    transcribe_parser.add_argument("--force", action="store_true", help="Force reprocessing of existing files")
    transcribe_parser.add_argument("--min-free-gb", type=float, help="Minimum free disk space in GB")
    transcribe_parser.add_argument("--wait-if-low-disk", action="store_true", help="Wait if disk space is low")
    transcribe_parser.add_argument("--check-interval-s", type=int, help="Disk check interval in seconds")
    transcribe_parser.add_argument("--max-wait-min", type=int, help="Maximum wait time in minutes")
    transcribe_parser.add_argument("--run-log", help="Run log file path")
    
    # Import subcommand
    import_parser = subparsers.add_parser(
        "import",
        help="Import existing transcripts into database"
    )
    import_parser.add_argument("--transcripts-dir", required=True, help="Directory containing transcript files")
    import_parser.add_argument("--db", required=True, help="Database file path")
    import_parser.add_argument("--force", action="store_true", help="Force re-import of existing transcripts")
    
    # Search subcommand
    search_parser = subparsers.add_parser(
        "search",
        help="Search transcripts in database"
    )
    search_parser.add_argument("--db", required=True, help="Database file path")
    search_parser.add_argument("--query", required=True, help="Search query")
    search_parser.add_argument("--limit", type=int, default=50, help="Maximum number of results")
    
    # KWIC (Keyword In Context) subcommand
    kwic_parser = subparsers.add_parser(
        "kwic",
        help="Keyword in context search"
    )
    kwic_parser.add_argument("--db", required=True, help="Database file path")
    kwic_parser.add_argument("--query", required=True, help="Search query")
    kwic_parser.add_argument("--context", type=int, default=10, help="Number of context words")
    kwic_parser.add_argument("--limit", type=int, default=50, help="Maximum number of results")
    
    # List subcommand
    list_parser = subparsers.add_parser(
        "list",
        help="List transcripts in database"
    )
    list_parser.add_argument("--db", required=True, help="Database file path")
    list_parser.add_argument("--limit", type=int, default=50, help="Maximum number of transcripts to show")
    
    # Stats subcommand
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show database statistics"
    )
    stats_parser.add_argument("--db", required=True, help="Database file path")
    
    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.command == "transcribe":
        # Set up sys.argv for the transcribe_batch module
        argv = ['transcribe_batch.py']
        for arg in vars(args):
            if arg != "command" and getattr(args, arg) is not None:
                value = getattr(args, arg)
                flag = f"--{arg}"  # Keep underscores as they are
                if isinstance(value, bool):
                    if value:
                        argv.append(flag)
                else:
                    argv.extend([flag, str(value)])
        
        # Temporarily replace sys.argv and call the main function
        original_argv = sys.argv[:]
        try:
            sys.argv = argv
            return transcribe_batch.main()
        finally:
            sys.argv = original_argv
    
    elif args.command == "import":
        with TranscriptDB(args.db) as db:
            print(f"Importing transcripts from {args.transcripts_dir} into {args.db}")
            stats = db.import_transcript_files(args.transcripts_dir, args.force)
            print(f"\n📊 Import complete:")
            print(f"   ✅ Imported: {stats['imported']}")
            print(f"   🔄 Updated: {stats['updated']}")
            print(f"   ⏭️  Skipped: {stats['skipped']}")
            print(f"   ❌ Errors: {stats['errors']}")
        return 0
    
    elif args.command == "search":
        with TranscriptDB(args.db) as db:
            results = db.search(args.query, args.limit)
            print_search_results(results, args.query)
        return 0
    
    elif args.command == "kwic":
        with TranscriptDB(args.db) as db:
            results = db.kwic(args.query, args.context, args.limit)
            print_kwic_results(results, args.query)
        return 0
    
    elif args.command == "list":
        with TranscriptDB(args.db) as db:
            transcripts = db.list_transcripts(args.limit)
            print(f"\n📝 Transcripts in database:\n")
            for i, t in enumerate(transcripts, 1):
                duration = format_time(t['duration_seconds'])
                print(f"[{i:2d}] {t['title']} ({t['filename']})")
                print(f"     Duration: {duration} | Segments: {t['segment_count']} | Speakers: {t['speaker_count']}")
                print(f"     Created: {t['created_at'][:19]}")
                print()
        return 0
    
    elif args.command == "stats":
        with TranscriptDB(args.db) as db:
            stats = db.get_transcript_stats()
            print(f"\n📊 Database Statistics:")
            print(f"   📝 Transcripts: {stats['transcript_count']}")
            print(f"   💬 Segments: {stats['segment_count']:,}")
            print(f"   ⏱️  Total Duration: {stats['total_duration_hours']:.1f} hours")
            print(f"\n🏆 Longest Transcripts:")
            for i, t in enumerate(stats['longest_transcripts'], 1):
                duration = format_time(t['duration_seconds'])
                print(f"   {i}. {t['filename']} ({duration})")
        return 0
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
