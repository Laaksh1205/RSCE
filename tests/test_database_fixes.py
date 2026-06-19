"""Unit tests for database bug fixes."""
import pytest
import tempfile
import os
from src.storage.database import get_connection, validate_pmids


def test_validate_pmids_valid():
    """Test PMID validation with valid inputs."""
    valid_pmids = ["12345678", "PMC1234567", "123-456-789"]
    validate_pmids(valid_pmids)  # Should not raise


def test_validate_pmids_invalid_characters():
    """Test PMID validation rejects invalid characters."""
    invalid_pmids = ["123;456", "123'456", "123\"456"]
    for pmid in invalid_pmids:
        with pytest.raises(ValueError, match="invalid characters"):
            validate_pmids([pmid])


def test_validate_pmids_empty():
    """Test PMID validation rejects empty strings."""
    with pytest.raises(ValueError, match="Invalid PMID"):
        validate_pmids([""])


def test_validate_pmids_none():
    """Test PMID validation rejects None values."""
    with pytest.raises(ValueError, match="Invalid PMID"):
        validate_pmids([None])


def test_get_connection_with_filename_only():
    """Test database connection with filename-only path (no directory)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = get_connection(db_path)
        assert conn is not None
        conn.close()
        # Verify database was created
        assert os.path.exists(db_path)


def test_get_connection_with_subdirectory():
    """Test database connection with subdirectory path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "subdir", "test.db")
        conn = get_connection(db_path)
        assert conn is not None
        conn.close()
        # Verify database and subdirectory were created
        assert os.path.exists(db_path)
