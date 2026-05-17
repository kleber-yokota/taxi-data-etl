import os
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Set
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TLCDownloader:
    """
    Responsible for extracting Parquet file links from the NYC TLC website
    and downloading them idempotently.
    """
    
    def __init__(self, base_url: str, download_dir: str = "data/raw"):
        """
        Initialize the downloader.

        Args:
            base_url (str): The URL of the NYC TLC trip record data page.
            download_dir (str): The local directory where files will be stored.
        """
        self.base_url = base_url
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # Use a synchronous httpx client. 
        # Timeout is set to None for the main client to avoid timeouts on large files.
        self.client = httpx.Client(follow_redirects=True, timeout=None)

    def fetch_parquet_urls(self) -> Set[str]:
        """
        Scrapes the NYC TLC page to find all links ending in .parquet.

        Returns:
            Set[str]: A set of absolute URLs to Parquet files.
        """
        logger.info(f"Fetching Parquet URLs from: {self.base_url}")
        response = self.client.get(self.base_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        links = set()
        
        for a in soup.find_all("a", href=True):
            url = a["href"]
            if url.endswith(".parquet"):
                if url.startswith("/"):
                    url = f"https://www.nyc.gov{url}"
                links.add(url)
                
        logger.info(f"Found {len(links)} Parquet files.")
        return links

    def download_file(self, url: str) -> Path:
        """
        Downloads a Parquet file idempotently.
        If the file exists locally and the size matches the remote Content-Length,
        the download is skipped.

        Args:
            url (str): The absolute URL of the file to download.

        Returns:
            Path: The path to the downloaded file.
        """
        filename = url.split("/")[-1]
        target_path = self.download_dir / filename
        
        try:
            head_response = self.client.head(url)
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
        with self.client.stream("GET", url) as response:
            response.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        
        return target_path

    def run(self) -> List[Path]:
        """
        Orchestrates the extraction of all available files.

        Returns:
            List[Path]: A list of paths to the downloaded files.
        """
        urls = self.fetch_parquet_urls()
        downloaded_files = []
        
        for url in urls:
            try:
                path = self.download_file(url)
                downloaded_files.append(path)
            except Exception as e:
                logger.error(f"Failed to download {url}: {e}")
                
        return downloaded_files
