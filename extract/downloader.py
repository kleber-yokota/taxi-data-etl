import os
import httpx
from pathlib import Path
from typing import List, Iterable
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_file(url: str, download_dir: Path) -> Path:
    """
    Downloads a Parquet file idempotently.
    If the file exists locally and the size matches the remote Content-Length,
    the download is skipped.

    Args:
        url (str): The absolute URL of the file to download.
        download_dir (Path): The local directory where the file will be stored.

    Returns:
        Path: The path to the downloaded file.
    """
    filename = url.split("/")[-1]
    target_path = download_dir / filename
    
    with httpx.Client(follow_redirects=True, timeout=None) as client:
        try:
            head_response = client.head(url)
            head_response.raise_for_status()
            remote_size = int(head_response.headers.get("Content-Length", 0))
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"Error retrieving metadata for {filename}: {e}")
            raise

        if target_path.exists():
            local_size = target_path.stat().st_size
            if local_size == remote_size:
                logger.info(f"File {filename} already exists and is complete. Skipping download.")
                return target_path
            else:
                logger.warning(f"File {filename} exists but size differs. Re-downloading...")

        logger.info(f"Downloading {filename} (Approx. {remote_size / 1024 / 1024:.2f} MB)...")
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
    
    return target_path

def download_all(urls: Iterable[str], download_dir: str = "data/raw") -> List[Path]:
    """
    Downloads all provided URLs to the specified directory.

    Args:
        urls (Iterable[str]): An iterable of absolute URLs to download.
        download_dir (str): The local directory where files will be stored.

    Returns:
        List[Path]: A list of paths to the successfully downloaded files.
    """
    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)
    
    downloaded_files = []
    for url in urls:
        try:
            path = download_file(url, download_path)
            downloaded_files.append(path)
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            
    return downloaded_files
