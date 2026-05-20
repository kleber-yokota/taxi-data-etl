"""Unit tests for ResultAggregator."""

from unittest.mock import MagicMock

import pytest

from orchestrator.aggregator import ResultAggregator
from orchestrator.result import FileOutcome, FileStatus
from extract.downloader import DownloadResult
from upload.uploader import UploadResult, UploadStatus


def mock_download_result():
    return MagicMock(
        file_path=MagicMock(),
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


def mock_upload_skipped():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc123",
        hash_type="sha256",
    )


def mock_upload_error():
    return UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.ERROR,
        error_message="Upload failed",
    )


def test_aggregator_initial_state():
    """Test aggregator starts with zero counts and empty outcomes."""
    aggregator = ResultAggregator()

    assert aggregator.outcomes == []
    assert aggregator.succeeded == 0
    assert aggregator.skipped == 0
    assert aggregator.failed == 0


def test_aggregator_add_success():
    """Test adding a successful outcome."""
    aggregator = ResultAggregator()

    outcome = FileOutcome(
        url="http://example.com/file.parquet",
        status=FileStatus.SUCCESS,
        download_result=mock_download_result(),
        upload_result=mock_upload_success(),
    )

    aggregator.add_outcome(outcome)

    assert len(aggregator.outcomes) == 1
    assert aggregator.succeeded == 1
    assert aggregator.skipped == 0
    assert aggregator.failed == 0


def test_aggregator_add_skipped():
    """Test adding a skipped outcome."""
    aggregator = ResultAggregator()

    outcome = FileOutcome(
        url="http://example.com/file.parquet",
        status=FileStatus.SKIPPED,
        download_result=mock_download_result(),
        upload_result=mock_upload_skipped(),
    )

    aggregator.add_outcome(outcome)

    assert len(aggregator.outcomes) == 1
    assert aggregator.succeeded == 0
    assert aggregator.skipped == 1
    assert aggregator.failed == 0


def test_aggregator_add_failed():
    """Test adding a failed outcome."""
    aggregator = ResultAggregator()

    outcome = FileOutcome(
        url="http://example.com/file.parquet",
        status=FileStatus.UPLOAD_FAILED,
        download_result=mock_download_result(),
        upload_result=mock_upload_error(),
        error_message="Upload failed",
    )

    aggregator.add_outcome(outcome)

    assert len(aggregator.outcomes) == 1
    assert aggregator.succeeded == 0
    assert aggregator.skipped == 0
    assert aggregator.failed == 1


def test_aggregator_add_download_failed():
    """Test adding a download failed outcome."""
    aggregator = ResultAggregator()

    outcome = FileOutcome(
        url="http://example.com/file.parquet",
        status=FileStatus.DOWNLOAD_FAILED,
        error_message="Download failed",
    )

    aggregator.add_outcome(outcome)

    assert len(aggregator.outcomes) == 1
    assert aggregator.succeeded == 0
    assert aggregator.skipped == 0
    assert aggregator.failed == 1


def test_aggregator_add_download_error():
    """Test adding a download error outcome."""
    aggregator = ResultAggregator()

    outcome = FileOutcome(
        url="http://example.com/file.parquet",
        status=FileStatus.DOWNLOAD_ERROR,
        error_message="Connection timeout",
    )

    aggregator.add_outcome(outcome)

    assert len(aggregator.outcomes) == 1
    assert aggregator.succeeded == 0
    assert aggregator.skipped == 0
    assert aggregator.failed == 1


def test_aggregator_get_result():
    """Test getting aggregated PipelineResult."""
    aggregator = ResultAggregator()

    success_outcome = FileOutcome(
        url="http://example.com/file1.parquet",
        status=FileStatus.SUCCESS,
        download_result=mock_download_result(),
        upload_result=mock_upload_success(),
    )

    skipped_outcome = FileOutcome(
        url="http://example.com/file2.parquet",
        status=FileStatus.SKIPPED,
        download_result=mock_download_result(),
        upload_result=mock_upload_skipped(),
    )

    failed_outcome = FileOutcome(
        url="http://example.com/file3.parquet",
        status=FileStatus.UPLOAD_FAILED,
        download_result=mock_download_result(),
        upload_result=mock_upload_error(),
        error_message="Upload failed",
    )

    aggregator.add_outcome(success_outcome)
    aggregator.add_outcome(skipped_outcome)
    aggregator.add_outcome(failed_outcome)

    result = aggregator.get_result()

    assert result.total == 3
    assert result.succeeded == 1
    assert result.skipped == 1
    assert result.failed == 1
    assert len(result.files) == 3
    assert result.files[0] is success_outcome
    assert result.files[1] is skipped_outcome
    assert result.files[2] is failed_outcome


def test_aggregator_multiple_outcomes():
    """Test adding multiple outcomes."""
    aggregator = ResultAggregator()

    for i in range(5):
        outcome = FileOutcome(
            url=f"http://example.com/file{i}.parquet",
            status=FileStatus.SUCCESS,
            download_result=mock_download_result(),
            upload_result=mock_upload_success(),
        )
        aggregator.add_outcome(outcome)

    result = aggregator.get_result()

    assert result.total == 5
    assert result.succeeded == 5
    assert result.skipped == 0
    assert result.failed == 0


def test_aggregator_mixed_outcomes():
    """Test adding mixed outcomes."""
    aggregator = ResultAggregator()

    outcomes = [
        FileOutcome(
            url="http://example.com/file1.parquet",
            status=FileStatus.SUCCESS,
            download_result=mock_download_result(),
            upload_result=mock_upload_success(),
        ),
        FileOutcome(
            url="http://example.com/file2.parquet",
            status=FileStatus.SKIPPED,
            download_result=mock_download_result(),
            upload_result=mock_upload_skipped(),
        ),
        FileOutcome(
            url="http://example.com/file3.parquet",
            status=FileStatus.DOWNLOAD_FAILED,
            error_message="Forbidden",
        ),
        FileOutcome(
            url="http://example.com/file4.parquet",
            status=FileStatus.UPLOAD_FAILED,
            download_result=mock_download_result(),
            upload_result=mock_upload_error(),
            error_message="Upload failed",
        ),
        FileOutcome(
            url="http://example.com/file5.parquet",
            status=FileStatus.DOWNLOAD_ERROR,
            error_message="Connection timeout",
        ),
    ]

    for outcome in outcomes:
        aggregator.add_outcome(outcome)

    result = aggregator.get_result()

    assert result.total == 5
    assert result.succeeded == 1
    assert result.skipped == 1
    assert result.failed == 3
