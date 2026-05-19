from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.pipeline import (
    FileOutcome,
    FileStatus,
    PipelineResult,
    run_pipeline,
)
from upload.uploader import UploadResult, UploadStatus


@pytest.fixture
def mock_download_success():
    result = MagicMock()
    result.file_path = Path("/tmp/test.parquet")
    result.hash_value = "abc123"
    result.hash_type = "sha256"
    return result


@pytest.fixture
def mock_upload_success():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SUCCESS,
        hash_value="abc123",
        hash_type="sha256",
    )


def test_empty_urls():
    with patch("orchestrator.pipeline.generate_parquet_urls", return_value=[]):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 0
    assert result.succeeded == 0
    assert result.skipped == 0
    assert result.failed == 0
    assert result.files == []


def test_all_success(mock_download_success, mock_upload_success):
    test_urls = [
        "http://example.com/file1.parquet",
        "http://example.com/file2.parquet",
    ]

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file", return_value=mock_download_success
        ),
        patch("orchestrator.pipeline.upload_file", return_value=mock_upload_success),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 2
    assert result.succeeded == 2
    assert result.skipped == 0
    assert result.failed == 0
    assert all(f.status == FileStatus.SUCCESS for f in result.files)


def test_download_forbidden(mock_upload_success):
    test_urls = ["http://example.com/forbidden.parquet"]

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch("orchestrator.pipeline.download_file", return_value=None),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.files[0].status == FileStatus.DOWNLOAD_FAILED


def test_download_raises_exception():
    test_urls = ["http://example.com/error.parquet"]

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file",
            side_effect=RuntimeError("Connection timeout"),
        ),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.files[0].status == FileStatus.DOWNLOAD_ERROR
    assert "Connection timeout" in result.files[0].error_message


def test_upload_error(mock_download_success):
    test_urls = ["http://example.com/file.parquet"]
    upload_error = UploadResult(
        file_name="file.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.ERROR,
        error_message="S3 connection refused",
    )

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file", return_value=mock_download_success
        ),
        patch("orchestrator.pipeline.upload_file", return_value=upload_error),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert result.files[0].status == FileStatus.UPLOAD_FAILED
    assert "S3 connection refused" in result.files[0].error_message


def test_upload_skipped(mock_download_success):
    test_urls = ["http://example.com/file.parquet"]
    upload_skipped = UploadResult(
        file_name="file.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc123",
        hash_type="sha256",
    )

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file", return_value=mock_download_success
        ),
        patch("orchestrator.pipeline.upload_file", return_value=upload_skipped),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 1
    assert result.succeeded == 0
    assert result.skipped == 1
    assert result.failed == 0
    assert result.files[0].status == FileStatus.SKIPPED


def test_mixed_scenario():
    success_result = MagicMock()
    success_result.file_path = Path("/tmp/success.parquet")
    success_result.hash_value = "abc"
    success_result.hash_type = "sha256"

    forbidden_result = MagicMock()
    forbidden_result.file_path = Path("/tmp/forbidden.parquet")
    forbidden_result.hash_value = "def"
    forbidden_result.hash_type = "sha256"

    test_urls = [
        "http://example.com/success.parquet",
        "http://example.com/forbidden.parquet",
        "http://example.com/error.parquet",
    ]

    upload_ok = UploadResult(
        file_name="success.parquet",
        original_path="/tmp/success.parquet",
        status=UploadStatus.SUCCESS,
        hash_value="abc",
        hash_type="sha256",
    )

    def mock_download_side_effect(url, *args, **kwargs):
        if "success" in url:
            return success_result
        elif "forbidden" in url:
            return None
        raise RuntimeError("Network error")

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file",
            side_effect=mock_download_side_effect,
        ),
        patch("orchestrator.pipeline.upload_file", return_value=upload_ok),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == 3
    assert result.succeeded == 1
    assert result.failed == 2
    assert result.files[0].status == FileStatus.SUCCESS
    assert result.files[1].status == FileStatus.DOWNLOAD_FAILED
    assert result.files[2].status == FileStatus.DOWNLOAD_ERROR


def test_bucket_path_prefix(mock_download_success, mock_upload_success):
    test_urls = ["http://example.com/yellow_tripdata_2024-01.parquet"]

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file", return_value=mock_download_success
        ),
        patch("orchestrator.pipeline.upload_file") as mock_upload,
    ):
        mock_upload.return_value = mock_upload_success
        run_pipeline(
            hasher=MagicMock(),
            bucket_path_prefix="raw/2024/",
        )

    mock_upload.assert_called_once_with(
        source_path="/tmp/test.parquet",
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abc123",
        hash_type="sha256",
        bucket_name="raw-data",
    )


def test_custom_bucket_name(mock_download_success, mock_upload_success):
    test_urls = ["http://example.com/yellow_tripdata_2024-01.parquet"]

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=test_urls),
        patch(
            "orchestrator.pipeline.download_file", return_value=mock_download_success
        ),
        patch("orchestrator.pipeline.upload_file") as mock_upload,
    ):
        mock_upload.return_value = mock_upload_success
        run_pipeline(
            hasher=MagicMock(),
            bucket_name="my-custom-bucket",
        )

    mock_upload.assert_called_once_with(
        source_path="/tmp/test.parquet",
        bucket_path="yellow_tripdata_2024-01.parquet",
        file_hash="abc123",
        hash_type="sha256",
        bucket_name="my-custom-bucket",
    )
