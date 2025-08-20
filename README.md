# EDU ASR - Educational Audio/Video Transcription Toolkit

A comprehensive toolkit for transcribing educational audio/video content and performing qualitative analysis through full-text search.

## ✨ Features

- 🎵 **Batch transcription** using WhisperX with speaker diarization
- 🔄 **One-file-at-a-time processing** to manage disk space efficiently  
- 📁 **Remote sync support** via rclone (SharePoint, Google Drive, etc.)
- 🗄️ **SQLite database** with full-text search (FTS5)
- 🔍 **Advanced search capabilities** including keyword-in-context (KWIC)
- ⏰ **Smart resume** - skips already processed files
- 💾 **Multiple output formats** - JSON, SRT, VTT, TXT, CSV
- 🤖 **AI summarization** - Generate summaries via LM Studio
- 📊 **Processing statistics** and progress tracking

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Transcribe Audio/Video Files

**Local files:**
```bash
python -m eduasr.cli transcribe \
  --input_dir "/path/to/your/media" \
  --output_dir "out" \
  --config "config.yaml" \
  --model "medium.en"
```

**Remote files (SharePoint/OneDrive via rclone):**
```bash
export REMOTE_PATH='General/2025-07-28-2025-07-30-Tremont PD Data/PD Sessions/Video/2025-07-30'

python -m eduasr.cli transcribe \
  --rclone-remote "mysharepoint" \
  --remote-path "$REMOTE_PATH" \
  --scratch-dir "scratch" \
  --output_dir "out" \
  --config "config.yaml" \
  --model "medium.en" \
  --include-ext ".mov,.mp4,.m4a,.wav" \
  --min-free-gb 10 \
  --wait-if-low-disk \
  --max-files 100 \
  --run-log "out/run_log.csv"
```

### 3. Import Transcripts into Database

```bash
python -m eduasr.cli import \
  --transcripts-dir "out" \
  --db "out/edu_asr.sqlite"
```

### 4. Search and Analyze

```bash
# Full-text search
python -m eduasr.cli search \
  --db "out/edu_asr.sqlite" \
  --query "qualitative"

# Keyword in context analysis
python -m eduasr.cli kwic \
  --db "out/edu_asr.sqlite" \
  --query "data" \
  --context 10

# Database statistics
python -m eduasr.cli stats --db "out/edu_asr.sqlite"

# List all transcripts
python -m eduasr.cli list --db "out/edu_asr.sqlite"
```

### 5. Export to CSV for Excel/Sheets

```bash
# Export all JSON transcripts to CSV format
python -m eduasr.cli export-csv \
  --output-dir "out" \
  --force  # Optional: overwrite existing CSV files
```

### 6. Generate AI Summaries (LM Studio)

```bash
# First, test connection to LM Studio
python -m eduasr.cli summarize \
  --test \
  --output-dir "out" \
  --config "summarizer_config.yaml"

# Generate 1-3 paragraph summaries for all transcripts
python -m eduasr.cli summarize \
  --output-dir "out" \
  --config "summarizer_config.yaml" \
  --force  # Optional: overwrite existing summaries

# Collate all summaries into a single markdown document
python -m eduasr.cli collate-summaries \
  --output-dir "out" \
  --output-file "all_summaries.md"  # Optional: custom filename
```

### 7. Build Static Site

```bash
python build_static_index.py \
  --out-dir "./" \
  --static-dir "./static_site" \
  --title "Transcript Browser" \
  --inline
```

## 📖 Detailed Usage

### Transcription Command Options

```bash
python -m eduasr.cli transcribe --help
```

**Key Options:**
- `--model` - Whisper model size: `tiny`, `small`, `medium`, `large-v3` (quality vs speed)
- `--include-ext` - File extensions to process: `.mov,.mp4,.m4a,.wav,.mp3`
- `--max-files` - Limit number of files to process
- `--force` - Re-process already transcribed files
- `--min-free-gb` - Minimum free disk space required
- `--wait-if-low-disk` - Wait for disk space instead of failing

### Database Commands

