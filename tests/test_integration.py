"""Integration tests for the complete EDU ASR workflow."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

from eduasr.db import TranscriptDB
from eduasr.cli import main


@pytest.mark.integration
class TestCompleteWorkflow:
    """Test complete workflows from transcription to search."""
    
    def test_import_and_search_workflow(self, temp_dir, sample_transcript_json):
        """Test complete workflow: create transcripts -> import -> search."""
        # Create sample transcript files
        json_file = temp_dir / "integration-test.json"
        with open(json_file, 'w') as f:
            json.dump(sample_transcript_json, f)
        
        srt_file = temp_dir / "integration-test.srt"
        with open(srt_file, 'w') as f:
            f.write("""1
00:00:00,000 --> 00:00:02,500
Hello everyone, welcome to class.

2
00:00:02,500 --> 00:00:05,000
Today we will learn about math.
""")
        
        db_path = temp_dir / "integration.sqlite"
        
        # Step 1: Import transcripts
        with patch('sys.argv', [
            'eduasr.cli', 'import',
            '--transcripts-dir', str(temp_dir),
            '--db', str(db_path)
        ]):
            result = main()
            assert result == 0
        
        # Step 2: Search transcripts
        with patch('sys.argv', [
            'eduasr.cli', 'search',
            '--db', str(db_path),
            '--query', 'math',
            '--limit', '10'
        ]):
            with patch('eduasr.cli.print_search_results') as mock_print:
                result = main()
                assert result == 0
                mock_print.assert_called_once()
                
                # Check that search results were passed to print function
                call_args = mock_print.call_args[0]
                results = call_args[0]
                query = call_args[1]
                
                assert query == 'math'
                assert len(results) >= 1
                assert any('math' in r['text'].lower() for r in results)
        
        # Step 3: KWIC analysis
        with patch('sys.argv', [
            'eduasr.cli', 'kwic',
            '--db', str(db_path),
            '--query', 'welcome',
            '--context', '5',
            '--limit', '5'
        ]):
            with patch('eduasr.cli.print_kwic_results') as mock_print_kwic:
                result = main()
                assert result == 0
                mock_print_kwic.assert_called_once()
        
        # Step 4: Database statistics
        with patch('sys.argv', [
            'eduasr.cli', 'stats',
            '--db', str(db_path)
        ]):
            result = main()
            assert result == 0
    
    @patch('eduasr.transcribe_batch.whisperx')
    def test_transcribe_to_search_workflow(self, mock_whisperx, temp_dir):
        """Test workflow from transcription to search (mocked transcription)."""
        # Mock WhisperX components
        mock_model = Mock()
        mock_model.transcribe.return_value = {
            'segments': [
                {
                    'start': 0.0,
                    'end': 3.0,
                    'text': 'This is a test lesson about mathematics.',
                    'confidence': 0.95
                },
                {
                    'start': 3.0,
                    'end': 6.0,
                    'text': 'Students should pay attention to the examples.',
                    'confidence': 0.92
                }
            ]
        }
        mock_whisperx.load_model.return_value = mock_model
        mock_whisperx.load_audio.return_value = [0.1, 0.2, 0.3]  # Mock audio data
        mock_whisperx.align.return_value = mock_model.transcribe.return_value
        
        # Create fake audio file
        audio_file = temp_dir / "test-lesson.wav"
        audio_file.write_bytes(b'fake audio data')
        
        output_dir = temp_dir / "output"
        db_path = temp_dir / "workflow.sqlite"
        
        # Step 1: Transcribe (mocked)
        with patch('sys.argv', [
            'eduasr.cli', 'transcribe',
            '--input_dir', str(temp_dir),
            '--output_dir', str(output_dir),
            '--model', 'tiny'
        ]):
            with patch('eduasr.transcribe_batch.tqdm', side_effect=lambda x, desc=None: x):
                result = main()
                assert result == 0
        
        # Check that output files were created
        json_output = output_dir / "test-lesson.json"
        assert json_output.exists()
        
        # Step 2: Import transcripts
        with patch('sys.argv', [
            'eduasr.cli', 'import',
            '--transcripts-dir', str(output_dir),
            '--db', str(db_path)
        ]):
            result = main()
            assert result == 0
        
        # Step 3: Search for content
        with patch('sys.argv', [
            'eduasr.cli', 'search',
            '--db', str(db_path),
            '--query', 'mathematics',
            '--limit', '10'
        ]):
            with patch('eduasr.cli.print_search_results') as mock_print:
                result = main()
                assert result == 0
                
                call_args = mock_print.call_args[0]
                results = call_args[0]
                assert len(results) >= 1
                assert any('mathematics' in r['text'].lower() for r in results)


@pytest.mark.integration
class TestErrorRecovery:
    """Test error recovery and edge cases in integrated workflows."""
    
    def test_partial_import_recovery(self, temp_dir):
        """Test recovery from partial import failures."""
        # Create one good transcript and one bad transcript
        good_transcript = {
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'Good transcript.'}
            ]
        }
        
        good_file = temp_dir / "good.json"
        with open(good_file, 'w') as f:
            json.dump(good_transcript, f)
        
        bad_file = temp_dir / "bad.json"
        with open(bad_file, 'w') as f:
            f.write("{ invalid json content")
        
        db_path = temp_dir / "recovery.sqlite"
        
        # Import should partially succeed
        with patch('sys.argv', [
            'eduasr.cli', 'import',
            '--transcripts-dir', str(temp_dir),
            '--db', str(db_path)
        ]):
            result = main()
            assert result == 0  # Should complete despite errors
        
        # Check that the good transcript was imported
        with TranscriptDB(str(db_path)) as db:
            transcripts = db.list_transcripts()
            assert len(transcripts) == 1
            assert transcripts[0]['filename'] == 'good'
    
    def test_database_consistency_after_updates(self, temp_dir, sample_transcript_json):
        """Test database consistency after multiple import operations."""
        json_file = temp_dir / "consistency-test.json"
        db_path = temp_dir / "consistency.sqlite"
        
        # First import
        with open(json_file, 'w') as f:
            json.dump(sample_transcript_json, f)
        
        with patch('sys.argv', [
            'eduasr.cli', 'import',
            '--transcripts-dir', str(temp_dir),
            '--db', str(db_path)
        ]):
            result = main()
            assert result == 0
        
        # Modify transcript and re-import with force
        sample_transcript_json['segments'].append({
            'start': 10.0,
            'end': 12.0,
            'text': 'Additional content added.',
            'speaker': 'SPEAKER_02',
            'confidence': 0.85
        })
        
        with open(json_file, 'w') as f:
            json.dump(sample_transcript_json, f)
        
        with patch('sys.argv', [
            'eduasr.cli', 'import',
            '--transcripts-dir', str(temp_dir),
            '--db', str(db_path),
            '--force'
        ]):
            result = main()
            assert result == 0
        
        # Verify database consistency
        with TranscriptDB(str(db_path)) as db:
            # Should still have only one transcript
            transcripts = db.list_transcripts()
            assert len(transcripts) == 1
            
            # But should have updated segment count
            assert transcripts[0]['segment_count'] == 5
            
            # Search should find new content
            results = db.search('Additional content')
            assert len(results) == 1


@pytest.mark.integration 
class TestCLIIntegrationEdgeCases:
    """Test CLI integration with edge cases and error conditions."""
    
    def test_cli_help_commands_integration(self):
        """Test that all CLI help commands work without errors."""
        commands = ['transcribe', 'import', 'search', 'kwic', 'list', 'stats']
        
        for cmd in commands:
            with patch('sys.argv', ['eduasr.cli', cmd, '--help']):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                # Help commands should exit with code 0
                assert exc_info.value.code == 0
    
    def test_cli_with_nonexistent_database(self, temp_dir):
        """Test CLI behavior with nonexistent database files."""
        nonexistent_db = temp_dir / "nonexistent.sqlite"
        
        # Search on nonexistent database should handle gracefully
        with patch('sys.argv', [
            'eduasr.cli', 'search',
            '--db', str(nonexistent_db),
            '--query', 'test'
        ]):
            # Should create database and return empty results
            result = main()
            assert result == 0
            
            # Database should be created
            assert nonexistent_db.exists()
    
    def test_cli_with_empty_database(self, temp_dir):
        """Test CLI behavior with empty database."""
        db_path = temp_dir / "empty.sqlite"
        
        # Create empty database
        with TranscriptDB(str(db_path)) as db:
            pass  # Just create tables
        
        # Search empty database
        with patch('sys.argv', [
            'eduasr.cli', 'search',
            '--db', str(db_path),
            '--query', 'anything'
        ]):
            with patch('eduasr.cli.print_search_results') as mock_print:
                result = main()
                assert result == 0
                
                # Should get empty results
                call_args = mock_print.call_args[0]
                results = call_args[0]
                assert len(results) == 0


@pytest.mark.integration
@pytest.mark.slow
class TestLargeDatasetHandling:
    """Test handling of larger datasets (marked as slow tests)."""
    
    def test_large_transcript_import(self, temp_dir):
        """Test importing a large number of transcript files."""
        db_path = temp_dir / "large.sqlite"
        
        # Create multiple transcript files
        for i in range(10):  # Reduced from 100 for faster testing
            transcript = {
                'segments': [
                    {
                        'start': j * 2.0,
                        'end': (j + 1) * 2.0,
                        'text': f'This is segment {j} of transcript {i}.',
                        'speaker': f'SPEAKER_{j % 3}',
                        'confidence': 0.9
                    }
                    for j in range(5)  # 5 segments per transcript
                ]
            }
            
            json_file = temp_dir / f"transcript_{i:03d}.json"
            with open(json_file, 'w') as f:
                json.dump(transcript, f)
        
        # Import all transcripts
        with patch('sys.argv', [
            'eduasr.cli', 'import',
            '--transcripts-dir', str(temp_dir),
            '--db', str(db_path)
        ]):
            result = main()
            assert result == 0
        
        # Verify all were imported
        with TranscriptDB(str(db_path)) as db:
            stats = db.get_transcript_stats()
            assert stats['transcript_count'] == 10
            assert stats['segment_count'] == 50  # 10 transcripts * 5 segments
        
        # Test search performance
        with patch('sys.argv', [
            'eduasr.cli', 'search',
            '--db', str(db_path),
            '--query', 'segment',
            '--limit', '20'
        ]):
            with patch('eduasr.cli.print_search_results') as mock_print:
                result = main()
                assert result == 0
                
                call_args = mock_print.call_args[0]
                results = call_args[0]
                assert len(results) == 20  # Should be limited to 20
