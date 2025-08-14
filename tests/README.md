# EDU ASR Test Suite

Comprehensive unit and integration tests for the EDU ASR toolkit.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Pytest configuration and fixtures
├── test_db.py               # Database module tests
├── test_cli.py              # CLI module tests  
├── test_transcribe_batch.py # Transcription utilities tests
├── test_integration.py      # End-to-end integration tests
└── README.md               # This file
```

## Running Tests

### Quick Setup

First, install test dependencies:

```bash
# Activate your virtual environment
source .venv/bin/activate

# Install pytest (if not already installed)
pip install pytest pytest-cov
```

### Test Commands

**Run all tests:**
```bash
python -m pytest tests/
```

**Run with verbose output:**
```bash
python -m pytest tests/ -v
```

**Run specific test modules:**
```bash
# Database tests only
python -m pytest tests/test_db.py -v

# CLI tests only  
python -m pytest tests/test_cli.py -v

# Integration tests only
python -m pytest tests/test_integration.py -v
```

**Run tests by category:**
```bash
# Unit tests only (fast)
python -m pytest tests/ -m "not integration and not slow" -v

# Integration tests only
python -m pytest tests/ -m "integration" -v

# Skip slow tests
python -m pytest tests/ -m "not slow" -v
```

**Run with coverage report:**
```bash
python -m pytest tests/ --cov=eduasr --cov-report=html --cov-report=term
```

### Test Runner Script

Use the included test runner for common scenarios:

```bash
# Run all tests
python run_tests.py

# Run only unit tests (fast)
python run_tests.py --type unit -v

# Run with coverage
python run_tests.py --coverage -v

# Run integration tests
python run_tests.py --type integration -v
```

### Simple Verification

For quick verification without pytest:

```bash
python test_simple.py
```

## Test Categories

### Unit Tests

Test individual functions and classes in isolation:

- **Database operations** (import, search, KWIC)
- **CLI argument parsing**
- **File utilities** (finding, processing, cleanup)
- **Time formatting** and output writers
- **Configuration loading**

### Integration Tests

Test complete workflows:

- **Import → Search workflow**
- **Transcribe → Import → Search** (with mocked transcription)
- **Error recovery** and partial failures
- **Database consistency** after updates
- **Large dataset handling**

### Test Fixtures

Key fixtures available in `conftest.py`:

- `temp_dir` - Temporary directory for test files
- `sample_transcript_json` - Sample WhisperX transcript data
- `sample_transcript_files` - Complete set of transcript files (JSON, SRT, VTT, TXT)
- `test_db` - Pre-populated test database
- `mock_whisperx` - Mocked WhisperX for transcription tests
- `sample_config` - Sample configuration dictionary

## Test Coverage

The test suite covers:

### Database Module (`test_db.py`)
- ✅ Database initialization and table creation
- ✅ File hash calculation
- ✅ Title generation from filenames
- ✅ Single transcript import
- ✅ Batch transcript import
- ✅ Full-text search functionality
- ✅ KWIC (keyword in context) search
- ✅ Database statistics
- ✅ Transcript listing
- ✅ Error handling and edge cases

### CLI Module (`test_cli.py`)
- ✅ Argument parser creation
- ✅ All subcommand parsing (transcribe, import, search, kwic, list, stats)
- ✅ Required argument validation
- ✅ Command execution with mocked dependencies
- ✅ Help command functionality
- ✅ Error handling scenarios
- ✅ Type validation

### Transcription Module (`test_transcribe_batch.py`)
- ✅ Configuration loading (with/without YAML)
- ✅ Disk space utilities
- ✅ Remote file operations (rclone mocking)
- ✅ Local file finding (case-insensitive)
- ✅ Processing status tracking
- ✅ Time formatting (SRT/VTT)
- ✅ Output file writers
- ✅ File cleanup utilities
- ✅ Main function workflow (mocked)

### Integration Tests (`test_integration.py`)
- ✅ Complete import → search workflow
- ✅ Transcribe → import → search workflow (mocked)
- ✅ Error recovery from partial failures
- ✅ Database consistency after updates
- ✅ CLI help command integration
- ✅ Empty/nonexistent database handling
- ✅ Large dataset handling (marked as slow)

## Mock Strategy

Tests use comprehensive mocking to avoid external dependencies:

- **WhisperX** - Mocked transcription models and functions
- **rclone** - Mocked subprocess calls for remote operations  
- **File I/O** - Temporary directories and mock file operations
- **Network/Remote** - No actual remote calls made
- **Time operations** - Controlled timing for disk space tests

## Test Markers

Tests are marked for selective execution:

- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Tests that take longer to run
- `@pytest.mark.unit` - Unit tests (default)

## Continuous Integration

Tests are designed to run in CI environments:

- No external network dependencies
- No actual file downloads
- Mocked transcription models
- Deterministic outcomes
- Fast execution (except slow-marked tests)

## Writing New Tests

### Guidelines

1. **Use descriptive test names** that explain what is being tested
2. **Mock external dependencies** (WhisperX, rclone, file I/O)
3. **Use appropriate fixtures** from `conftest.py`
4. **Test both success and failure cases**
5. **Add appropriate markers** for test categorization
6. **Keep tests isolated** - no dependencies between tests
7. **Use temporary directories** for file operations

### Example Test Structure

```python
class TestNewFeature:
    """Test new feature functionality."""
    
    def test_feature_success_case(self, temp_dir):
        """Test successful feature operation."""
        # Arrange
        # Act  
        # Assert
        
    def test_feature_error_handling(self):
        """Test feature error handling."""
        # Test error conditions
        
    @pytest.mark.integration
    def test_feature_integration(self, test_db):
        """Test feature in integrated workflow."""
        # Integration test
```

## Troubleshooting Tests

### Common Issues

**Import errors:**
```bash
# Make sure you're in the project root
cd /path/to/edu_asr

# Check Python path
python -c "import sys; print(sys.path)"
```

**Missing pytest:**
```bash
pip install pytest pytest-cov
```

**Database errors:**
```bash
# Check that temp directories are writable
# Ensure no SQLite files are locked
```

**Mock failures:**
```bash
# Check that mocks match actual function signatures
# Verify mock return values match expected types
```

### Debug Mode

Run tests with extra debugging:

```bash
# Show print statements
python -m pytest tests/ -s

# Show detailed traceback
python -m pytest tests/ --tb=long

# Stop on first failure
python -m pytest tests/ -x
```
