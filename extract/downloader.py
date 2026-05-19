import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from extract.hasher import Hasher

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


@dataclass
class DownloadResult:
    """Holds the outcome of a file download.

    Attributes:
        file_path: The path to the downloaded file.
        hash_value: The hash digest of the file content.
        hash_type: The algorithm used to compute the hash.
    """

    file_path: Path
    hash_value: str
    hash_type: str


MAX_RETRIES = 3
RETRY_DELAY = 2


def get_remote_size(client: httpx.Client, url: str) -> Optional[int]:
    """Retrieves the remote file size using an HTTP HEAD request.

    Args:
        client: The HTTP client instance.
        url: The absolute URL of the file.

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
    """Downloads the file content via streaming and writes it to a temporary file.

    Args:
        client: The HTTP client instance.
        url: The absolute URL of the file.
        temp_path: The temporary path where the file will be written.
    """
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with open(temp_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)


def is_download_required(target_path: Path, remote_size: int) -> bool:
    """Determines if a download is necessary based on file existence and size.

    Args:
        target_path: The final target path of the file.
        remote_size: The expected size of the file on the remote server.

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


def execute_download_with_retry(
    client: httpx.Client,
    url: str,
    temp_path: Path,
    hasher: Hasher,
    expected_hash: Optional[str] = None,
) -> None:
    """Handles the retry loop for downloading a file and verifying its integrity.

    Args:
        client: The HTTP client instance.
        url: The absolute URL of the file.
        temp_path: The temporary path for the download.
        hasher: A Hasher instance to compute the file hash.
        expected_hash: Optional expected hash for integrity verification.

    Raises:
        Exception: If the download fails after all retry attempts.
    """
    filename = url.split("/")[-1]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Downloading {filename} (Attempt {attempt}/{MAX_RETRIES})...")
            stream_to_disk(client, url, temp_path)

            actual_hash = hasher.hash(temp_path)
            if expected_hash and actual_hash != expected_hash:
                logger.warning(
                    f"Checksum mismatch for {filename}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
            return

        except (httpx.HTTPError, ValueError, IOError, NetworkError) as e:
            logger.warning(f"Attempt {attempt} failed for {filename}: {e}")
            if temp_path.exists():
                temp_path.unlink()

            if attempt == MAX_RETRIES:
                logger.error(f"Maximum retry attempts reached for {filename}.")
                raise

            time.sleep(RETRY_DELAY * attempt)


def download_file(
    url: str,
    download_dir: Path,
    hasher: Hasher,
    expected_hash: Optional[str] = None,
) -> Optional[DownloadResult]:
    """Coordinates the idempotent download process.

    Args:
        url: The absolute URL of the file to download.
        download_dir: The directory where the file should be stored.
        hasher: A Hasher instance to compute the file hash.
        expected_hash: Optional expected hash for integrity verification.

    Returns:
        Optional[DownloadResult]: The download result, or None if access was forbidden.

    Raises:
        RuntimeError: If remote metadata cannot be retrieved.
        NetworkError: If a network connection failure occurs.
        Exception: If the download fails after all retry attempts.
    """
    download_dir.mkdir(parents=True, exist_ok=True)

    filename = url.split("/")[-1]
    target_path = download_dir / filename
    temp_path = target_path.with_suffix(".tmp")

    with httpx.Client(follow_redirects=True, timeout=None) as client:
        try:
            remote_size = get_remote_size(client, url)
        except (FileForbiddenError, RemoteFileNotFoundError) as e:
            logger.warning(e)
            return None

        if remote_size is None:
            raise RuntimeError(f"Could not determine remote size for: {url}")

        if not is_download_required(target_path, remote_size):
            hash_value = hasher.hash(target_path)
            return DownloadResult(
                file_path=target_path,
                hash_value=hash_value,
                hash_type=hasher.algorithm,
            )

        execute_download_with_retry(client, url, temp_path, hasher, expected_hash)

        temp_path.replace(target_path)
        logger.info(f"Successfully finalized download: {filename}")

    hash_value = hasher.hash(target_path)
    return DownloadResult(
        file_path=target_path,
        hash_value=hash_value,
        hash_type=hasher.algorithm,
    )
