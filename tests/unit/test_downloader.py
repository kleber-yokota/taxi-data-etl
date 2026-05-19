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


# ===========================================================================
# PRIORITY 1 - CRITICAL TESTS FOR x_execute_download_with_retry
# ===========================================================================

def test_execute_download_with_retry_attempts_and_logs(tmp_path, caplog):
    """
    CRITICAL TEST: Ensures all 3 retry attempts execute and logs are recorded.
    
    Detects mutations that alter the retry loop range (mutmut_6, mutmut_7)
    and filename extraction (mutmut_1, mutmut_28).
    """
    import logging
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    
    # Simulate 3 consecutive failures
    call_count = [0]
    
    def mock_stream_to_disk(*args, **kwargs):
        call_count[0] += 1
        raise NetworkError(f"Consecutive failure {call_count[0]}")
    
    with caplog.at_level(logging.WARNING):
        with patch("time.sleep"):
            with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk):
                with pytest.raises(NetworkError) as exc_info:
                    execute_download_with_retry(None, url, temp_path)
    
    # CRITICAL CHECK: Must have attempted 3 times
    assert call_count[0] == 3, f"Expected 3 attempts, got {call_count[0]}"
    assert str(exc_info.value) == "Consecutive failure 3"
    
    # CRITICAL CHECK: Must have logs for each attempt (logs include "for file.csv")
    log_messages = [record.message for record in caplog.records]
    assert any("Attempt 1 failed" in msg for msg in log_messages), "Missing log for Attempt 1"
    assert any("Attempt 2 failed" in msg for msg in log_messages), "Missing log for Attempt 2"
    assert any("Attempt 3 failed" in msg for msg in log_messages), "Missing log for Attempt 3"
    assert any("Maximum retry attempts reached" in msg for msg in log_messages), "Missing max retry log"


def test_execute_download_with_retry_exact_retry_count(tmp_path):
    """
    CRITICAL TEST: Counts exact calls to stream_to_disk.
    
    Detects mutations that alter the loop range:
    - range(2, MAX_RETRIES + 1) (mutmut_10) - skips 1st attempt
    - range(1, MAX_RETRIES - 1) (mutmut_11) - only 2 attempts
    - range(1, MAX_RETRIES + 2) (mutmut_12) - 4 attempts
    - range(None, ...) (mutmut_6)
    - range(1, None) (mutmut_7)
    """
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    
    call_count = [0]
    
    def mock_stream_to_disk(*args, **kwargs):
        call_count[0] += 1
        raise NetworkError(f"Failure {call_count[0]}")
    
    with patch("time.sleep"):
        with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk) as mock:
            with pytest.raises(NetworkError):
                execute_download_with_retry(None, url, temp_path)
    
    # CRITICAL CHECK: Must call exactly 3 times
    assert call_count[0] == 3, f"Expected 3 calls to stream_to_disk, got {call_count[0]}"
    assert mock.call_count == 3, f"Expected mock.call_count == 3, got {mock.call_count}"


def test_execute_download_with_retry_first_attempt_failure(tmp_path, caplog):
    """
    CRITICAL TEST: Simulates failure on the FIRST attempt.
    
    This is the most dangerous mutation (mutmut_10) that skips the 1st attempt.
    If the code is correct, the failure must happen on attempt 1.
    """
    import logging
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    
    # Mock that fails on 1st call using an object to persist state
    class MockState:
        def __init__(self):
            self.call_count = 0
        
        def __call__(self, *args, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                raise NetworkError("First attempt failed")
            raise NetworkError("Subsequent failures")
    
    mock_state = MockState()
    
    with caplog.at_level(logging.WARNING):
        with patch("time.sleep"):
            with patch("extract.downloader.stream_to_disk", side_effect=mock_state):
                with pytest.raises(NetworkError) as exc_info:
                    execute_download_with_retry(None, url, temp_path)
    
    # CHECK: Log must show "Attempt 1 failed" with the correct message
    log_messages = [record.message for record in caplog.records]
    assert any("Attempt 1 failed" in msg and "First attempt failed" in msg for msg in log_messages), \
        f"Expected 'Attempt 1 failed' with 'First attempt failed' in logs, got: {log_messages}"
    
    # The final exception will be "Subsequent failures" since the code tries 3 times
    # The important thing is that the 1st attempt was made and failed
    assert any("Attempt 1 failed" in msg for msg in log_messages), \
        "Should have logged Attempt 1 failure"


def test_execute_download_with_retry_temp_cleanup_on_failure(tmp_path):
    """
    CRITICAL TEST: Verifies temporary file is cleaned up after failure.
    
    Detects mutations that alter stream_to_disk parameters (mutmut_14-19).
    """
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    
    def mock_stream_to_disk(*args, **kwargs):
        # Create a temporary file
        temp_path.write_bytes(b"failed content")
        raise NetworkError("Network error")
    
    with patch("time.sleep"):
        with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk):
            with pytest.raises(NetworkError):
                execute_download_with_retry(None, url, temp_path)
    
    # CRITICAL CHECK: Temporary file must be deleted
    assert not temp_path.exists(), "Temporary file should be cleaned up after failure"


