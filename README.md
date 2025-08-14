# EDU ASR - Educational Audio/Video Transcription Toolkit

A comprehensive toolkit for transcribing educational audio/video content and performing qualitative analysis through full-text search.

## ✨ Features

- 🎵 **Batch transcription** using WhisperX with speaker diarization
- 🔄 **One-file-at-a-time processing** to manage disk space efficiently  
- 📁 **Remote sync support** via rclone (SharePoint, Google Drive, etc.)
- 🗄️ **SQLite database** with full-text search (FTS5)
- 🔍 **Advanced search capabilities** including keyword-in-context (KWIC)
- ⏰ **Smart resume** - skips already processed files
- 💾 **Multiple output formats** - JSON, SRT, VTT, TXT
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
# Set your remote path
export REMOTE_PATH='General/2025-07-28-2025-07-30-Tremont PD Data/PD Sessions/Video/2025-07-28'

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
  --query "student engagement"

# Keyword in context analysis
python -m eduasr.cli kwic \
  --db "out/edu_asr.sqlite" \
  --query "formative assessment" \
  --context 10

# Database statistics
python -m eduasr.cli stats --db "out/edu_asr.sqlite"

# List all transcripts
python -m eduasr.cli list --db "out/edu_asr.sqlite"
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
│   ├── *.done          # Processing markers
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
```

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

## 🤝 Contributing

This toolkit is designed for educational research workflows. Key design principles:

- **Space efficient**: One-file-at-a-time remote processing
- **Resumable**: Skip already processed files
- **Searchable**: Full-text search with context
- **Flexible**: Multiple input/output options
- **Reliable**: Error handling and progress tracking

## 📄 License

This project is intended for educational and research use.