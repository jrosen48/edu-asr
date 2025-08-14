"""Tests for database module."""

import pytest
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, mock_open

from eduasr.db import TranscriptDB, format_time, print_search_results, print_kwic_results


class TestTranscriptDB:
    """Test cases for TranscriptDB class."""
    
    def test_init_creates_tables(self, temp_dir):
        """Test that database initialization creates required tables."""
        db_path = temp_dir / "test.sqlite"
        
        with TranscriptDB(str(db_path)) as db:
            cursor = db.conn.cursor()
            
            # Check that main tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            assert 'transcripts' in tables
            assert 'segments' in tables
            assert 'segments_fts' in tables
    
    def test_calculate_file_hash(self, temp_dir):
        """Test file hash calculation."""
        db_path = temp_dir / "test.sqlite"
        test_file = temp_dir / "test.txt"
        
        with open(test_file, 'w') as f:
            f.write("test content")
        
        with TranscriptDB(str(db_path)) as db:
            hash1 = db.calculate_file_hash(test_file)
            hash2 = db.calculate_file_hash(test_file)
            
            # Same file should produce same hash
            assert hash1 == hash2
            assert len(hash1) == 32  # MD5 hash length
    
    def test_generate_title(self, temp_dir):
        """Test title generation from filename."""
        db_path = temp_dir / "test.sqlite"
        
        with TranscriptDB(str(db_path)) as db:
            # Test basic filename
            assert db.generate_title("hello-world") == "Hello World"
            
            # Test with date prefix
            assert db.generate_title("2023-01-15-meeting-notes") == "Meeting Notes"
            
            # Test with numbers and special chars
            assert db.generate_title("lesson_01_intro") == "Lesson Intro"
            
            # Test empty/problematic input
            assert db.generate_title("") == ""
            assert db.generate_title("123") == "123"
    
    def test_import_single_transcript(self, temp_dir, sample_transcript_files, sample_transcript_json):
        """Test importing a single transcript file."""
        db_path = temp_dir / "test.sqlite"
        
        with TranscriptDB(str(db_path)) as db:
            result = db.import_single_transcript(
                sample_transcript_files['json'], 
                temp_dir, 
                force=False
            )
            
            assert result == "imported"
            
            # Check transcript was added
            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transcripts")
            assert cursor.fetchone()[0] == 1
            
            # Check segments were added
            cursor.execute("SELECT COUNT(*) FROM segments")
            assert cursor.fetchone()[0] == 4
            
            # Test that re-importing without force skips
            result2 = db.import_single_transcript(
                sample_transcript_files['json'], 
                temp_dir, 
                force=False
            )
            assert result2 == "skipped"
    
    def test_import_transcript_files(self, temp_dir, sample_transcript_files):
        """Test importing multiple transcript files."""
        db_path = temp_dir / "test.sqlite"
        
        with TranscriptDB(str(db_path)) as db:
            stats = db.import_transcript_files(str(temp_dir), force=False)
            
            assert stats['imported'] == 1
            assert stats['updated'] == 0
            assert stats['skipped'] == 0
            assert stats['errors'] == 0
    
    def test_search(self, test_db):
        """Test full-text search functionality."""
        with TranscriptDB(test_db) as db:
            # Search for existing text
            results = db.search("math")
            assert len(results) == 1
            assert "math" in results[0]['text'].lower()
            
            # Search for non-existing text
            results = db.search("chemistry")
            assert len(results) == 0
            
            # Search with limit
            results = db.search("welcome", limit=1)
            assert len(results) <= 1
    
    def test_kwic(self, test_db):
        """Test keyword in context search."""
        with TranscriptDB(test_db) as db:
            results = db.kwic("math", context_words=3)
            
            assert len(results) >= 1
            result = results[0]
            assert 'left_context' in result
            assert 'keyword' in result
            assert 'right_context' in result
            assert result['keyword'].lower() == 'math'
    
    def test_get_transcript_stats(self, test_db):
        """Test getting database statistics."""
        with TranscriptDB(test_db) as db:
            stats = db.get_transcript_stats()
            
            assert stats['transcript_count'] == 1
            assert stats['segment_count'] == 4
            assert stats['total_duration_seconds'] == 9.0
            assert stats['total_duration_hours'] == 9.0 / 3600
            assert len(stats['longest_transcripts']) <= 5
    
    def test_list_transcripts(self, test_db):
        """Test listing transcripts."""
        with TranscriptDB(test_db) as db:
            transcripts = db.list_transcripts(limit=10)
            
            assert len(transcripts) == 1
            transcript = transcripts[0]
            assert transcript['filename'] == 'test-lesson-001'
            assert transcript['title'] == 'Test Lesson 001'
            assert transcript['duration_seconds'] == 9.0
            assert transcript['segment_count'] == 4
            assert transcript['speaker_count'] == 2


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_format_time(self):
        """Test time formatting function."""
        assert format_time(0) == "00:00:00"
        assert format_time(61) == "00:01:01"
        assert format_time(3661) == "01:01:01"
        assert format_time(3723.5) == "01:02:03"
    
    def test_print_search_results(self, capsys):
        """Test search results printing."""
        results = [
            {
                'title': 'Test Lesson',
                'filename': 'test-lesson-001',
                'speaker': 'SPEAKER_00',
                'start_time': 0.0,
                'end_time': 5.0,
                'snippet': 'This is a <mark>test</mark> snippet',
                'text': 'This is a test snippet for unit testing'
            }
        ]
        
        print_search_results(results, "test")
        captured = capsys.readouterr()
        
        assert "Found 1 results for 'test'" in captured.out
        assert "Test Lesson" in captured.out
        assert "SPEAKER_00" in captured.out
        assert "00:00:00-00:00:05" in captured.out
    
    def test_print_kwic_results(self, capsys):
        """Test KWIC results printing."""
        results = [
            {
                'title': 'Test Lesson',
                'speaker': 'SPEAKER_00',
                'start_time': 0.0,
                'left_context': 'This is a',
                'keyword': 'test',
                'right_context': 'snippet for unit'
            }
        ]
        
        print_kwic_results(results, "test")
        captured = capsys.readouterr()
        
        assert "KWIC results for 'test'" in captured.out
        assert "Test Lesson" in captured.out
        assert "**test**" in captured.out