| Command | Description | Example |
|---------|-------------|---------|
| `import` | Import transcripts into database | `python -m eduasr.cli import --transcripts-dir "out" --db "db.sqlite"` |
| `search` | Full-text search across all transcripts | `python -m eduasr.cli search --db "db.sqlite" --query "student"` |
| `kwic` | Keyword in context analysis | `python -m eduasr.cli kwic --db "db.sqlite" --query "learning"` |
| `list` | List all transcripts with metadata | `python -m eduasr.cli list --db "db.sqlite" --limit 20` |
| `stats` | Show database statistics | `python -m eduasr.cli stats --db "db.sqlite"` |
| `export-csv` | Export JSON transcripts to CSV | `python -m eduasr.cli export-csv --output-dir "out" --force` |
| `summarize` | Generate AI summaries via LM Studio | `python -m eduasr.cli summarize --output-dir "out" --config "summarizer_config.yaml"` |
| `collate-summaries` | Collate summaries into markdown | `python -m eduasr.cli collate-summaries --output-dir "out"` |

### Configuration

The `config.yaml` file controls transcription settings:

```yaml
# Whisper model configuration
model_size: medium.en      # tiny, small, medium, large-v3
language: en
device: cpu               # cpu or cuda
compute_type: int8        # int8, float16, float32

# Audio processing
vad: false               # Voice activity detection
batch_size: 8

# Speaker diarization
diarization: true
diarization_backend: pyannote
min_speaker_count: 1
max_speaker_count: 15
hf_token_env: HF_TOKEN   # Hugging Face token for pyannote

# Output formats
write_srt: true          # SubRip subtitles
write_vtt: true          # WebVTT subtitles  
write_json: true         # Full WhisperX output
write_txt: true          # Plain text
```

## 📁 File Organization

```
edu_asr/
├── config.yaml          # Transcription settings
├── requirements.txt     # Python dependencies
├── scratch/             # Temporary files (auto-cleaned)
├── out/                 # Transcription outputs
│   ├── *.json          # WhisperX results with timing
│   ├── *.srt           # Subtitle files
│   ├── *.vtt           # WebVTT files
│   ├── *.txt           # Plain text
│   ├── *.csv           # Excel/Sheets compatible format
│   ├── *.summary.json  # AI-generated summaries
│   ├── *.done          # Processing markers
│   ├── all_summaries.json  # Batch summary file
│   ├── all_summaries.md    # Collated markdown summary
│   ├── run_log.csv     # Processing statistics
│   └── edu_asr.sqlite  # Search database
└── eduasr/             # Python module
    ├── cli.py          # Command-line interface
    ├── transcribe_batch.py  # Transcription engine
    └── db.py           # Database operations
```

## 🔧 Advanced Features

### Remote File Processing

The toolkit supports efficient remote file processing:

1. **Lists** files on remote without downloading
2. **Filters** out already processed files  
3. **Downloads** one file at a time
4. **Transcribes** the file
5. **Uploads** results (if configured)
6. **Deletes** local copy to save space
7. **Repeats** for next file

This allows processing large remote collections without filling local storage.

### Search Capabilities

**Full-Text Search:**
- Search across all transcript text
- Supports phrases with quotes: `"exit ticket"`
- Case-insensitive matching
- Ranked results by relevance

**Keyword in Context (KWIC):**
- Shows words surrounding search terms
- Configurable context window
- Ideal for qualitative analysis
- Preserves speaker and timing information

**Database Features:**
- Fast SQLite FTS5 full-text search
- Speaker diarization preserved
- Precise timing information
- File metadata and statistics

### Model Selection Guide

| Model | Speed | Quality | Use Case |
|-------|-------|---------|----------|
| `tiny` | Fastest | Basic | Quick drafts, testing |
| `small` | Fast | Good | General use, real-time |
| `medium` | Moderate | Very Good | **Recommended default** |
| `large-v3` | Slow | Excellent | High-quality final transcripts |

Add `.en` suffix (e.g., `medium.en`) for English-only processing (faster).

## 🔍 Example Workflows

### Workflow 1: Local Media Files

