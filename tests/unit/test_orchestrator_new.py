"""Unit tests for the refactored pipeline with composition."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator import PipelineOrchestrator, FileProcessor, ResultAggregator
from orchestrator.result import FileOutcome, FileStatus, PipelineResult
from extract.hasher import Sha256Hasher
from upload.uploader import UploadResult, UploadStatus


def test_result_aggregator_counts():
    """Test ResultAggregator counts correctly."""
    aggregator = ResultAggregator()

    outcomes = [
        FileOutcome(url="url1", status=FileStatus.SUCCESS),
        FileOutcome(url="url2", status=FileStatus.SKIPPED),
        FileOutcome(url="url3", status=FileStatus.DOWNLOAD_ERROR),
        FileOutcome(url="url4", status=FileStatus.UPLOAD_FAILED),
    ]

    for outcome in outcomes:
        aggregator.add_outcome(outcome)

    result = aggregator.get_result()

    assert result.total == 4
    assert result.succeeded == 1
    assert result.skipped == 1
    assert result.failed == 2
    assert len(result.files) == 4


def test_file_processor_download_scenarios():
    """Test FileProcessor download scenarios without requiring upload."""
    processor = FileProcessor(
        download_dir=Path("/tmp/test"),
        hasher=Sha256Hasher(),
    )
    
    test_url = "http://example.com/test.parquet"
    
    mock_download_result = MagicMock()
    mock_download_result.file_path = Path("/tmp/test.parquet")
    mock_download_result.hash_value = "abc123"
    mock_download_result.hash_type = "sha256"
    
    # Scenario 1: Download forbidden
    with patch.object(processor, '_download', return_value=None):
        outcome = processor.process_file(
            url=test_url,
            bucket_name="test-bucket",
            bucket_path_prefix="",
        )
        assert outcome.status == FileStatus.DOWNLOAD_FAILED
        assert outcome.error_message == "forbidden or not found"
    
    # Scenario 2: Download exception
    with patch.object(processor, '_download', side_effect=RuntimeError("Connection timeout")):
        outcome = processor.process_file(
            url=test_url,
            bucket_name="test-bucket",
            bucket_path_prefix="",
        )
        assert outcome.status == FileStatus.DOWNLOAD_ERROR
        assert "Connection timeout" in outcome.error_message


def test_file_processor_upload_scenarios():
    """Test FileProcessor upload scenarios with mocked upload."""
    processor = FileProcessor(
        download_dir=Path("/tmp/test"),
        hasher=Sha256Hasher(),
    )
    
    test_url = "http://example.com/test.parquet"
    
    mock_download_result = MagicMock()
    mock_download_result.file_path = Path("/tmp/test.parquet")
    mock_download_result.hash_value = "abc123"
    mock_download_result.hash_type = "sha256"
    
    # Scenario 1: Upload success
    with patch.object(processor, '_upload', return_value=UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SUCCESS,
        hash_value="abc123",
        hash_type="sha256",
    )):
        with patch.object(processor, '_download', return_value=mock_download_result):
            outcome = processor.process_file(
                url=test_url,
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )
            assert outcome.status == FileStatus.SUCCESS
    
    # Scenario 2: Upload error
    with patch.object(processor, '_upload', return_value=UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.ERROR,
        error_message="S3 connection refused",
    )):
        with patch.object(processor, '_download', return_value=mock_download_result):
            outcome = processor.process_file(
                url=test_url,
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )
            assert outcome.status == FileStatus.UPLOAD_FAILED
            assert "S3 connection refused" in outcome.upload_result.error_message
    
    # Scenario 3: Upload skipped
    with patch.object(processor, '_upload', return_value=UploadResult(
        file_name="test.parquet",
        original_path="/tmp/test.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc123",
        hash_type="sha256",
    )):
        with patch.object(processor, '_download', return_value=mock_download_result):
            outcome = processor.process_file(
                url=test_url,
                bucket_name="test-bucket",
                bucket_path_prefix="",
            )
            assert outcome.status == FileStatus.SKIPPED


def test_file_processor_bucket_path_prefix():
    """Test FileProcessor correctly applies bucket path prefix."""
    processor = FileProcessor(
        download_dir=Path("/tmp/test"),
        hasher=Sha256Hasher(),
    )
    
    test_url = "http://example.com/yellow_tripdata_2024-01.parquet"
    
    mock_download_result = MagicMock(
        file_path=Path("/tmp/test.parquet"),
        hash_value="abc123",
        hash_type="sha256",
    )
    
    with patch.object(processor, '_upload') as mock_upload:
        mock_upload.return_value = UploadResult(
            file_name="test.parquet",
            original_path="/tmp/test.parquet",
            status=UploadStatus.SUCCESS,
            hash_value="abc123",
            hash_type="sha256",
        )
        
        with patch.object(processor, '_download', return_value=mock_download_result):
            outcome = processor.process_file(
                url=test_url,
                bucket_name="test-bucket",
                bucket_path_prefix="raw/2024/",
            )
            
            assert outcome.status == FileStatus.SUCCESS
            mock_upload.assert_called_once_with(
                source_path="/tmp/test.parquet",
                bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
                file_hash="abc123",
                hash_type="sha256",
                bucket_name="test-bucket",
            )


def test_orchestrator_empty_urls():
    """Test Orchestrator with no URLs."""
    orchestrator = PipelineOrchestrator(
        hasher=Sha256Hasher(),
        download_dir=Path("/tmp/test"),
        bucket_name="test-bucket",
        bucket_path_prefix="",
    )
    
    with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=[]):
        result = orchestrator.run()
        
        assert result.total == 0
        assert result.succeeded == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert len(result.files) == 0


def test_orchestrator_pipeline_execution():
    """Test Orchestrator with complete pipeline execution."""
    orchestrator = PipelineOrchestrator(
        hasher=Sha256Hasher(),
        download_dir=Path("/tmp/test"),
        bucket_name="test-bucket",
        bucket_path_prefix="raw/data/",
    )
    
    test_urls = [
        "http://example.com/yellow_tripdata_2024-01.parquet",
        "http://example.com/green_tripdata_2024-01.parquet",
    ]
    
    mock_outcome = FileOutcome(
        url=test_urls[0],
        status=FileStatus.SUCCESS,
    )
    
    with patch.object(orchestrator.processor, 'process_file', return_value=mock_outcome):
        with patch("orchestrator.orchestrator.generate_parquet_urls", return_value=test_urls):
            result = orchestrator.run()
            
            assert result.total == 2
            assert result.succeeded == 2
            assert result.skipped == 0
            assert result.failed == 0
            assert len(result.files) == 2
            assert all(f.status == FileStatus.SUCCESS for f in result.files)
            
            # Verify process_file was called for each URL
            assert orchestrator.processor.process_file.call_count == 2