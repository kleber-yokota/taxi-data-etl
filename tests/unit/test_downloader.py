import hashlib
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from extract.downloader import (
    NetworkError,
    download_file,
    execute_download_with_retry,
    get_remote_size,
    is_download_required,
    stream_to_disk,
    verify_checksum,
)

# ==============================================================================
# 1. PURE LOGIC TESTS (Without Mocks)
# ==============================================================================
# These functions deal only with local files and calculations.
# Using tmp_path is the recommended practice for testing file IO.


def test_verify_checksum_correct(tmp_path):
    """Tests that the checksum is validated correctly for actual content."""
    file_path = tmp_path / "test.txt"
    content = b"hello world"
    file_path.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()
    assert verify_checksum(file_path, expected_hash) is True


def test_verify_checksum_incorrect(tmp_path):
    """Tests that the checksum fails for incorrect content."""
    file_path = tmp_path / "test.txt"
    file_path.write_bytes(b"hello world")
    assert verify_checksum(file_path, "wrong_hash") is False


def test_is_download_required_logic(tmp_path, caplog):
    """Tests the download decision logic based on existence and size."""
    import logging

    with caplog.at_level(logging.INFO):
        target_path = tmp_path / "exists.csv"

        # Case 1: File does not exist -> Download required
        missing_path = tmp_path / "missing.csv"
        assert is_download_required(missing_path, 100) is True
        assert f"File {missing_path.name} not found. Download required." in caplog.text

        # Case 2: File exists but size differs -> Download required
        target_path.write_bytes(b"123")  # size 3
        assert is_download_required(target_path, 100) is True
        assert (
            f"File {target_path.name} size mismatch. Re-download required."
            in caplog.text
        )

        # Case 3: Size matches -> Download NOT required
        assert is_download_required(target_path, 3) is False
        assert f"File {target_path.name} is already complete. Skipping." in caplog.text


# ==============================================================================
# 2. NETWORK AND BEHAVIOR TESTS (With respx)
# ==============================================================================
# respx intercepts httpx.Client calls, allowing us to test the real integration
# between module functions without needing complex MagicMocks.


@respx.mock
def test_get_remote_size_behavior():
    """Tests retrieving the remote size via HEAD request."""
    url = "http://example.com/file.csv"
    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": "1234"})
    )

    with httpx.Client() as client:
        assert get_remote_size(client, url) == 1234

    # Test missing Content-Length header
    respx.head(url).mock(return_value=httpx.Response(200))
    with httpx.Client() as client:
        assert get_remote_size(client, url) == 0


@respx.mock
def test_stream_to_disk_behavior(tmp_path):
    """Tests writing stream chunks to disk."""
    url = "http://example.com/file.csv"
    temp_file = tmp_path / "test.tmp"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"chunk1chunk2"))

    with httpx.Client() as client:
        stream_to_disk(client, url, temp_file)

    assert temp_file.read_bytes() == b"chunk1chunk2"


@respx.mock
def test_execute_download_retry_behavior(tmp_path, caplog):
    """
    Tests that the download retries if an error occurs.
    We test the real integration between execute_download_with_retry and stream_to_disk.
    """
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"

    # Simulates: 1st attempt Error 500, 2nd attempt Success
    respx.get(url).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, content=b"recovered content"),
        ]
    )

    with patch("time.sleep"):  # Prevents the test from waiting for retry delays
        with httpx.Client() as client:
            execute_download_with_retry(client, url, temp_path)

    assert temp_path.read_bytes() == b"recovered content"
    # Verify the filename was correctly extracted and used in the logs
    filename = "file.csv"
    assert any(
        f"Attempt 1 failed for {filename}" in record.message
        for record in caplog.records
    )


@respx.mock
def test_download_file_full_flow_success(tmp_path):
    """
    Full flow: Idempotency Check (HEAD) -> Download (GET) -> Atomic Replace.
    Verifies the complete orchestration of the download_file coordinator.
    """
    download_dir = tmp_path / "downloads"
    url = "http://example.com/data.csv"
    content = b"final content"

    # Mock Server Configuration
    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": str(len(content))})
    )
    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    # Coordinator execution (testing the final behavior)
    path, file_hash = download_file(url, download_dir)

    assert path.exists()
    assert path.read_bytes() == content
    assert path.name == "data.csv"
    assert file_hash == hashlib.sha256(content).hexdigest()


@respx.mock
def test_download_file_nested_directory(tmp_path):
    """Tests that download_file correctly creates nested download directories."""
    download_dir = tmp_path / "deep" / "nested" / "downloads"
    url = "http://example.com/data.csv"
    content = b"nested content"

    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": str(len(content))})
    )
    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    path, _ = download_file(url, download_dir)

    assert path.exists()
    assert download_dir.exists()


@respx.mock
def test_download_file_idempotency_behavior(tmp_path):
    """Tests that the file is NOT downloaded if it already exists with the correct size."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    url = "http://example.com/data.csv"
    target_path = download_dir / "data.csv"

    content = b"stable content"
    target_path.write_bytes(content)

    # Server says size is identical to local
    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": str(len(content))})
    )
    # If GET is called, the test will fail because we configured a 404
    mock_get = respx.get(url).mock(return_value=httpx.Response(404))

    result_path, result_hash = download_file(url, download_dir)

    assert result_path == target_path
    assert result_hash == hashlib.sha256(content).hexdigest()
    # Ensures that the download request (GET) was never triggered
    assert mock_get.call_count == 0


@respx.mock
def test_download_file_forbidden_behavior(tmp_path, caplog):
    """Tests that a 403 Forbidden response results in None and a warning log."""
    download_dir = tmp_path / "forbidden"
    url = "http://example.com/forbidden.csv"
    respx.head(url).mock(return_value=httpx.Response(403))

    result = download_file(url, download_dir)

    assert result is None
    assert any("Access forbidden" in record.message for record in caplog.records)


@respx.mock
def test_download_file_not_found_behavior(tmp_path, caplog):
    """Tests that a 404 Not Found response results in None and a warning log."""
    download_dir = tmp_path / "not_found"
    url = "http://example.com/missing.csv"
    respx.head(url).mock(return_value=httpx.Response(404))

    result = download_file(url, download_dir)

    assert result is None
    assert any("File not found" in record.message for record in caplog.records)


@respx.mock
def test_download_file_network_error_behavior(tmp_path):
    """Tests that a network connection error raises NetworkError."""
    download_dir = tmp_path / "network_error"
    url = "http://example.com/error.csv"
    respx.head(url).mock(side_effect=httpx.ConnectError("Connection failed"))

    with pytest.raises(NetworkError, match="Network connection failed"):
        download_file(url, download_dir)