```bash
# Transcribe a folder of recordings
python -m eduasr.cli transcribe \
  --input_dir "recordings/" \
  --output_dir "transcripts/" \
  --model "medium.en" \
  --config "config.yaml"

# Import into searchable database  
python -m eduasr.cli import \
  --transcripts-dir "transcripts/" \
  --db "research.sqlite"

# Search for themes
python -m eduasr.cli search --db "research.sqlite" --query "collaboration"
python -m eduasr.cli kwic --db "research.sqlite" --query "peer feedback" --context 15
```

### Workflow 2: SharePoint Integration

```bash
# Process remote files one-by-one (space efficient)
python -m eduasr.cli transcribe \
  --rclone-remote "sharepoint" \
  --remote-path "Research/Interviews/2024" \
  --scratch-dir "temp/" \
  --output_dir "results/" \
  --model "large-v3" \
  --min-free-gb 20 \
  --wait-if-low-disk \
  --run-log "processing.log"

# Build searchable database
python -m eduasr.cli import --transcripts-dir "results/" --db "interviews.sqlite"

# Analyze content
python -m eduasr.cli stats --db "interviews.sqlite"
python -m eduasr.cli search --db "interviews.sqlite" --query "student motivation"
```

### Workflow 3: Incremental Processing

```bash
# Initial batch
python -m eduasr.cli transcribe --input_dir "batch1/" --output_dir "out/"
python -m eduasr.cli import --transcripts-dir "out/" --db "corpus.sqlite"

# Add new files later (only processes new files)
python -m eduasr.cli transcribe --input_dir "batch2/" --output_dir "out/"
python -m eduasr.cli import --transcripts-dir "out/" --db "corpus.sqlite"

# Search across all batches
python -m eduasr.cli search --db "corpus.sqlite" --query "assessment strategies"

# Export to CSV for qualitative analysis in Excel/Sheets
python -m eduasr.cli export-csv --output-dir "out"

# Generate AI summaries using LM Studio
python -m eduasr.cli summarize --output-dir "out" --config "summarizer_config.yaml"

# Create a single markdown document with all summaries
python -m eduasr.cli collate-summaries --output-dir "out"
```

## 🤖 AI Summarization Setup

