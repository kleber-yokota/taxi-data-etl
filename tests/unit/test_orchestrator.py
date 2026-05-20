"""Unit tests for the refactored pipeline with composition."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator import PipelineOrchestrator
from orchestrator.result import FileOutcome, FileStatus, PipelineResult
from extract.hasher import Sha256Hasher
from upload.uploader import UploadResult, UploadStatus


def mock_download_success():
    return MagicMock(
        file_path=Path("/tmp/test.parquet"),
        hash_value="abc123",
        hash_type="sha256",
    )


def mock_upload_success():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SUCCESS,
        hash_value="abc123",
        hash_type="sha256",
    )


def test_empty_urls():
    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=[]):
        orchestrator = PipelineOrchestrator(hasher=MagicMock())
        result = orchestrator.run()

    assert result.total == 0
    assert result.succeeded == 0
    assert result.skipped == 0
    assert result.failed == 0
    assert result.files == []


def test_all_success():
    test_urls = [
        "http://example.com/file1.parquet",
        "http://example.com/file2.parquet",
    ]

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", return_value=mock_download_success()):
            with patch("orchestrator.processor.upload_file", return_value=mock_upload_success()):
                Path("/tmp/test.parquet").write_bytes(b"test content")
                orchestrator = PipelineOrchestrator(hasher=MagicMock())
                result = orchestrator.run()

    assert result.total == 2
    assert result.succeeded == 2
    assert result.skipped == 0
    assert result.failed == 0
    assert all(f.status == FileStatus.SUCCESS for f in result.files)


def test_download_forbidden():
    test_urls = ["http://example.com/forbidden.parquet"]

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", return_value=None):
            orchestrator = PipelineOrchestrator(hasher=MagicMock())
            result = orchestrator.run()

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.files[0].status == FileStatus.DOWNLOAD_FAILED


def test_download_raises_exception():
    test_urls = ["http://example.com/error.parquet"]

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", side_effect=RuntimeError("Connection timeout")):
            orchestrator = PipelineOrchestrator(hasher=MagicMock())
            result = orchestrator.run()

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.files[0].status == FileStatus.DOWNLOAD_FAILED
    assert "Connection timeout" in result.files[0].error_message


def test_upload_error():
    test_urls = ["http://example.com/file.parquet"]
    upload_error = UploadResult(
        file_name="file.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.ERROR,
        error_message="S3 connection refused",
    )

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", return_value=mock_download_success()):
            with patch("orchestrator.processor.upload_file", return_value=upload_error):
                Path("/tmp/test.parquet").write_bytes(b"test content")
                orchestrator = PipelineOrchestrator(hasher=MagicMock())
                result = orchestrator.run()

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.files[0].status == FileStatus.UPLOAD_FAILED
    assert "S3 connection refused" in result.files[0].upload_result.error_message


def test_upload_skipped():
    test_urls = ["http://example.com/file.parquet"]
    upload_skipped = UploadResult(
        file_name="file.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc123",
        hash_type="sha256",
    )

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", return_value=mock_download_success()):
            with patch("orchestrator.processor.upload_file", return_value=upload_skipped):
                Path("/tmp/test.parquet").write_bytes(b"test content")
                orchestrator = PipelineOrchestrator(hasher=MagicMock())
                result = orchestrator.run()

    assert result.total == 1
    assert result.succeeded == 0
    assert result.skipped == 1
    assert result.failed == 0
    assert result.files[0].status == FileStatus.SKIPPED


def test_mixed_scenario():
    test_urls = [
        "http://example.com/file1.parquet",
        "http://example.com/file2.parquet",
        "http://example.com/file3.parquet",
    ]

    def mock_download_side_effect(*args, **kwargs):
        url = args[0] if args else kwargs.get('url', '')
        if "file1" in url:
            return mock_download_success()
        elif "file2" in url:
            raise RuntimeError("Network error")
        else:
            return mock_download_success()

    upload_ok = UploadResult(
        file_name="file1.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SUCCESS,
        hash_value="abc123",
        hash_type="sha256",
    )
    upload_skipped = UploadResult(
        file_name="file3.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc123",
        hash_type="sha256",
    )

    call_count = [0]

    def mock_upload_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return upload_ok
        else:
            return upload_skipped

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", side_effect=mock_download_side_effect):
            with patch("orchestrator.processor.upload_file", side_effect=mock_upload_side_effect):
                Path("/tmp/test.parquet").write_bytes(b"test content")
                Path("/tmp/file3.parquet").write_bytes(b"test content")
                orchestrator = PipelineOrchestrator(hasher=MagicMock())
                result = orchestrator.run()

    assert result.total == 3
    assert result.succeeded == 1
    assert result.skipped == 1
    assert result.failed == 1


def test_bucket_path_prefix():
    test_urls = ["http://example.com/yellow_tripdata_2024-01.parquet"]

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", return_value=mock_download_success()):
            with patch("orchestrator.processor.upload_file") as mock_upload:
                mock_upload.return_value = mock_upload_success()
                Path("/tmp/test.parquet").write_bytes(b"test content")
                orchestrator = PipelineOrchestrator(hasher=MagicMock())
                orchestrator.run(bucket_path_prefix="raw/2024/")

    mock_upload.assert_called_once_with(
        source_path="/tmp/test.parquet",
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abc123",
        hash_type="sha256",
        bucket_name="raw-data",
    )


def test_custom_bucket_name():
    test_urls = ["http://example.com/yellow_tripdata_2024-01.parquet"]

    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
        with patch("orchestrator.processor.download_file", return_value=mock_download_success()):
            with patch("orchestrator.processor.upload_file") as mock_upload:
                mock_upload.return_value = mock_upload_success()
                Path("/tmp/test.parquet").write_bytes(b"test content")
                orchestrator = PipelineOrchestrator(hasher=MagicMock())
                orchestrator.run(bucket_name="my-custom-bucket")

    mock_upload.assert_called_once_with(
        source_path="/tmp/test.parquet",
        bucket_path="yellow_tripdata_2024-01.parquet",
        file_hash="abc123",
        hash_type="sha256",
        bucket_name="my-custom-bucket",
    )
