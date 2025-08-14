"""Pytest configuration and shared fixtures."""

import pytest
import tempfile
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
import sys
import os

# Add the parent directory to sys.path so we can import eduasr
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from eduasr.db import TranscriptDB


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_transcript_json():
    """Sample WhisperX transcript JSON data."""
    return {
        "segments": [
            {
                "start": 0.0,
                "end": 2.5,
                "text": "Hello everyone, welcome to class.",
                "speaker": "SPEAKER_00",
                "confidence": 0.95
            },
            {
                "start": 2.5,
                "end": 5.0,
                "text": "Today we will learn about math.",
                "speaker": "SPEAKER_00", 
                "confidence": 0.92
            },
            {
                "start": 5.0,
                "end": 7.5,
                "text": "Can everyone see the board?",
                "speaker": "SPEAKER_00",
                "confidence": 0.88
            },
            {
                "start": 7.5,
                "end": 9.0,
                "text": "Yes, we can see it clearly.",
                "speaker": "SPEAKER_01",
                "confidence": 0.90
            }
        ]
    }


@pytest.fixture
def sample_transcript_files(temp_dir, sample_transcript_json):
    """Create sample transcript files in multiple formats."""
    base_name = "test-lesson-001"
    
    # JSON file
    json_file = temp_dir / f"{base_name}.json"
    with open(json_file, 'w') as f:
        json.dump(sample_transcript_json, f, indent=2)
    
    # SRT file
    srt_file = temp_dir / f"{base_name}.srt"
    with open(srt_file, 'w') as f:
        f.write("""1
00:00:00,000 --> 00:00:02,500
Hello everyone, welcome to class.

2
00:00:02,500 --> 00:00:05,000
Today we will learn about math.

3
00:00:05,000 --> 00:00:07,500
Can everyone see the board?

4
00:00:07,500 --> 00:00:09,000
Yes, we can see it clearly.
""")
    
    # VTT file
    vtt_file = temp_dir / f"{base_name}.vtt"
    with open(vtt_file, 'w') as f:
        f.write("""WEBVTT

00:00:00.000 --> 00:00:02.500
Hello everyone, welcome to class.

00:00:02.500 --> 00:00:05.000
Today we will learn about math.

00:00:05.000 --> 00:00:07.500
Can everyone see the board?

00:00:07.500 --> 00:00:09.000
Yes, we can see it clearly.
""")
    
    # TXT file
    txt_file = temp_dir / f"{base_name}.txt"
    with open(txt_file, 'w') as f:
        f.write("Hello everyone, welcome to class. Today we will learn about math. Can everyone see the board? Yes, we can see it clearly.")
    
    # .done file
    done_file = temp_dir / f"{base_name}.done"
    done_file.touch()
    
    return {
        'json': json_file,
        'srt': srt_file,
        'vtt': vtt_file,
        'txt': txt_file,
        'done': done_file,
        'base_name': base_name
    }


@pytest.fixture
def test_db(temp_dir):
    """Create a test database with sample data."""
    db_path = temp_dir / "test.sqlite"
    
    with TranscriptDB(str(db_path)) as db:
        # Add a sample transcript manually
        cursor = db.conn.cursor()
        cursor.execute("""
            INSERT INTO transcripts (
                filename, file_hash, title, duration_seconds, segment_count,
                speaker_count, transcript_json_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "test-lesson-001", "abc123", "Test Lesson 001", 9.0, 4, 2, "/fake/path.json"
        ))
        transcript_id = cursor.lastrowid
        
        # Add sample segments
        segments_data = [
            (transcript_id, 0, 0.0, 2.5, "SPEAKER_00", "Hello everyone, welcome to class.", 0.95),
            (transcript_id, 1, 2.5, 5.0, "SPEAKER_00", "Today we will learn about math.", 0.92),
            (transcript_id, 2, 5.0, 7.5, "SPEAKER_00", "Can everyone see the board?", 0.88),
            (transcript_id, 3, 7.5, 9.0, "SPEAKER_01", "Yes, we can see it clearly.", 0.90),
        ]
        
        cursor.executemany("""
            INSERT INTO segments (
                transcript_id, segment_index, start_time, end_time,
                speaker, text, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, segments_data)
        
        # Manually populate FTS table (since triggers might not work in test)
        cursor.executemany("""
            INSERT INTO segments_fts (text, speaker, filename, title)
            VALUES (?, ?, ?, ?)
        """, [
            ("Hello everyone, welcome to class.", "SPEAKER_00", "test-lesson-001", "Test Lesson 001"),
            ("Today we will learn about math.", "SPEAKER_00", "test-lesson-001", "Test Lesson 001"),
            ("Can everyone see the board?", "SPEAKER_00", "test-lesson-001", "Test Lesson 001"),
            ("Yes, we can see it clearly.", "SPEAKER_01", "test-lesson-001", "Test Lesson 001"),
        ])
        
        db.conn.commit()
    
    return str(db_path)


@pytest.fixture
def mock_whisperx():
    """Mock WhisperX for testing transcription without actual model loading."""
    with patch('eduasr.transcribe_batch.whisperx') as mock:
        # Mock the load_model function
        mock_model = Mock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "This is a test transcription.",
                    "confidence": 0.95
                }
            ]
        }
        mock.load_model.return_value = mock_model
        
        # Mock load_audio function
        mock.load_audio.return_value = [0.1, 0.2, 0.3]  # Fake audio data
        
        # Mock align function
        mock.align.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "This is a test transcription.",
                    "confidence": 0.95,
                    "speaker": "SPEAKER_00"
                }
            ]
        }
        
        yield mock


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        'model_size': 'tiny',
        'language': 'en',
        'device': 'cpu',
        'compute_type': 'int8',
        'batch_size': 4,
        'diarization': False,
        'write_json': True,
        'write_srt': True,
        'write_vtt': True,
        'write_txt': True
    }