def test_execute_download_with_retry_recovery_second_attempt(tmp_path):
    """
    CRITICAL TEST: Simulates failure on 1st and success on 2nd attempt.
    
    Detects if mutmut_10 (range(2, MAX_RETRIES + 1)) is present.
    If present, this test will fail because the 1st attempt is skipped.
    """
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    success_content = b"success content"
    
    call_count = [0]
    
    def mock_stream_to_disk(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise NetworkError("First attempt failed")
        # Success on 2nd attempt
        temp_path.write_bytes(success_content)
    
    with patch("time.sleep"):
        with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk):
            execute_download_with_retry(None, url, temp_path)
    
    # CRITICAL CHECK: Must have attempted exactly 2 times
    assert call_count[0] == 2, f"Expected 2 attempts (1 fail, 1 success), got {call_count[0]}"
    assert temp_path.read_bytes() == success_content


def test_execute_download_with_retry_recovery_third_attempt(tmp_path):
    """
    CRITICAL TEST: Simulates failure on first 2 and success on 3rd attempt.
    
    Verifies the retry loop works correctly up to the maximum limit.
    Detects mutmut_10, mutmut_11, mutmut_12.
    """
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    success_content = b"final success"
    
    call_count = [0]
    
    def mock_stream_to_disk(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:
            raise NetworkError(f"Attempt {call_count[0]} failed")
        # Success on 3rd attempt
        temp_path.write_bytes(success_content)
    
    with patch("time.sleep"):
        with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk):
            execute_download_with_retry(None, url, temp_path)
    
    # CRITICAL CHECK: Must have attempted exactly 3 times
    assert call_count[0] == 3, f"Expected 3 attempts, got {call_count[0]}"
    assert temp_path.read_bytes() == success_content


def test_execute_download_with_retry_respects_max_retries(tmp_path, caplog):
    """
    CRITICAL TEST: Verifies the maximum number of retries is respected.
    
    Detects mutations that alter MAX_RETRIES in the range (mutmut_11, mutmut_12).
    """
    import logging
    from extract.downloader import NetworkError
    
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    
    call_count = [0]
    
    def mock_stream_to_disk(*args, **kwargs):
        call_count[0] += 1
        raise NetworkError(f"Persistent failure {call_count[0]}")
    
    with caplog.at_level(logging.ERROR):
        with patch("time.sleep"):
            with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk):
                with pytest.raises(NetworkError):
                    execute_download_with_retry(None, url, temp_path)
    
    # CRITICAL CHECK: Must not exceed MAX_RETRIES (3)
    assert call_count[0] <= 3, f"Exceeded MAX_RETRIES: {call_count[0]} attempts"
    assert any(
        "Maximum retry attempts reached" in record.message 
        for record in caplog.records
    ), "Missing max retry error log"


def test_execute_download_with_retry_filename_extraction(tmp_path, caplog):
    """
    CRITICAL TEST: Verifies filename is correctly extracted from URLs.
    
    Detects mutations that alter filename extraction (mutmut_2-5).
    """
    import logging
    from extract.downloader import NetworkError
    
    url = "http://example.com/path/to/myfile.csv"
    temp_path = tmp_path / "temp.tmp"
    
    def mock_stream_to_disk(*args, **kwargs):
        temp_path.write_bytes(b"content")
    
    # Configure logging to capture logs
    logger = logging.getLogger("extract.downloader")
    logger.setLevel(logging.INFO)
    
    with caplog.at_level(logging.INFO):
        with patch("time.sleep"):
            with patch("extract.downloader.stream_to_disk", side_effect=mock_stream_to_disk):
                execute_download_with_retry(None, url, temp_path)
    
    # CHECK: Log must contain the correct filename
    log_messages = [record.message for record in caplog.records]
    
    # Must contain the filename "myfile.csv"
    assert any("myfile.csv" in msg for msg in log_messages), \
        f"Expected 'myfile.csv' in logs, got: {log_messages}"


# ===========================================================================
# 4. MUTATION-KILLING TESTS (respx-based, no mock.patch)
# ===========================================================================
# These tests use respx for HTTP mocking instead of unittest.mock.patch
# to ensure they work correctly in mutmut's mirrored environment.


@respx.mock
def test_get_remote_size_http_error_logs_exact_message(caplog):
    """
    Tests that get_remote_size logs the exact HTTP error message for non-403/404 errors.
    
    Kills mutations that replace logger.error(...) with logger.error(None) (mutmut_19).
    """
    import logging

    url = "http://example.com/file.csv"
    respx.head(url).mock(return_value=httpx.Response(500))

    with caplog.at_level(logging.ERROR):
        with httpx.Client() as client:
            result = get_remote_size(client, url)

    assert result is None
    assert any(
        "HTTP error for" in record.message and url in record.message
        for record in caplog.records
    ), f"Expected HTTP error log for {url}, got: {[r.message for r in caplog.records]}"