The summarization feature uses [LM Studio](https://lmstudio.ai/) to generate concise 1-3 paragraph summaries of educational transcripts, similar to Otter AI's meeting summaries.

### Prerequisites

1. **Download and install LM Studio** from https://lmstudio.ai/
2. **Load a model** - Recommended: Any 3B parameter instruct model (e.g., Phi-3.5-mini-instruct, Qwen2.5-3B-Instruct)
3. **Start the local server** in LM Studio (Server tab → Start Server)

### Configuration

Edit `summarizer_config.yaml` to match your setup:

```yaml
summarizer:
  lm_studio_url: "http://127.0.0.1:1234"  # Default LM Studio URL
  model_name: "meta-llama-3.1-8b-instruct"               # Adjust to your loaded model
  max_tokens: 512                         # Summary length
  temperature: 0.7                        # Creativity (0.0-1.0)
```

### Usage

```bash
# Test connection first
python -m eduasr.cli summarize --test --output-dir "out" --config "summarizer_config.yaml"

# Generate summaries for all transcripts
python -m eduasr.cli summarize --output-dir "out" --config "summarizer_config.yaml"

# Force regenerate existing summaries
python -m eduasr.cli summarize --output-dir "out" --config "summarizer_config.yaml" --force
```

### Output Files

- `*.summary.json` - Individual summary files
- `all_summaries.json` - Batch summary with metadata
- `all_summaries.md` - Collated markdown document (use `collate-summaries` command)
- Each summary focuses on educational content, themes, and key interactions

## 🛠️ Troubleshooting

**Common Issues:**

1. **"No module named 'whisperx'"**
   ```bash
   pip install -r requirements.txt
   ```

2. **Out of disk space**
   - Use `--min-free-gb` and `--wait-if-low-disk` options
   - Process files in smaller batches with `--max-files`

3. **Slow transcription**
   - Try smaller model: `--model "small.en"`
   - Reduce batch size in `config.yaml`: `batch_size: 4`

4. **Missing audio files**
   - Check file extensions with `--include-ext`
   - Verify case sensitivity (auto-handled)

5. **Search not working**
   - Re-import transcripts: `--force` flag
   - Check database path exists

6. **Summarization not working**
   - Test LM Studio connection: `python -m eduasr.cli summarize --test --output-dir "out"`
   - Ensure LM Studio is running and has a model loaded
   - Check the model name in `summarizer_config.yaml` matches your loaded model
   - Verify the LM Studio server URL (default: http://localhost:1234)

## 📊 Output Formats

### JSON (WhisperX Format)
Complete transcription with timing, confidence, and speaker data:
```json
{
  "segments": [
    {
      "start": 0.5,
      "end": 3.2, 
      "text": "Welcome to today's lesson",
      "speaker": "SPEAKER_00",
      "confidence": 0.95
    }
  ]
}
```

### SRT (SubRip)
Standard subtitle format for video players:
```
1
00:00:00,500 --> 00:00:03,200
Welcome to today's lesson
```

### VTT (WebVTT)
Web-compatible subtitle format:
```
WEBVTT

00:00:00.500 --> 00:00:03.200
Welcome to today's lesson
```

### TXT (Plain Text)
Simple text output for reading:
```
Welcome to today's lesson. Today we'll explore...
```

### CSV (Excel/Sheets Compatible)
Structured data format for analysis in Excel or Google Sheets:
```csv
start_time,end_time,speaker,text
0.5,3.2,SPEAKER_00,"Welcome to today's lesson"
3.2,6.8,SPEAKER_01,"Thank you for having us"
6.8,10.5,N/A,"Today we'll explore data analysis"
```

**Columns:**
- `start_time`: Segment start time in seconds
- `end_time`: Segment end time in seconds  
- `speaker`: Speaker ID (N/A if no diarization)
- `text`: Transcript text

### Summary JSON (AI-Generated)
Educational summaries generated by LM Studio:
```json
{
  "file": "/path/to/transcript.json",
  "filename": "lesson-001.json",
  "summary": "This educational session focused on data analysis techniques in the classroom. The instructor introduced various methods for students to collect, visualize, and interpret data through hands-on experiments. Key activities included partner-based data collection exercises and collaborative analysis of results.\n\nThe discussion emphasized the importance of student-centered learning approaches, with participants exploring how data literacy can be integrated across different subject areas. The session concluded with strategies for helping students develop critical thinking skills through data interpretation and evidence-based reasoning.",
  "total_segments": 156,
  "total_duration_seconds": 1847.3,
  "speaker_count": 4,
  "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02", "SPEAKER_03"],
  "generated_at": "2024-01-15 14:30:22"
}
```

### Markdown Summary (Collated)
All summaries combined in a single readable document:
```markdown
# Transcript Summaries

*Generated on 2025-08-19 at 11:50:01*

This document contains AI-generated summaries of 8 educational transcripts.

---

## 1. lesson-001

**File:** `lesson-001.json`  
**Duration:** 30.7 minutes  
**Segments:** 156  
**Speakers:** 4 (SPEAKER_00, SPEAKER_01, SPEAKER_02, SPEAKER_03)  
**Generated:** 2025-01-15 14:30:22  

This educational session focused on data analysis techniques in the classroom. The instructor introduced various methods for students to collect, visualize, and interpret data through hands-on experiments. Key activities included partner-based data collection exercises and collaborative analysis of results.

The discussion emphasized the importance of student-centered learning approaches, with participants exploring how data literacy can be integrated across different subject areas. The session concluded with strategies for helping students develop critical thinking skills through data interpretation and evidence-based reasoning.

---

## 2. lesson-002
...
```

## 🤝 Contributing

This toolkit is designed for educational research workflows. Key design principles:

- **Space efficient**: One-file-at-a-time remote processing
- **Resumable**: Skip already processed files
- **Searchable**: Full-text search with context
- **Flexible**: Multiple input/output options
- **Reliable**: Error handling and progress tracking

## 📄 License

This project is intended for educational and research use.