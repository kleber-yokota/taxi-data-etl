import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


class ChecksumError(Exception):
    """Raised when a downloaded file fails checksum verification."""

    pass


class NetworkError(Exception):
    """Raised when a network connection failure occurs."""

    pass


class FileForbiddenError(Exception):
    """Raised when access to a file is forbidden (HTTP 403)."""

    pass


class RemoteFileNotFoundError(Exception):
    """Raised when a remote file is not found (HTTP 404)."""

    pass


# Retry configurations
MAX_RETRIES = 3
RETRY_DELAY = 2  # Initial delay in seconds

# ==========================================
# 1. NETWORK & IO PRIMITIVES (Low Level)
# ==========================================


def get_remote_size(client: httpx.Client, url: str) -> Optional[int]:
    """
    Retrieves the remote file size using an HTTP HEAD request.

    Args:
        client (httpx.Client): The HTTP client instance.
        url (str): The absolute URL of the file.

    Returns:
        Optional[int]: The size of the file in bytes, or None if the request fails.
    """
    try:
        response = client.head(url)
        response.raise_for_status()
        return int(response.headers.get("Content-Length", 0))
    except httpx.ConnectError as e:
        raise NetworkError(f"Network connection failed for {url}: {e}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise FileForbiddenError(f"Access forbidden for {url}")
        if e.response.status_code == 404:
            raise RemoteFileNotFoundError(f"File not found: {url}")
        logger.error(f"HTTP error for {url}: {e}")
        return None
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"Unexpected error retrieving metadata for {url}: {e}")
        return None


def stream_to_disk(client: httpx.Client, url: str, temp_path: Path) -> None:
    """
    Downloads the file content via streaming and writes it to a temporary file.

    Args:
        client (httpx.Client): The HTTP client instance.
        url (str): The absolute URL of the file.
        temp_path (Path): The temporary path where the file will be written.
    """
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(temp_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)


def compute_sha256(file_path: Path) -> str:
    """
    Computes the SHA-256 checksum of a file.

    Args:
        file_path (Path): The path to the file.

    Returns:
        str: The SHA-256 hash string.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def verify_checksum(file_path: Path, expected_hash: str) -> bool:
    """
    Verifies the SHA-256 checksum of a file to ensure data integrity.

    Args:
        file_path (Path): The path to the file to verify.
        expected_hash (str): The expected SHA-256 hash string.

    Returns:
        bool: True if the computed hash matches the expected hash, False otherwise.
    """
    return compute_sha256(file_path) == expected_hash


# ==========================================
# 2. IDEMPOTENCY LOGIC (Decision Layer)
# ==========================================


def is_download_required(
    target_path: Path, remote_size: int, expected_hash: Optional[str] = None
) -> bool:
    """
    Determines if a download is necessary based on file existence, size, and optional checksum.

    Args:
        target_path (Path): The final target path of the file.
        remote_size (int): The expected size of the file on the remote server.

    Returns:
        bool: True if the file needs to be downloaded or updated, False if already complete.
    """
    if not target_path.exists():
        logger.info(f"File {target_path.name} not found. Download required.")
        return True

    if target_path.stat().st_size != remote_size:
        logger.info(f"File {target_path.name} size mismatch. Re-download required.")
        return True

    logger.info(f"File {target_path.name} is already complete. Skipping.")
    return False


# ==========================================
# 3. EXECUTION LOGIC (Retry Layer)
# ==========================================


def execute_download_with_retry(
    client: httpx.Client, url: str, temp_path: Path, expected_hash: Optional[str] = None
) -> None:
    """
    Handles the retry loop for downloading a file and verifying its integrity.

    Args:
        client (httpx.Client): The HTTP client instance.
        url (str): The absolute URL of the file.
        temp_path (Path): The temporary path for the download.
        expected_hash (Optional[str]): An optional SHA-256 hash for verification.

    Raises:
        Exception: If the download fails after all retry attempts.
    """
    filename = url.split("/")[-1]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Downloading {filename} (Attempt {attempt}/{MAX_RETRIES})...")
            stream_to_disk(client, url, temp_path)

            if expected_hash and not verify_checksum(temp_path, expected_hash):
                logger.warning(f"Checksum verification failed for {filename}")
            return  # Success

        except (httpx.HTTPError, ValueError, IOError, NetworkError) as e:
            logger.warning(f"Attempt {attempt} failed for {filename}: {e}")
            if temp_path.exists():
                temp_path.unlink()

            if attempt == MAX_RETRIES:
                logger.error(f"Maximum retry attempts reached for {filename}.")
                raise

            # Exponential backoff
            time.sleep(RETRY_DELAY * attempt)


# ==========================================
# 4. HIGH-LEVEL COORDINATOR (Facade)
# ==========================================


def download_file(
    url: str, download_dir: Path, expected_hash: Optional[str] = None
) -> Optional[Tuple[Path, str]]:
    """
    Coordinates the idempotent download process.

    Args:
        url (str): The absolute URL of the file to download.
        download_dir (Path): The directory where the file should be stored.
        expected_hash (Optional[str]): An optional SHA-256 hash for integrity verification.

    Returns:
        Optional[Tuple[Path, str]]: A tuple containing the path to the downloaded file and its computed SHA-256 hash,
        or None if access to the file was forbidden.

    Raises:
        RuntimeError: If remote metadata cannot be retrieved.
        NetworkError: If a network connection failure occurs.
        Exception: If the download fails after all retry attempts.
    """

    # Ensure the download directory exists
    download_dir.mkdir(parents=True, exist_ok=True)

    filename = url.split("/")[-1]
    target_path = download_dir / filename
    temp_path = target_path.with_suffix(".tmp")

    with httpx.Client(follow_redirects=True, timeout=None) as client:
        # Step 1: Idempotency Check
        try:
            remote_size = get_remote_size(client, url)
        except (FileForbiddenError, RemoteFileNotFoundError) as e:
            logger.warning(e)
            return None

        if remote_size is None:
            raise RuntimeError(f"Could not determine remote size for: {url}")

        if not is_download_required(target_path, remote_size):
            return target_path, compute_sha256(target_path)

        # Step 2: Execute Download with Retry Logic
        execute_download_with_retry(client, url, temp_path, expected_hash)

        # Step 3: Atomic Finalization
        temp_path.replace(target_path)
        logger.info(f"Successfully finalized download: {filename}")

    return target_path, compute_sha256(target_path)