@respx.mock
def test_execute_download_with_retry_exact_retry_count_respx(tmp_path):
    """
    Tests that exactly MAX_RETRIES (3) attempts are made using respx-based HTTP mocking.
    
    Unlike mock.patch-based tests, this works correctly in mutmut's mirrored
    environment because respx patches at the transport layer.
    
    Kills mutations that alter the loop range to 4 attempts (mutmut_12).
    """
    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"

    # All 3+ attempts will fail with HTTP 500
    respx.get(url).mock(return_value=httpx.Response(500))

    with patch("time.sleep"):
        with pytest.raises(httpx.HTTPStatusError):
            with httpx.Client() as client:
                execute_download_with_retry(client, url, temp_path)

    # Must have made exactly MAX_RETRIES (3) HTTP attempts
    assert len(respx.calls) == 3, (
        f"Expected 3 HTTP attempts, got {len(respx.calls)}. "
        f"If this is 4, the range(1, MAX_RETRIES+1) mutation (mutmut_12) survived."
    )


@respx.mock
def test_execute_download_with_retry_checksum_mismatch_logs_warning(tmp_path, caplog):
    """
    Tests that a checksum mismatch logs a warning and does not raise.
    
    Kills mutations that:
    - Replace `and not` with `or not` (mutmut_20)
    - Remove `not` from verify_checksum (mutmut_21)
    - Replace logger.warning(msg) with logger.warning(None) (mutmut_26)
    """
    import logging

    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    content = b"actual content"
    wrong_hash = "0" * 64

    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    with caplog.at_level(logging.WARNING):
        with patch("time.sleep"):
            with httpx.Client() as client:
                execute_download_with_retry(client, url, temp_path, wrong_hash)

    assert temp_path.read_bytes() == content
    warning_messages = [r.message for r in caplog.records]
    assert any(
        "Checksum verification failed for file.csv" in msg
        for msg in warning_messages
    ), f"Expected checksum warning in logs, got: {warning_messages}"


@respx.mock
def test_execute_download_with_retry_checksum_correct_no_warning(tmp_path, caplog):
    """
    Tests that a correct checksum produces no warning log.
    
    Kills mutations that alter verify_checksum arguments (mutmut_22, mutmut_23,
    mutmut_24, mutmut_25) by ensuring the correct checksum path is verified.
    """
    import logging
    import hashlib

    url = "http://example.com/file.csv"
    temp_path = tmp_path / "temp.tmp"
    content = b"valid content"
    expected_hash = hashlib.sha256(content).hexdigest()

    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    with caplog.at_level(logging.WARNING):
        with patch("time.sleep"):
            with httpx.Client() as client:
                execute_download_with_retry(client, url, temp_path, expected_hash)

    assert temp_path.read_bytes() == content
    warning_messages = [r.message for r in caplog.records]
    assert not any(
        "Checksum verification failed" in msg
        for msg in warning_messages
    ), f"Unexpected checksum warning for correct hash: {warning_messages}"


@respx.mock
def test_download_file_runtime_error_message(tmp_path):
    """
    Tests that RuntimeError contains a descriptive message when remote size is unavailable.
    
    Kills mutations that replace RuntimeError(msg) with RuntimeError(None) (mutmut_29).
    """
    download_dir = tmp_path / "rterror"
    url = "http://example.com/data.csv"

    # HEAD returns 500, causing get_remote_size to return None
    respx.head(url).mock(return_value=httpx.Response(500))

    with pytest.raises(RuntimeError, match="Could not determine remote size"):
        download_file(url, download_dir)


@respx.mock
def test_download_file_with_expected_hash_success(tmp_path):
    """
    Tests download_file with an expected_hash that matches the downloaded content.
    
    Kills mutations that drop the expected_hash argument when calling
    execute_download_with_retry (mutmut_39, mutmut_43).
    """
    import hashlib

    download_dir = tmp_path / "hash_check"
    url = "http://example.com/data.csv"
    content = b"content to verify"

    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": str(len(content))})
    )
    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    path, file_hash = download_file(url, download_dir, hashlib.sha256(content).hexdigest())

    assert path.exists()
    assert path.read_bytes() == content
    assert file_hash == hashlib.sha256(content).hexdigest()


@respx.mock
def test_download_file_success_log(tmp_path, caplog):
    """
    Tests that download_file logs a success message upon completion.
    
    Kills mutations that replace logger.info(msg) with logger.info(None) (mutmut_45).
    """
    import logging

    download_dir = tmp_path / "success_log"
    url = "http://example.com/data.csv"
    content = b"log test content"

    respx.head(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": str(len(content))})
    )
    respx.get(url).mock(return_value=httpx.Response(200, content=content))

    with caplog.at_level(logging.INFO):
        download_file(url, download_dir)

    assert any(
        "Successfully finalized download: data.csv" in record.message
        for record in caplog.records
    ), f"Expected success log, got: {[r.message for r in caplog.records]}"
