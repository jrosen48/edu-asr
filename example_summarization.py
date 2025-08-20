#!/usr/bin/env python3
"""
Example script demonstrating EDU ASR summarization workflow.

This script shows how to:
1. Test LM Studio connection
2. Generate summaries for transcripts
3. Read and display summary results

Prerequisites:
- LM Studio running with a 3B instruct model loaded
- JSON transcript files in the 'out' directory
"""

import subprocess
import json
from pathlib import Path


def run_command(cmd, description):
    """Run a command and print the result."""
    print(f"\n🔄 {description}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def main():
    """Main example workflow."""
    print("EDU ASR Summarization Example")
    print("=" * 60)
    
    # Step 1: Test LM Studio connection
    success = run_command([
        "python3", "-m", "eduasr.cli", "summarize", 
        "--test", 
        "--output-dir", "out", 
        "--config", "summarizer_config.yaml"
    ], "Testing LM Studio connection")
    
    if not success:
        print("\n❌ LM Studio connection failed!")
        print("Please ensure:")
        print("1. LM Studio is running")
        print("2. A 3B instruct model is loaded")
        print("3. The server is started (Server tab → Start Server)")
        return
    
    # Step 2: Generate summaries (dry run - just a few files)
    print("\n" + "=" * 60)
    print("🤖 Generating summaries...")
    
    success = run_command([
        "python3", "-m", "eduasr.cli", "summarize",
        "--output-dir", "out",
        "--config", "summarizer_config.yaml"
    ], "Generating AI summaries for all transcripts")
    
    if not success:
        print("❌ Summary generation failed!")
        return
    
    # Step 3: Show example summary
    print("\n" + "=" * 60)
    print("📄 Example Summary Results:")
    
    out_dir = Path("out")
    summary_files = list(out_dir.glob("*.summary.json"))
    
    if summary_files:
        # Show first summary as example
        example_file = summary_files[0]
        with open(example_file) as f:
            summary_data = json.load(f)
        
        print(f"\nFile: {summary_data['filename']}")
        print(f"Duration: {summary_data['total_duration_seconds']:.1f} seconds")
        print(f"Segments: {summary_data['total_segments']}")
        print(f"Speakers: {summary_data['speaker_count']}")
        print(f"\nSummary:")
        print("-" * 40)
        print(summary_data['summary'])
        print("-" * 40)
        
        print(f"\n✅ Found {len(summary_files)} summary files")
        print("📁 Individual summaries: *.summary.json")
        
        batch_file = out_dir / "all_summaries.json"
        if batch_file.exists():
            print("📄 Batch summary: all_summaries.json")
    else:
        print("No summary files found.")
    
    print("\n🎉 Example workflow complete!")
    print("\nNext steps:")
    print("- Review individual *.summary.json files")
    print("- Use summaries for qualitative analysis")
    print("- Integrate with your research workflow")


if __name__ == "__main__":
    main()

