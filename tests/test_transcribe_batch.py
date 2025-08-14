"""Tests for transcribe_batch module."""

import pytest
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, Mock, mock_open, call
import tempfile

from eduasr.transcribe_batch import (
    load_config, get_disk_free_gb, wait_for_disk_space,
    list_remote_files, sync_single_file, find_local_files,
    is_already_processed, is_already_processed_remote, mark_as_processed,
    cleanup_file, format_time, format_time_vtt, write_srt, write_vtt, write_txt
)


class TestConfigLoading:
    """Test configuration loading functionality."""
    
    @patch('builtins.open', mock_open(read_data='model_size: medium.en\nlanguage: en\ndevice: cpu'))
    @patch('eduasr.transcribe_batch.yaml.safe_load')
    def test_load_config_success(self, mock_yaml_load):
        """Test successful config loading."""
        mock_yaml_load.return_value = {
            'model_size': 'medium.en',
            'language': 'en',
            'device': 'cpu'
        }
        
        config = load_config('config.yaml')
        
        assert config['model_size'] == 'medium.en'
        assert config['language'] == 'en'
        assert config['device'] == 'cpu'
        mock_yaml_load.assert_called_once()
    
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_config_file_not_found(self, mock_open):
        """Test config loading when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_config('nonexistent.yaml')
    
    @patch('eduasr.transcribe_batch.yaml', None)  # Simulate missing yaml module
    def test_load_config_no_yaml_module(self):
        """Test config loading when yaml module is not available."""
        config = load_config('config.yaml')
        assert config == {}


class TestDiskSpaceUtilities:
    """Test disk space management utilities."""
    
    @patch('eduasr.transcribe_batch.shutil.disk_usage')
    def test_get_disk_free_gb(self, mock_disk_usage):
        """Test disk space calculation."""
        # Mock disk usage: total=100GB, used=30GB, free=70GB
        mock_disk_usage.return_value = Mock(free=70 * 1024**3)
        
        free_gb = get_disk_free_gb('/some/path')
        assert free_gb == 70.0
        mock_disk_usage.assert_called_once_with('/some/path')
    
    @patch('eduasr.transcribe_batch.get_disk_free_gb')
    @patch('eduasr.transcribe_batch.time.sleep')
    def test_wait_for_disk_space_success(self, mock_sleep, mock_get_disk_free):
        """Test waiting for disk space when space becomes available."""
        # First call returns insufficient space, second call returns sufficient space
        mock_get_disk_free.side_effect = [5.0, 15.0]
        
        # Should not raise exception
        wait_for_disk_space('/path', min_free_gb=10.0, check_interval_s=1, max_wait_min=1)
        
        assert mock_get_disk_free.call_count == 2
        mock_sleep.assert_called_once_with(1)
    
    @patch('eduasr.transcribe_batch.get_disk_free_gb')
    @patch('eduasr.transcribe_batch.time.sleep')
    def test_wait_for_disk_space_timeout(self, mock_sleep, mock_get_disk_free):
        """Test waiting for disk space timeout."""
        # Always return insufficient space
        mock_get_disk_free.return_value = 5.0
        
        with pytest.raises(RuntimeError, match="Insufficient disk space"):
            wait_for_disk_space('/path', min_free_gb=10.0, check_interval_s=1, max_wait_min=1/60)  # 1 second max
    
    @patch('eduasr.transcribe_batch.get_disk_free_gb')
    def test_wait_for_disk_space_immediate_success(self, mock_get_disk_free):
        """Test when sufficient disk space is immediately available."""
        mock_get_disk_free.return_value = 15.0
        
        # Should return immediately without waiting
        wait_for_disk_space('/path', min_free_gb=10.0, check_interval_s=30, max_wait_min=60)
        
        mock_get_disk_free.assert_called_once()


class TestRemoteFileOperations:
    """Test remote file operations with rclone."""
    
    @patch('eduasr.transcribe_batch.subprocess.run')
    def test_list_remote_files_success(self, mock_run):
        """Test successful remote file listing."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.mp4\nfile2.wav\nfile3.mov\n"
        mock_run.return_value = mock_result
        
        files = list_remote_files('myremote', '/path', '.mp4,.wav,.mov')
        
        assert files == ['file1.mp4', 'file2.wav', 'file3.mov']
        mock_run.assert_called_once()
        
        # Check that rclone command was constructed correctly
        call_args = mock_run.call_args[0][0]
        assert 'rclone' in call_args
        assert 'lsf' in call_args
        assert 'myremote:/path' in call_args
        assert '--recursive' in call_args
    
    @patch('eduasr.transcribe_batch.subprocess.run')
    def test_list_remote_files_failure(self, mock_run):
        """Test remote file listing failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "rclone error message"
        mock_run.return_value = mock_result
        
        files = list_remote_files('myremote', '/path', '.mp4')
        
        assert files == []
        mock_run.assert_called_once()
    
    @patch('eduasr.transcribe_batch.subprocess.run')
    def test_sync_single_file_success(self, mock_run):
        """Test successful single file sync."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = sync_single_file('myremote', '/remote/file.mp4', tmpdir)
            
            expected_path = str(Path(tmpdir) / 'file.mp4')
            assert result == expected_path
            mock_run.assert_called_once()
            
            # Check rclone copyto command
            call_args = mock_run.call_args[0][0]
            assert 'rclone' in call_args
            assert 'copyto' in call_args
            assert 'myremote:/remote/file.mp4' in call_args
            assert expected_path in call_args
    
    @patch('eduasr.transcribe_batch.subprocess.run')
    def test_sync_single_file_failure(self, mock_run):
        """Test single file sync failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "sync failed"
        mock_run.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = sync_single_file('myremote', '/remote/file.mp4', tmpdir)
            assert result is None


class TestLocalFileOperations:
    """Test local file operations."""
    
    def test_find_local_files(self, temp_dir):
        """Test finding local files with extension matching."""
        # Create test files with various extensions
        test_files = [
            'video1.mp4',
            'video2.MP4',  # Different case
            'audio1.wav',
            'audio2.WAV',  # Different case
            'document.txt',  # Should not match
            'video3.mov'
        ]
        
        for filename in test_files:
            (temp_dir / filename).touch()
        
        # Test case-insensitive extension matching
        found_files = find_local_files(str(temp_dir), '.mp4,.wav')
        found_names = [Path(f).name for f in found_files]
        
        # Should find all video and audio files regardless of case
        assert 'video1.mp4' in found_names
        assert 'video2.MP4' in found_names
        assert 'audio1.wav' in found_names
        assert 'audio2.WAV' in found_names
        assert 'document.txt' not in found_names
        assert 'video3.mov' not in found_names
    
    def test_find_local_files_recursive(self, temp_dir):
        """Test recursive file finding."""
        # Create nested directory structure
        subdir = temp_dir / 'subdir'
        subdir.mkdir()
        
        (temp_dir / 'root.mp4').touch()
        (subdir / 'nested.mp4').touch()
        
        found_files = find_local_files(str(temp_dir), '.mp4')
        found_names = [Path(f).name for f in found_files]
        
        assert 'root.mp4' in found_names
        assert 'nested.mp4' in found_names
    
    def test_is_already_processed(self, temp_dir):
        """Test checking if file is already processed."""
        # Create test audio file and done file
        audio_file = temp_dir / 'test.mp4'
        audio_file.touch()
        
        done_file = temp_dir / 'test.done'
        done_file.touch()
        
        assert is_already_processed(str(audio_file), str(temp_dir)) is True
        
        # Test without done file
        audio_file2 = temp_dir / 'test2.mp4'
        audio_file2.touch()
        
        assert is_already_processed(str(audio_file2), str(temp_dir)) is False
    
    def test_is_already_processed_remote(self, temp_dir):
        """Test checking if remote file is already processed."""
        # Create done file
        done_file = temp_dir / 'remote-file.done'
        done_file.touch()
        
        assert is_already_processed_remote('remote-file.mp4', str(temp_dir)) is True
        assert is_already_processed_remote('other-file.mp4', str(temp_dir)) is False
    
    def test_mark_as_processed(self, temp_dir):
        """Test marking file as processed."""
        audio_file = temp_dir / 'test.mp4'
        audio_file.touch()
        
        mark_as_processed(str(audio_file), str(temp_dir))
        
        done_file = temp_dir / 'test.done'
        assert done_file.exists()
    
    @patch('eduasr.transcribe_batch.os.remove')
    def test_cleanup_file_success(self, mock_remove):
        """Test successful file cleanup."""
        cleanup_file('/path/to/file.mp4')
        mock_remove.assert_called_once_with('/path/to/file.mp4')
    
    @patch('eduasr.transcribe_batch.os.remove', side_effect=OSError("Permission denied"))
    def test_cleanup_file_failure(self, mock_remove):
        """Test file cleanup failure."""
        # Should not raise exception, just print warning
        cleanup_file('/path/to/file.mp4')
        mock_remove.assert_called_once_with('/path/to/file.mp4')


class TestTimeFormatting:
    """Test time formatting utilities."""
    
    def test_format_time(self):
        """Test SRT time formatting."""
        assert format_time(0) == "00:00:00,000"
        assert format_time(1.5) == "00:00:01,500"
        assert format_time(61.25) == "00:01:01,250"
        assert format_time(3661.125) == "01:01:01,125"
    
    def test_format_time_vtt(self):
        """Test VTT time formatting."""
        assert format_time_vtt(0) == "00:00:00.000"
        assert format_time_vtt(1.5) == "00:00:01.500"
        assert format_time_vtt(61.25) == "00:01:01.250"
        assert format_time_vtt(3661.125) == "01:01:01.125"


class TestOutputWriters:
    """Test output file writers."""
    
    def test_write_srt(self, temp_dir):
        """Test SRT file writing."""
        result = {
            'segments': [
                {'start': 0.0, 'end': 2.5, 'text': 'Hello world.'},
                {'start': 2.5, 'end': 5.0, 'text': 'How are you?'}
            ]
        }
        
        srt_file = temp_dir / 'test.srt'
        write_srt(result, srt_file)
        
        content = srt_file.read_text()
        assert '1\n00:00:00,000 --> 00:00:02,500\nHello world.\n\n' in content
        assert '2\n00:00:02,500 --> 00:00:05,000\nHow are you?\n\n' in content
    
    def test_write_vtt(self, temp_dir):
        """Test VTT file writing."""
        result = {
            'segments': [
                {'start': 0.0, 'end': 2.5, 'text': 'Hello world.'},
                {'start': 2.5, 'end': 5.0, 'text': 'How are you?'}
            ]
        }
        
        vtt_file = temp_dir / 'test.vtt'
        write_vtt(result, vtt_file)
        
        content = vtt_file.read_text()
        assert content.startswith('WEBVTT\n\n')
        assert '00:00:00.000 --> 00:00:02.500\nHello world.\n\n' in content
        assert '00:00:02.500 --> 00:00:05.000\nHow are you?\n\n' in content
    
    def test_write_txt(self, temp_dir):
        """Test TXT file writing."""
        result = {
            'segments': [
                {'text': 'Hello world.'},
                {'text': 'How are you?'}
            ]
        }
        
        txt_file = temp_dir / 'test.txt'
        write_txt(result, txt_file)
        
        content = txt_file.read_text()
        assert 'Hello world. How are you? ' == content


class TestTranscriptionFunction:
    """Test main transcription function."""
    
    @patch('eduasr.transcribe_batch.json.dump')
    @patch('eduasr.transcribe_batch.write_srt')
    @patch('eduasr.transcribe_batch.write_vtt')
    @patch('eduasr.transcribe_batch.write_txt')
    def test_transcribe_file_output_formats(self, mock_write_txt, mock_write_vtt, 
                                          mock_write_srt, mock_json_dump, temp_dir, 
                                          mock_whisperx, sample_config):
        """Test that transcribe_file writes all output formats."""
        from eduasr.transcribe_batch import transcribe_file
        
        # Create a test audio file
        audio_file = temp_dir / 'test.wav'
        audio_file.touch()
        
        # Mock whisperx responses
        mock_result = {
            'segments': [
                {
                    'start': 0.0,
                    'end': 5.0,
                    'text': 'Test transcription',
                    'confidence': 0.95
                }
            ]
        }
        
        mock_model = Mock()
        mock_model.transcribe.return_value = mock_result
        
        # Call transcribe_file
        result = transcribe_file(str(audio_file), str(temp_dir), sample_config, mock_model)
        
        # Verify outputs were written
        mock_json_dump.assert_called_once()
        mock_write_srt.assert_called_once()
        mock_write_vtt.assert_called_once()
        mock_write_txt.assert_called_once()
        
        # Verify result structure
        assert result['file'] == str(audio_file)
        assert result['status'] == 'success'
        assert result['segments'] == 1


class TestMainFunctionMocking:
    """Test main function with mocked dependencies."""
    
    @patch('eduasr.transcribe_batch.load_config')
    @patch('eduasr.transcribe_batch.find_local_files')
    @patch('eduasr.transcribe_batch.is_already_processed')
    def test_main_local_files_workflow(self, mock_is_processed, mock_find_files, mock_load_config):
        """Test main function workflow with local files."""
        from eduasr.transcribe_batch import main
        
        # Mock configuration and file discovery
        mock_load_config.return_value = {'model_size': 'tiny', 'device': 'cpu'}
        mock_find_files.return_value = ['/path/file1.wav', '/path/file2.wav']
        mock_is_processed.return_value = False
        
        # Mock sys.argv for argument parsing
        test_args = [
            'transcribe_batch.py',
            '--input_dir', '/input',
            '--output_dir', '/output'
        ]
        
        with patch('sys.argv', test_args):
            with patch('eduasr.transcribe_batch.whisperx') as mock_whisperx:
                # Mock WhisperX imports to avoid ImportError
                mock_whisperx.load_model.return_value = Mock()
                
                with patch('eduasr.transcribe_batch.transcribe_file') as mock_transcribe:
                    mock_transcribe.return_value = {
                        'duration': 10.0,
                        'segments': 5,
                        'status': 'success'
                    }
                    
                    with patch('eduasr.transcribe_batch.mark_as_processed'):
                        result = main()
        
        assert result == 0  # Success exit code
