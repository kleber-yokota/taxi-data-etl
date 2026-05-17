import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from extract.downloader import download_file, download_all
import httpx

@pytest.fixture
def mock_httpx_client(mocker):
    """Mocks the httpx.Client and its methods."""
    mock_client = mocker.patch("httpx.Client")
    return mock_client.return_value

def test_download_file_new_file(mock_httpx_client, tmp_path):
    """Test that a non-existent file is downloaded."""
    url = "https://example.com/test.parquet"
    download_dir = tmp_path
    
    # Mock HEAD response for size
    mock_head = MagicMock()
    mock_head.headers = {"Content-Length": "100"}
    mock_head.raise_for_status = MagicMock()
    mock_httpx_client.head.return_value = mock_head
    
    # Mock stream for download
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = [b"chunk1", b"chunk2"]
    
    # Setup the context manager for stream
    mock_httpx_client.stream.return_value.__enter__.return_value = mock_response

    result = download_file(url, download_dir)
    
    assert result.exists()
    assert result.name == "test.parquet"
    mock_httpx_client.stream.assert_called_once_with("GET", url)

def test_download_file_idempotent_skip(mock_httpx_client, tmp_path):
    """Test that a file is skipped if size matches remote."""
    url = "https://example.com/test.parquet"
    download_dir = tmp_path
    target_file = download_dir / "test.parquet"
    
    # Create a local file with size 100
    target_file.write_bytes(b"a" * 100)
    
    # Mock HEAD response for size 100
    mock_head = MagicMock()
    mock_head.headers = {"Content-Length": "100"}
    mock_head.raise_for_status = MagicMock()
    mock_httpx_client.head.return_value = mock_head
    
    result = download_file(url, download_dir)
    
    assert result == target_file
    # Stream should NOT be called
    mock_httpx_client.stream.assert_not_called()

def test_download_file_idempotent_redownload(mock_httpx_client, tmp_path):
    """Test that a file is redownloaded if size differs."""
    url = "https://example.com/test.parquet"
    download_dir = tmp_path
    target_file = download_dir / "test.parquet"
    
    # Create a local file with size 50
    target_file.write_bytes(b"a" * 50)
    
    # Mock HEAD response for size 100
    mock_head = MagicMock()
    mock_head.headers = {"Content-Length": "100"}
    mock_head.raise_for_status = MagicMock()
    mock_httpx_client.head.return_value = mock_head
    
    # Mock stream for download
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = [b"chunk1"]
    mock_httpx_client.stream.return_value.__enter__.return_value = mock_response

    result = download_file(url, download_dir)
    
    assert result == target_file
    # Stream SHOULD be called because size differs
    mock_httpx_client.stream.assert_called_once_with("GET", url)

def test_download_all_handles_errors(mock_httpx_client, tmp_path):
    """Test that download_all continues if one file fails."""
    urls = {"https://example.com/ok.parquet", "https://example.com/fail.parquet"}
    download_dir = tmp_path
    
    # Setup mocks to fail for the 'fail' URL and succeed for the 'ok' URL
    def side_effect(url):
        if "fail" in url:
            raise httpx.HTTPError("Network Error")
        # Success case
        mock_head = MagicMock()
        mock_head.headers = {"Content-Length": "10"}
        mock_head.raise_for_status = MagicMock()
        return mock_head

    mock_httpx_client.head.side_effect = side_effect
    
    # Setup stream mock for the success case
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = [b"data"]
    mock_httpx_client.stream.return_value.__enter__.return_value = mock_response

    results = download_all(urls, str(download_dir))
    
    # Only one file should have been successfully downloaded
    assert len(results) == 1
