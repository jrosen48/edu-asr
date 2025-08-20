#!/usr/bin/env python3
"""Transcript summarization module using LM Studio."""

import json
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
import time


class LMStudioSummarizer:
    """Summarizer that uses LM Studio for generating transcript summaries."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the summarizer with configuration."""
        self.base_url = config.get('lm_studio_url', 'http://localhost:1234')
        self.model_name = config.get('model_name', '3b-instruct')
        self.max_tokens = config.get('max_tokens', 512)
        self.temperature = config.get('temperature', 0.7)
        self.timeout = config.get('timeout', 60)
        
        # Prompt template for summarization
        self.summary_prompt = config.get('summary_prompt', """
Please provide a concise summary of this educational transcript in 1-3 paragraphs. Focus on:
- Main topics and themes discussed
- Key learning objectives or educational content
- Important interactions or activities mentioned
- Any notable outcomes or conclusions

Transcript:
{transcript_text}

Summary:
""").strip()
    
    def _make_api_request(self, prompt: str) -> Optional[str]:
        """Make API request to LM Studio."""
        try:
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": False
            }
            
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content'].strip()
            else:
                print(f"❌ API request failed with status {response.status_code}: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error connecting to LM Studio: {e}")
        except Exception as e:
            print(f"❌ Error making API request: {e}")
            
        return None
    
    def _prepare_transcript_text(self, segments: List[Dict]) -> str:
        """Convert transcript segments to readable text."""
        text_parts = []
        current_speaker = None
        
        for segment in segments:
            speaker = segment.get('speaker')
            text = segment.get('text', '').strip()
            
            if not text:
                continue
            
            # Handle None speaker values
            if speaker is None:
                speaker = 'N/A'
                
            # Add speaker label when it changes
            if speaker != 'N/A' and speaker != current_speaker:
                current_speaker = speaker
                text_parts.append(f"\n[{speaker}]")
            
            text_parts.append(text)
        
        return ' '.join(text_parts).strip()
    
    def _truncate_transcript(self, text: str, max_chars: int = 8000) -> str:
        """Truncate transcript if too long, keeping beginning and end."""
        if len(text) <= max_chars:
            return text
            
        # Keep first 60% and last 20% of the transcript
        keep_start = int(max_chars * 0.6)
        keep_end = int(max_chars * 0.2)
        
        start_text = text[:keep_start]
        end_text = text[-keep_end:]
        
        return f"{start_text}\n\n[... middle portion omitted for length ...]\n\n{end_text}"
    
    def summarize_transcript(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """Summarize a single transcript JSON file."""
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            segments = data.get('segments', [])
            if not segments:
                print(f"⚠️  No segments found in {json_file.name}")
                return None
            
            # Prepare transcript text
            transcript_text = self._prepare_transcript_text(segments)
            if not transcript_text.strip():
                print(f"⚠️  No text content found in {json_file.name}")
                return None
            
            # Truncate if too long
            transcript_text = self._truncate_transcript(transcript_text)
            
            # Create prompt
            prompt = self.summary_prompt.format(transcript_text=transcript_text)
            
            # Generate summary
            print(f"🤖 Generating summary for {json_file.name}...")
            summary = self._make_api_request(prompt)
            
            if summary:
                # Calculate some basic stats
                total_segments = len(segments)
                total_duration = 0
                speakers = set()
                
                for segment in segments:
                    # Handle end time safely
                    end_time = segment.get('end')
                    if end_time is not None:
                        total_duration = max(total_duration, end_time)
                    
                    # Handle speaker safely
                    speaker = segment.get('speaker')
                    if speaker is not None and speaker != 'N/A':
                        speakers.add(speaker)
                
                return {
                    'file': str(json_file),
                    'filename': json_file.name,
                    'summary': summary,
                    'total_segments': total_segments,
                    'total_duration_seconds': total_duration,
                    'speaker_count': len(speakers),
                    'speakers': sorted(list(speakers)) if speakers else [],
                    'generated_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                print(f"❌ Failed to generate summary for {json_file.name}")
                return None
                
        except Exception as e:
            print(f"❌ Error processing {json_file.name}: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test connection to LM Studio API."""
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if response.status_code == 200:
                models = response.json()
                print(f"✅ Connected to LM Studio at {self.base_url}")
                if 'data' in models:
                    print(f"📋 Available models: {[m.get('id', 'unknown') for m in models['data']]}")
                return True
            else:
                print(f"❌ LM Studio responded with status {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to LM Studio at {self.base_url}: {e}")
            return False


def load_summarizer_config(config_file: Path = None) -> Dict[str, Any]:
    """Load summarizer configuration from file."""
    default_config = {
        'lm_studio_url': 'http://localhost:1234',
        'model_name': '3b-instruct',
        'max_tokens': 512,
        'temperature': 0.7,
        'timeout': 60,
        'summary_prompt': """
Please provide a concise summary of this educational transcript in 1-3 paragraphs. Focus on:
- Main topics and themes discussed
- Key learning objectives or educational content
- Important interactions or activities mentioned
- Any notable outcomes or conclusions

Transcript:
{transcript_text}

Summary:
""".strip()
    }
    
    if config_file and config_file.exists():
        try:
            with open(config_file, 'r') as f:
                if config_file.suffix.lower() == '.json':
                    user_config = json.load(f)
                else:
                    # Assume YAML
                    import yaml
                    user_config = yaml.safe_load(f)
            
            # Merge with defaults
            default_config.update(user_config.get('summarizer', {}))
        except Exception as e:
            print(f"⚠️  Error loading config from {config_file}: {e}")
            print("Using default configuration")
    
    return default_config


def collate_summaries_to_markdown(output_dir: str, output_file: str = None):
    """Collate all summary files into a single markdown document."""
    output_path = Path(output_dir)
    
    if not output_path.exists():
        print(f"❌ Output directory '{output_dir}' does not exist")
        return False
    
    # Find all summary files
    summary_files = list(output_path.glob("*.summary.json"))
    if not summary_files:
        print(f"❌ No summary files found in '{output_dir}'")
        print("💡 Run summarization first: python -m eduasr.cli summarize --output-dir out")
        return False
    
    # Sort by filename for consistent ordering
    summary_files.sort(key=lambda x: x.name)
    
    # Default output file
    if output_file is None:
        output_file = str(output_path / "all_summaries.md")
    
    print(f"📝 Collating {len(summary_files)} summaries into markdown...")
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write header
            f.write("# Transcript Summaries\n\n")
            f.write(f"*Generated on {time.strftime('%Y-%m-%d at %H:%M:%S')}*\n\n")
            f.write(f"This document contains AI-generated summaries of {len(summary_files)} educational transcripts.\n\n")
            f.write("---\n\n")
            
            # Process each summary file
            for i, summary_file in enumerate(summary_files, 1):
                try:
                    with open(summary_file, 'r', encoding='utf-8') as sf:
                        summary_data = json.load(sf)
                    
                    # Extract filename without extension for cleaner headers
                    base_name = Path(summary_data['filename']).stem
                    
                    # Write section header
                    f.write(f"## {i}. {base_name}\n\n")
                    
                    # Write metadata
                    duration_min = summary_data.get('total_duration_seconds', 0) / 60
                    f.write(f"**File:** `{summary_data['filename']}`  \n")
                    f.write(f"**Duration:** {duration_min:.1f} minutes  \n")
                    f.write(f"**Segments:** {summary_data.get('total_segments', 0)}  \n")
                    
                    speaker_count = summary_data.get('speaker_count', 0)
                    if speaker_count > 0:
                        speakers = summary_data.get('speakers', [])
                        f.write(f"**Speakers:** {speaker_count} ({', '.join(speakers)})  \n")
                    else:
                        f.write(f"**Speakers:** Not available  \n")
                    
                    f.write(f"**Generated:** {summary_data.get('generated_at', 'Unknown')}  \n\n")
                    
                    # Write summary
                    summary_text = summary_data.get('summary', 'No summary available')
                    f.write(f"{summary_text}\n\n")
                    f.write("---\n\n")
                    
                    print(f"✅ Added {base_name}")
                    
                except Exception as e:
                    print(f"⚠️  Error processing {summary_file.name}: {e}")
                    continue
        
        print(f"\n📄 Markdown file created: {output_file}")
        print(f"📊 Successfully collated {len(summary_files)} summaries")
        
        # Show file size
        file_size = Path(output_file).stat().st_size / 1024  # KB
        print(f"📏 File size: {file_size:.1f} KB")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating markdown file: {e}")
        return False


def batch_summarize(output_dir: str, config_file: str = None, force: bool = False):
    """Summarize all JSON transcript files in a directory."""
    output_path = Path(output_dir)
    
    if not output_path.exists():
        print(f"❌ Output directory '{output_dir}' does not exist")
        return
    
    # Load configuration
    config_path = Path(config_file) if config_file else None
    config = load_summarizer_config(config_path)
    
    # Initialize summarizer
    summarizer = LMStudioSummarizer(config)
    
    # Test connection first
    if not summarizer.test_connection():
        print("\n💡 Make sure LM Studio is running and has a model loaded.")
        print("   Start LM Studio and load your 3b instruct model, then try again.")
        return
    
    # Find JSON files
    json_files = list(output_path.glob("*.json"))
    if not json_files:
        print(f"❌ No JSON transcript files found in '{output_dir}'")
        return
    
    print(f"\n🔄 Found {len(json_files)} JSON transcript files")
    
    summaries = []
    success_count = 0
    skipped_count = 0
    error_count = 0
    
    for json_file in json_files:
        summary_file = json_file.with_suffix('.summary.json')
        
        # Skip if summary already exists and not forcing
        if summary_file.exists() and not force:
            print(f"⏭️  Skipping {json_file.name} (summary already exists, use --force to overwrite)")
            skipped_count += 1
            continue
        
        # Generate summary
        summary_data = summarizer.summarize_transcript(json_file)
        
        if summary_data:
            # Save individual summary file
            with open(summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)
            
            summaries.append(summary_data)
            success_count += 1
            print(f"✅ Summary saved to {summary_file.name}")
        else:
            error_count += 1
    
    # Save batch summary file
    if summaries:
        batch_summary_file = output_path / "all_summaries.json"
        with open(batch_summary_file, 'w') as f:
            json.dump({
                'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_files': len(summaries),
                'summaries': summaries
            }, f, indent=2)
        
        print(f"📄 Batch summary saved to {batch_summary_file.name}")
    
    print(f"\n📊 Summarization Complete:")
    print(f"   ✅ Summarized: {success_count}")
    print(f"   ⏭️  Skipped: {skipped_count}")
    print(f"   ❌ Errors: {error_count}")
    
    if success_count > 0:
        print(f"\n💡 Summary files created:")
        print(f"   • Individual: *.summary.json files")
        print(f"   • Batch: all_summaries.json")
        print(f"   • Each summary is 1-3 paragraphs focusing on educational content")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Summarize transcripts using LM Studio")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Summarize command
    sum_parser = subparsers.add_parser("summarize", help="Generate summaries")
    sum_parser.add_argument("--output-dir", required=True, help="Directory containing JSON transcript files")
    sum_parser.add_argument("--config", help="Configuration file (JSON or YAML)")
    sum_parser.add_argument("--force", action="store_true", help="Force overwrite existing summaries")
    sum_parser.add_argument("--test", action="store_true", help="Test connection to LM Studio")
    
    # Collate command
    collate_parser = subparsers.add_parser("collate", help="Collate summaries to markdown")
    collate_parser.add_argument("--output-dir", required=True, help="Directory containing summary files")
    collate_parser.add_argument("--output-file", help="Output markdown file")
    
    args = parser.parse_args()
    
    if args.command == "summarize":
        if args.test:
            config = load_summarizer_config(Path(args.config) if args.config else None)
            summarizer = LMStudioSummarizer(config)
            summarizer.test_connection()
        else:
            batch_summarize(args.output_dir, args.config, args.force)
    elif args.command == "collate":
        collate_summaries_to_markdown(args.output_dir, args.output_file)
    else:
        parser.print_help()
