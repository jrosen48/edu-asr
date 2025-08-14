"""Tests for CLI module."""

import pytest
import sys
from unittest.mock import patch, Mock, call
from pathlib import Path
import argparse

from eduasr.cli import create_parser, main


class TestCLIParser:
    """Test CLI argument parsing."""
    
    def test_create_parser_structure(self):
        """Test that parser is created with correct structure."""
        parser = create_parser()
        
        assert isinstance(parser, argparse.ArgumentParser)
        
        # Test help output includes all subcommands
        help_text = parser.format_help()
        expected_commands = ['transcribe', 'import', 'search', 'kwic', 'list', 'stats']
        
        for cmd in expected_commands:
            assert cmd in help_text
    
    def test_transcribe_command_parsing(self):
        """Test transcribe command argument parsing."""
        parser = create_parser()
        
        # Test minimal required args
        args = parser.parse_args(['transcribe', '--output_dir', 'out'])
        assert args.command == 'transcribe'
        assert args.output_dir == 'out'
        
        # Test full args
        args = parser.parse_args([
            'transcribe',
            '--rclone-remote', 'myremote',
            '--remote-path', '/path/to/files', 
            '--input_dir', '/local/input',
            '--scratch-dir', '/scratch',
            '--include-ext', '.mp4,.wav',
            '--max-files', '50',
            '--output_dir', 'out',
            '--config', 'config.yaml',
            '--model', 'medium.en',
            '--force',
            '--min-free-gb', '10.5',
            '--wait-if-low-disk',
            '--check-interval-s', '30',
            '--max-wait-min', '60',
            '--run-log', 'log.csv'
        ])
        
        assert args.command == 'transcribe'
        assert args.rclone_remote == 'myremote'
        assert args.remote_path == '/path/to/files'
        assert args.input_dir == '/local/input'
        assert args.scratch_dir == '/scratch'
        assert args.include_ext == '.mp4,.wav'
        assert args.max_files == 50
        assert args.output_dir == 'out'
        assert args.config == 'config.yaml'
        assert args.model == 'medium.en'
        assert args.force is True
        assert args.min_free_gb == 10.5
        assert args.wait_if_low_disk is True
        assert args.check_interval_s == 30
        assert args.max_wait_min == 60
        assert args.run_log == 'log.csv'
    
    def test_import_command_parsing(self):
        """Test import command argument parsing."""
        parser = create_parser()
        
        args = parser.parse_args([
            'import',
            '--transcripts-dir', 'transcripts',
            '--db', 'database.sqlite',
            '--force'
        ])
        
        assert args.command == 'import'
        assert args.transcripts_dir == 'transcripts'
        assert args.db == 'database.sqlite'
        assert args.force is True
    
    def test_search_command_parsing(self):
        """Test search command argument parsing."""
        parser = create_parser()
        
        args = parser.parse_args([
            'search',
            '--db', 'database.sqlite',
            '--query', 'test query',
            '--limit', '25'
        ])
        
        assert args.command == 'search'
        assert args.db == 'database.sqlite'
        assert args.query == 'test query'
        assert args.limit == 25
    
    def test_kwic_command_parsing(self):
        """Test KWIC command argument parsing."""
        parser = create_parser()
        
        args = parser.parse_args([
            'kwic',
            '--db', 'database.sqlite',
            '--query', 'keyword',
            '--context', '15',
            '--limit', '20'
        ])
        
        assert args.command == 'kwic'
        assert args.db == 'database.sqlite'
        assert args.query == 'keyword'
        assert args.context == 15
        assert args.limit == 20
    
    def test_list_command_parsing(self):
        """Test list command argument parsing."""
        parser = create_parser()
        
        args = parser.parse_args([
            'list',
            '--db', 'database.sqlite',
            '--limit', '30'
        ])
        
        assert args.command == 'list'
        assert args.db == 'database.sqlite'
        assert args.limit == 30
    
    def test_stats_command_parsing(self):
        """Test stats command argument parsing."""
        parser = create_parser()
        
        args = parser.parse_args([
            'stats',
            '--db', 'database.sqlite'
        ])
        
        assert args.command == 'stats'
        assert args.db == 'database.sqlite'
    
    def test_required_arguments_validation(self):
        """Test that required arguments are enforced."""
        parser = create_parser()
        
        # Test missing command
        with pytest.raises(SystemExit):
            parser.parse_args([])
        
        # Test missing required args for transcribe
        with pytest.raises(SystemExit):
            parser.parse_args(['transcribe'])
        
        # Test missing required args for import
        with pytest.raises(SystemExit):
            parser.parse_args(['import', '--transcripts-dir', 'dir'])
        
        # Test missing required args for search
        with pytest.raises(SystemExit):
            parser.parse_args(['search', '--db', 'db.sqlite'])


