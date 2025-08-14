#!/usr/bin/env python3
"""Database module for transcript storage and full-text search."""

import json
import sqlite3
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib


class TranscriptDB:
    """SQLite database for storing and searching transcripts with FTS5."""
    
    def __init__(self, db_path: str):
        """Initialize database connection and create tables if needed."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        self.create_tables()
    
    def create_tables(self):
        """Create database tables and FTS5 index."""
        cursor = self.conn.cursor()
        
        # Main transcripts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                file_hash TEXT,
                title TEXT,
                duration_seconds REAL,
                segment_count INTEGER,
                speaker_count INTEGER,
                model_used TEXT,
                language TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_audio_path TEXT,
                transcript_json_path TEXT,
                transcript_srt_path TEXT,
                transcript_vtt_path TEXT,
                transcript_txt_path TEXT
            )
        """)
        
        # Segments table for individual transcript segments
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript_id INTEGER,
                segment_index INTEGER,
                start_time REAL,
                end_time REAL,
                speaker TEXT,
                text TEXT,
                confidence REAL,
                FOREIGN KEY (transcript_id) REFERENCES transcripts (id)
            )
        """)
        
        # FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
                text,
                speaker,
                filename,
                title,
                content='segments',
                content_rowid='id'
            )
        """)
        
        # Triggers to keep FTS5 in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
                INSERT INTO segments_fts(rowid, text, speaker, filename, title)
                SELECT new.id, new.text, new.speaker, 
                       (SELECT filename FROM transcripts WHERE id = new.transcript_id),
                       (SELECT title FROM transcripts WHERE id = new.transcript_id);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
                INSERT INTO segments_fts(segments_fts, rowid, text, speaker, filename, title)
                VALUES('delete', old.id, old.text, old.speaker, '', '');
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
                INSERT INTO segments_fts(segments_fts, rowid, text, speaker, filename, title)
                VALUES('delete', old.id, old.text, old.speaker, '', '');
                INSERT INTO segments_fts(rowid, text, speaker, filename, title)
                SELECT new.id, new.text, new.speaker,
                       (SELECT filename FROM transcripts WHERE id = new.transcript_id),
                       (SELECT title FROM transcripts WHERE id = new.transcript_id);
            END
        """)
        
        self.conn.commit()
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file for change detection."""
        hash_md5 = hashlib.md5()
        if file_path.exists():
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def import_transcript_files(self, transcripts_dir: str, force: bool = False) -> Dict[str, int]:
        """Import all transcript files from a directory."""
        transcripts_path = Path(transcripts_dir)
        stats = {"imported": 0, "updated": 0, "skipped": 0, "errors": 0}
        
        # Find all JSON transcript files
        json_files = list(transcripts_path.glob("*.json"))
        
        print(f"Found {len(json_files)} JSON transcript files")
        
        for json_file in json_files:
            try:
                result = self.import_single_transcript(json_file, transcripts_path, force)
                stats[result] += 1
                
                if result in ["imported", "updated"]:
                    print(f"✅ {result.title()}: {json_file.name}")
                elif result == "skipped":
                    print(f"⏭️  Skipped: {json_file.name} (already imported)")
                
            except Exception as e:
                print(f"❌ Error importing {json_file.name}: {e}")
                stats["errors"] += 1
        
        return stats
    
    def import_single_transcript(self, json_file: Path, base_dir: Path, force: bool = False) -> str:
        """Import a single transcript file. Returns 'imported', 'updated', or 'skipped'."""
        filename = json_file.stem
        
        # Check if already exists
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, file_hash FROM transcripts WHERE filename = ?", (filename,))
        existing = cursor.fetchone()
        
        # Calculate current file hash
        current_hash = self.calculate_file_hash(json_file)
        
        if existing and not force:
            if existing['file_hash'] == current_hash:
                return "skipped"
        
        # Load JSON data
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract metadata
        segments = data.get('segments', [])
        speakers = set()
        total_duration = 0
        
        for segment in segments:
            if 'speaker' in segment and segment['speaker']:
                speakers.add(segment['speaker'])
            if 'end' in segment:
                total_duration = max(total_duration, segment['end'])
        
        # Find related files
        srt_file = base_dir / f"{filename}.srt"
        vtt_file = base_dir / f"{filename}.vtt"
        txt_file = base_dir / f"{filename}.txt"
        
        # Generate a nice title from filename
        title = self.generate_title(filename)
        
        # Insert or update transcript record
        if existing:
            cursor.execute("""
                UPDATE transcripts SET
                    file_hash = ?, title = ?, duration_seconds = ?, segment_count = ?,
                    speaker_count = ?, updated_at = ?, transcript_json_path = ?,
                    transcript_srt_path = ?, transcript_vtt_path = ?, transcript_txt_path = ?
                WHERE id = ?
            """, (
                current_hash, title, total_duration, len(segments), len(speakers),
                datetime.now().isoformat(), str(json_file),
                str(srt_file) if srt_file.exists() else None,
                str(vtt_file) if vtt_file.exists() else None,
                str(txt_file) if txt_file.exists() else None,
                existing['id']
            ))
            transcript_id = existing['id']
            
            # Delete existing segments
            cursor.execute("DELETE FROM segments WHERE transcript_id = ?", (transcript_id,))
            result_type = "updated"
        else:
            cursor.execute("""
                INSERT INTO transcripts (
                    filename, file_hash, title, duration_seconds, segment_count,
                    speaker_count, transcript_json_path, transcript_srt_path,
                    transcript_vtt_path, transcript_txt_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename, current_hash, title, total_duration, len(segments),
                len(speakers), str(json_file),
                str(srt_file) if srt_file.exists() else None,
                str(vtt_file) if vtt_file.exists() else None,
                str(txt_file) if txt_file.exists() else None
            ))
            transcript_id = cursor.lastrowid
            result_type = "imported"
        
        # Insert segments
        for i, segment in enumerate(segments):
            cursor.execute("""
                INSERT INTO segments (
                    transcript_id, segment_index, start_time, end_time,
                    speaker, text, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                transcript_id, i,
                segment.get('start', 0),
                segment.get('end', 0),
                segment.get('speaker', ''),
                segment.get('text', ''),
                segment.get('confidence', 0)
            ))
        
        self.conn.commit()
        return result_type
    
    def generate_title(self, filename: str) -> str:
        """Generate a human-readable title from filename."""
        # Remove common prefixes and clean up
        title = filename
        
        # Handle date patterns like "2025-07-28-"
        title = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', title)
        
        # Replace hyphens and underscores with spaces
        title = title.replace('-', ' ').replace('_', ' ')
        
        # Capitalize words
        title = ' '.join(word.capitalize() for word in title.split())
        
        # Clean up common patterns
        title = re.sub(r'\b\d+\b$', '', title).strip()  # Remove trailing numbers
        title = re.sub(r'\s+', ' ', title)  # Multiple spaces to single
        
        return title or filename
    
    def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Full-text search across all transcripts."""
        cursor = self.conn.cursor()
        
        # Use FTS5 MATCH syntax - escape query for safety
        escaped_query = f'"{query}"' if ' ' in query else query
        
        cursor.execute("""
            SELECT 
                s.id, s.transcript_id, s.segment_index, s.start_time, s.end_time,
                s.speaker, s.text, s.confidence,
                t.filename, t.title, t.duration_seconds,
                snippet(segments_fts, 0, '<mark>', '</mark>', '...', 32) as snippet
            FROM segments_fts
            JOIN segments s ON s.text = segments_fts.text AND s.speaker = segments_fts.speaker
            JOIN transcripts t ON t.id = s.transcript_id AND t.filename = segments_fts.filename
            WHERE segments_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (escaped_query, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'segment_id': row['id'],
                'transcript_id': row['transcript_id'],
                'filename': row['filename'],
                'title': row['title'],
                'speaker': row['speaker'],
                'text': row['text'],
                'snippet': row['snippet'],
                'start_time': row['start_time'],
                'end_time': row['end_time'],
                'confidence': row['confidence'],
                'duration_seconds': row['duration_seconds']
            })
        
        return results
    
    def kwic(self, query: str, context_words: int = 10, limit: int = 50) -> List[Dict[str, Any]]:
        """Keyword in context search."""
        results = self.search(query, limit)
        
        # Enhance with better context
        for result in results:
            text = result['text']
            
            # Find query position (case-insensitive)
            query_pattern = re.compile(re.escape(query), re.IGNORECASE)
            match = query_pattern.search(text)
            
            if match:
                start, end = match.span()
                words = text.split()
                
                # Find word boundaries around the match
                char_to_word = {}
                char_pos = 0
                for word_idx, word in enumerate(words):
                    for _ in range(len(word)):
                        char_to_word[char_pos] = word_idx
                        char_pos += 1
                    char_pos += 1  # space
                
                start_word = char_to_word.get(start, 0)
                end_word = char_to_word.get(end, len(words) - 1)
                
                # Extract context
                context_start = max(0, start_word - context_words)
                context_end = min(len(words), end_word + context_words + 1)
                
                left_context = ' '.join(words[context_start:start_word])
                keyword = ' '.join(words[start_word:end_word + 1])
                right_context = ' '.join(words[end_word + 1:context_end])
                
                result['left_context'] = left_context
                result['keyword'] = keyword
                result['right_context'] = right_context
        
        return results
    
    def get_transcript_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM transcripts")
        transcript_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM segments")
        segment_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT SUM(duration_seconds) as total FROM transcripts")
        total_duration = cursor.fetchone()['total'] or 0
        
        cursor.execute("SELECT filename, duration_seconds FROM transcripts ORDER BY duration_seconds DESC LIMIT 5")
        longest = cursor.fetchall()
        
        return {
            'transcript_count': transcript_count,
            'segment_count': segment_count,
            'total_duration_seconds': total_duration,
            'total_duration_hours': total_duration / 3600,
            'longest_transcripts': [dict(row) for row in longest]
        }
    
    def list_transcripts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List all transcripts with metadata."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT filename, title, duration_seconds, segment_count, speaker_count,
                   created_at, updated_at
            FROM transcripts 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def print_search_results(results: List[Dict[str, Any]], query: str):
    """Pretty print search results."""
    if not results:
        print(f"No results found for '{query}'")
        return
    
    print(f"\n🔍 Found {len(results)} results for '{query}':\n")
    
    for i, result in enumerate(results, 1):
        print(f"[{i:2d}] {result['title']} ({result['filename']})")
        print(f"     Speaker: {result['speaker'] or 'Unknown'} | "
              f"Time: {format_time(result['start_time'])}-{format_time(result['end_time'])}")
        print(f"     {result['snippet'] or result['text'][:100]}...")
        print()


def print_kwic_results(results: List[Dict[str, Any]], query: str):
    """Pretty print KWIC results."""
    if not results:
        print(f"No results found for '{query}'")
        return
    
    print(f"\n🎯 KWIC results for '{query}':\n")
    
    for i, result in enumerate(results, 1):
        print(f"[{i:2d}] {result['title']} - {result['speaker'] or 'Unknown'} "
              f"@ {format_time(result['start_time'])}")
        
        if 'left_context' in result:
            print(f"     ...{result['left_context']} "
                  f"**{result['keyword']}** "
                  f"{result['right_context']}...")
        else:
            print(f"     {result['text'][:100]}...")
        print()
