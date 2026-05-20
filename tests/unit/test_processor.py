"""Unit tests for FileProcessor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.processor import FileProcessor
from orchestrator.result import FileOutcome, FileStatus
from extract.hasher import Sha256Hasher
from upload.uploader import UploadResult, UploadStatus


def mock_download_success():
    return MagicMock(
        file_path=Path("/tmp/test.parquet"),
        hash_value="abc123",
        hash_type="sha256",
    )


def mock_download_forbidden():
    return None


def mock_upload_success():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SUCCESS,
        hash_value="abc123",
        hash_type="sha256",
    )


def mock_upload_error():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.ERROR,
        error_message="S3 connection refused",
    )


def mock_upload_skipped():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc123",
        hash_type="sha256",
    )


def test_processor_success():
    """Test successful download and upload."""
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=Sha256Hasher(),
    )

    with patch.object(processor, "_download", return_value=mock_download_success()):
        with patch.object(processor, "_upload", return_value=mock_upload_success()):
            Path("/tmp/test.parquet").write_bytes(b"test content")
            outcome = processor.process_file(
                url="http://example.com/test.parquet",
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )

    assert outcome.status == FileStatus.SUCCESS
    assert outcome.url == "http://example.com/test.parquet"
    assert outcome.download_result is not None
    assert outcome.upload_result is not None
    assert outcome.upload_result.status == UploadStatus.SUCCESS
    assert outcome.error_message == ""


def test_processor_download_forbidden():
    """Test download forbidden (returns None)."""
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=Sha256Hasher(),
    )

    with patch.object(processor, "_download", return_value=mock_download_forbidden()):
        outcome = processor.process_file(
            url="http://example.com/test.parquet",
            bucket_name="test-bucket",
            bucket_path_prefix="",
        )

    assert outcome.status == FileStatus.DOWNLOAD_FAILED
    assert outcome.download_result is None
    assert "forbidden or not found" in outcome.error_message


def test_processor_download_exception():
    """Test download raises exception."""
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=Sha256Hasher(),
    )

    with patch.object(processor, "_download", side_effect=RuntimeError("Connection timeout")):
        outcome = processor.process_file(
            url="http://example.com/test.parquet",
            bucket_name="test-bucket",
            bucket_path_prefix="",
        )

        assert outcome.status == FileStatus.DOWNLOAD_ERROR
        assert "Connection timeout" in outcome.error_message
    assert outcome.upload_result is None


def test_processor_upload_error():
    """Test upload fails with error."""
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=Sha256Hasher(),
    )

    with patch.object(processor, "_download", return_value=mock_download_success()):
        with patch.object(processor, "_upload", return_value=mock_upload_error()):
            Path("/tmp/test.parquet").write_bytes(b"test content")
            outcome = processor.process_file(
                url="http://example.com/test.parquet",
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )

    assert outcome.status == FileStatus.UPLOAD_FAILED
    assert outcome.download_result is not None
    assert outcome.upload_result is not None
    assert outcome.upload_result.status == UploadStatus.ERROR
    assert "S3 connection refused" in outcome.upload_result.error_message


def test_processor_upload_skipped():
    """Test upload is skipped (already exists)."""
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=Sha256Hasher(),
    )

    with patch.object(processor, "_download", return_value=mock_download_success()):
        with patch.object(processor, "_upload", return_value=mock_upload_skipped()):
            Path("/tmp/test.parquet").write_bytes(b"test content")
            outcome = processor.process_file(
                url="http://example.com/test.parquet",
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )

    assert outcome.status == FileStatus.SKIPPED
    assert outcome.download_result is not None
    assert outcome.upload_result is not None
    assert outcome.upload_result.status == UploadStatus.SKIPPED


def test_processor_bucket_path_prefix():
    """Test bucket path prefix is applied correctly."""
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=Sha256Hasher(),
    )

    with patch.object(processor, "_download", return_value=mock_download_success()):
        with patch.object(processor, "_upload") as mock_upload:
            mock_upload.return_value = mock_upload_success()
            Path("/tmp/test.parquet").write_bytes(b"test content")
            processor.process_file(
                url="http://example.com/yellow_tripdata_2024-01.parquet",
                bucket_name="test-bucket",
                bucket_path_prefix="raw/2024/",
            )

    mock_upload.assert_called_once_with(
        source_path="/tmp/test.parquet",
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abc123",
        hash_type="sha256",
        bucket_name="test-bucket",
    )


def test_custom_hasher():
    """Test custom hasher is used."""
    custom_hasher = MagicMock()
    processor = FileProcessor(
        download_dir=Path("/tmp"),
        hasher=custom_hasher,
    )

    with patch("orchestrator.processor.download_file") as mock_download:
        mock_download.return_value = mock_download_success()
        with patch("orchestrator.processor.upload_file", return_value=mock_upload_success()):
            Path("/tmp/test.parquet").write_bytes(b"test content")
            processor.process_file(
                url="http://example.com/test.parquet",
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )

    # O hasher é passado para download_file
    mock_download.assert_called_once()
    call_args = mock_download.call_args
    assert call_args[0][2] is custom_hasher
