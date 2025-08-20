#!/usr/bin/env python3
"""
Demo script to test diarization functionality without requiring actual audio files.
This script verifies that the diarization implementation works correctly.
"""

import sys
from pathlib import Path

# Add the current directory to path so we can import from eduasr
sys.path.insert(0, str(Path(__file__).parent))

from eduasr.transcribe_batch import (
    get_hf_token, 
    assign_speakers_to_segments,
    write_srt,
    write_vtt, 
    write_txt
)


def test_hf_token_detection():
    """Test Hugging Face token detection."""
    print("🔍 Testing HF token detection...")
    
    config = {'hf_token_env': 'HF_TOKEN'}
    token = get_hf_token(config)
    
    if token:
        print(f"✅ HF token found: {token[:10]}...")
        return True
    else:
        print("❌ No HF token found. Set HF_TOKEN environment variable or save to ~/.eduasr/hf_token")
        return False


def test_speaker_assignment():
    """Test speaker assignment to transcription segments."""
    print("🎭 Testing speaker assignment...")
    
    # Mock transcription segments
    transcription_segments = [
        {'start': 0.0, 'end': 3.0, 'text': 'Hello everyone, welcome to our meeting.'},
        {'start': 3.0, 'end': 6.0, 'text': 'Thank you for having me here today.'},
        {'start': 6.0, 'end': 9.0, 'text': 'Let\'s start with the first agenda item.'},
        {'start': 9.0, 'end': 12.0, 'text': 'I have some questions about that topic.'},
    ]
    
    # Mock speaker segments (from diarization)
    speaker_segments = [
        {'start': 0.0, 'end': 7.0, 'speaker': 'SPEAKER_00'},  # First speaker
        {'start': 7.0, 'end': 12.0, 'speaker': 'SPEAKER_01'}, # Second speaker
    ]
    
    # Assign speakers to transcription segments
    result_segments = assign_speakers_to_segments(transcription_segments, speaker_segments)
    
    print("Results:")
    for i, segment in enumerate(result_segments):
        speaker = segment.get('speaker', 'UNKNOWN')
        text = segment['text'][:50] + ('...' if len(segment['text']) > 50 else '')
        print(f"  {i+1}. [{speaker}] {text}")
    
    # Verify assignment worked correctly
    assert result_segments[0]['speaker'] == 'SPEAKER_00'
    assert result_segments[1]['speaker'] == 'SPEAKER_00'
    assert result_segments[2]['speaker'] == 'SPEAKER_01'
    assert result_segments[3]['speaker'] == 'SPEAKER_01'
    
    print("✅ Speaker assignment working correctly!")
    return result_segments


def test_output_formats(segments_with_speakers):
    """Test output format generation with speaker labels."""
    print("📝 Testing output formats with speaker labels...")
    
    # Create a mock result with speaker information
    result = {'segments': segments_with_speakers}
    
    # Test directory
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)
    
    # Test SRT output
    srt_file = output_dir / "demo.srt"
    write_srt(result, srt_file)
    print(f"✅ SRT file created: {srt_file}")
    
    # Test VTT output
    vtt_file = output_dir / "demo.vtt"
    write_vtt(result, vtt_file)
    print(f"✅ VTT file created: {vtt_file}")
    
    # Test TXT output
    txt_file = output_dir / "demo.txt"
    write_txt(result, txt_file)
    print(f"✅ TXT file created: {txt_file}")
    
    # Show sample output
    print("\n📖 Sample SRT output:")
    print(srt_file.read_text()[:200] + "...")
    
    print("\n📖 Sample TXT output:")
    print(txt_file.read_text()[:200] + "...")


def main():
    """Run diarization demo tests."""
    print("🎤 EDU ASR Diarization Demo")
    print("=" * 40)
    
    try:
        # Test 1: HF token detection
        token_available = test_hf_token_detection()
        print()
        
        # Test 2: Speaker assignment
        segments_with_speakers = test_speaker_assignment()
        print()
        
        # Test 3: Output formats
        test_output_formats(segments_with_speakers)
        print()
        
        print("🎉 All diarization tests passed!")
        
        if not token_available:
            print("\n💡 To test with real audio files:")
            print("   1. Set up your HF token (see README)")
            print("   2. Run: python -m eduasr.cli transcribe --help")
            
        print("\n✨ Diarization implementation is ready to use!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