class TestCLIMain:
    """Test CLI main function execution."""
    
    @patch('eduasr.cli.transcribe_batch')
    def test_transcribe_command_execution(self, mock_transcribe_batch):
        """Test transcribe command calls transcribe_batch.main()."""
        mock_transcribe_batch.main.return_value = 0
        
        test_args = [
            'transcribe',
            '--output_dir', 'out',
            '--model', 'tiny'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            result = main()
        
        assert result == 0
        mock_transcribe_batch.main.assert_called_once()
    
    @patch('eduasr.cli.TranscriptDB')
    def test_import_command_execution(self, mock_db_class):
        """Test import command execution."""
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=None)
        mock_db.import_transcript_files.return_value = {
            'imported': 5,
            'updated': 2,
            'skipped': 1,
            'errors': 0
        }
        mock_db_class.return_value = mock_db
        
        test_args = [
            'import',
            '--transcripts-dir', 'transcripts',
            '--db', 'test.sqlite'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            result = main()
        
        assert result == 0
        mock_db_class.assert_called_once_with('test.sqlite')
        mock_db.import_transcript_files.assert_called_once_with('transcripts', False)
    
    @patch('eduasr.cli.TranscriptDB')
    @patch('eduasr.cli.print_search_results')
    def test_search_command_execution(self, mock_print_results, mock_db_class):
        """Test search command execution."""
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=None)
        mock_db.search.return_value = [{'text': 'test result'}]
        mock_db_class.return_value = mock_db
        
        test_args = [
            'search',
            '--db', 'test.sqlite',
            '--query', 'test query',
            '--limit', '10'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            result = main()
        
        assert result == 0
        mock_db_class.assert_called_once_with('test.sqlite')
        mock_db.search.assert_called_once_with('test query', 10)
        mock_print_results.assert_called_once()
    
    @patch('eduasr.cli.TranscriptDB')
    @patch('eduasr.cli.print_kwic_results')
    def test_kwic_command_execution(self, mock_print_kwic, mock_db_class):
        """Test KWIC command execution."""
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=None)
        mock_db.kwic.return_value = [{'keyword': 'test'}]
        mock_db_class.return_value = mock_db
        
        test_args = [
            'kwic',
            '--db', 'test.sqlite',
            '--query', 'keyword',
            '--context', '5',
            '--limit', '15'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            result = main()
        
        assert result == 0
        mock_db_class.assert_called_once_with('test.sqlite')
        mock_db.kwic.assert_called_once_with('keyword', 5, 15)
        mock_print_kwic.assert_called_once()
    
    @patch('eduasr.cli.TranscriptDB')
    @patch('eduasr.cli.format_time')
    def test_list_command_execution(self, mock_format_time, mock_db_class):
        """Test list command execution."""
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=None)
        mock_db.list_transcripts.return_value = [
            {
                'title': 'Test Transcript',
                'filename': 'test.json',
                'duration_seconds': 120.0,
                'segment_count': 10,
                'speaker_count': 2,
                'created_at': '2023-01-01 12:00:00'
            }
        ]
        mock_db_class.return_value = mock_db
        mock_format_time.return_value = "02:00"
        
        test_args = [
            'list',
            '--db', 'test.sqlite',
            '--limit', '25'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            result = main()
        
        assert result == 0
        mock_db_class.assert_called_once_with('test.sqlite')
        mock_db.list_transcripts.assert_called_once_with(25)
        mock_format_time.assert_called_once_with(120.0)
    
    @patch('eduasr.cli.TranscriptDB')
    @patch('eduasr.cli.format_time')
    def test_stats_command_execution(self, mock_format_time, mock_db_class):
        """Test stats command execution."""
        mock_db = Mock()
        mock_db.__enter__ = Mock(return_value=mock_db)
        mock_db.__exit__ = Mock(return_value=None)
        mock_db.get_transcript_stats.return_value = {
            'transcript_count': 10,
            'segment_count': 500,
            'total_duration_hours': 5.5,
            'longest_transcripts': [
                {'filename': 'long.json', 'duration_seconds': 3600}
            ]
        }
        mock_db_class.return_value = mock_db
        mock_format_time.return_value = "01:00:00"
        
        test_args = [
            'stats',
            '--db', 'test.sqlite'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            result = main()
        
        assert result == 0
        mock_db_class.assert_called_once_with('test.sqlite')
        mock_db.get_transcript_stats.assert_called_once()
        mock_format_time.assert_called_once_with(3600)


class TestCLIIntegration:
    """Integration tests for CLI functionality."""
    
    def test_help_commands(self):
        """Test that help commands work for all subcommands."""
        parser = create_parser()
        
        # Test main help
        help_text = parser.format_help()
        assert 'EDU ASR unified command-line interface' in help_text
        
        # Test subcommand help parsing doesn't crash
        subcommands = ['transcribe', 'import', 'search', 'kwic', 'list', 'stats']
        
        for cmd in subcommands:
            try:
                parser.parse_args([cmd, '--help'])
            except SystemExit:
                # Help commands exit with code 0, which is expected
                pass
    
    @patch('eduasr.cli.transcribe_batch')
    def test_sys_argv_restoration(self, mock_transcribe_batch):
        """Test that sys.argv is properly restored after transcribe command."""
        original_argv = sys.argv.copy()
        mock_transcribe_batch.main.return_value = 0
        
        test_args = [
            'transcribe',
            '--output_dir', 'out'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            main()
        
        # sys.argv should be restored to original state
        assert sys.argv == original_argv
    
    def test_invalid_command_handling(self):
        """Test handling of invalid commands."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(['invalid_command'])
    
    def test_model_choices_validation(self):
        """Test that model choices are properly validated."""
        parser = create_parser()
        
        # Valid model
        args = parser.parse_args([
            'transcribe',
            '--output_dir', 'out',
            '--model', 'medium.en'
        ])
        assert args.model == 'medium.en'
        
        # Invalid model should raise SystemExit
        with pytest.raises(SystemExit):
            parser.parse_args([
                'transcribe',
                '--output_dir', 'out',
                '--model', 'invalid_model'
            ])


class TestCLIErrorHandling:
    """Test CLI error handling scenarios."""
    
    @patch('eduasr.cli.TranscriptDB')
    def test_database_error_handling(self, mock_db_class):
        """Test handling of database connection errors."""
        mock_db_class.side_effect = Exception("Database connection failed")
        
        test_args = [
            'import',
            '--transcripts-dir', 'transcripts',
            '--db', 'nonexistent.sqlite'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            # Should not crash, but may return non-zero exit code
            with pytest.raises(Exception):
                main()
    
    @patch('eduasr.cli.transcribe_batch')
    def test_transcribe_batch_error_handling(self, mock_transcribe_batch):
        """Test handling of transcription errors."""
        mock_transcribe_batch.main.side_effect = Exception("Transcription failed")
        
        test_args = [
            'transcribe',
            '--output_dir', 'out'
        ]
        
        with patch('sys.argv', ['eduasr.cli'] + test_args):
            with pytest.raises(Exception):
                main()
    
    def test_type_conversion_errors(self):
        """Test handling of type conversion errors in arguments."""
        parser = create_parser()
        
        # Invalid integer
        with pytest.raises(SystemExit):
            parser.parse_args([
                'transcribe',
                '--output_dir', 'out',
                '--max-files', 'not_a_number'
            ])
        
        # Invalid float
        with pytest.raises(SystemExit):
            parser.parse_args([
                'transcribe',
                '--output_dir', 'out',
                '--min-free-gb', 'not_a_float'
            ])