class TestDatabaseIntegration:
    """Integration tests for database operations."""
    
    def test_full_import_and_search_workflow(self, temp_dir, sample_transcript_json):
        """Test complete workflow from import to search."""
        # Create sample files
        json_file = temp_dir / "workflow-test.json"
        with open(json_file, 'w') as f:
            json.dump(sample_transcript_json, f)
        
        db_path = temp_dir / "workflow.sqlite"
        
        # Import and search
        with TranscriptDB(str(db_path)) as db:
            # Import
            stats = db.import_transcript_files(str(temp_dir))
            assert stats['imported'] == 1
            
            # Search
            results = db.search("welcome")
            assert len(results) >= 1
            
            # KWIC
            kwic_results = db.kwic("class", context_words=5)
            assert len(kwic_results) >= 1
            
            # Stats
            stats = db.get_transcript_stats()
            assert stats['transcript_count'] == 1
            assert stats['segment_count'] == 4
    
    def test_database_context_manager(self, temp_dir):
        """Test database context manager properly closes connections."""
        db_path = temp_dir / "context.sqlite"
        
        # Use context manager
        with TranscriptDB(str(db_path)) as db:
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
        
        # Connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            cursor.execute("SELECT 1")
    
    def test_error_handling_malformed_json(self, temp_dir):
        """Test error handling for malformed JSON files."""
        # Create malformed JSON file
        bad_json_file = temp_dir / "bad.json"
        with open(bad_json_file, 'w') as f:
            f.write("{ invalid json content")
        
        db_path = temp_dir / "error.sqlite"
        
        with TranscriptDB(str(db_path)) as db:
            stats = db.import_transcript_files(str(temp_dir))
            assert stats['errors'] == 1
            assert stats['imported'] == 0
    
    def test_duplicate_filename_handling(self, temp_dir, sample_transcript_json):
        """Test handling of duplicate filenames with different content."""
        json_file = temp_dir / "duplicate-test.json"
        
        # First import
        with open(json_file, 'w') as f:
            json.dump(sample_transcript_json, f)
        
        db_path = temp_dir / "duplicate.sqlite"
        
        with TranscriptDB(str(db_path)) as db:
            result1 = db.import_single_transcript(json_file, temp_dir, force=False)
            assert result1 == "imported"
            
            # Modify content and re-import with force
            sample_transcript_json['segments'].append({
                "start": 10.0,
                "end": 12.0,
                "text": "This is additional content.",
                "speaker": "SPEAKER_02",
                "confidence": 0.85
            })
            
            with open(json_file, 'w') as f:
                json.dump(sample_transcript_json, f)
            
            result2 = db.import_single_transcript(json_file, temp_dir, force=True)
            assert result2 == "updated"
            
            # Should have 5 segments now
            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM segments WHERE transcript_id = 1")
            assert cursor.fetchone()[0] == 5
