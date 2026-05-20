import logging
from pathlib import Path
from typing import Optional

from extract.downloader import DownloadResult, download_file
from extract.hasher import Hasher
from orchestrator.result import FileOutcome, FileStatus, _classify_file
from upload.uploader import UploadResult, UploadStatus, upload_file

logger = logging.getLogger(__name__)


class FileProcessor:
    """Handles file download and upload operations."""

    def __init__(self, download_dir: Path, hasher: Hasher):
        self.download_dir = download_dir
        self.hasher = hasher

    def process_file(
        self,
        url: str,
        bucket_name: str,
        bucket_path_prefix: str,
    ) -> FileOutcome:
        """Process a single file: download, then upload.

        Args:
            url: The URL of the file to download.
            bucket_name: Name of the S3 bucket.
            bucket_path_prefix: Prefix for the bucket path.

        Returns:
            FileOutcome with the result of the operation.
        """
        filename = url.split("/")[-1]
        logger.info(f"Processing {filename}")

        try:
            download_result = self._download(url)
        except Exception as e:
            logger.error(f"Download failed for {filename}: {e}")
            return _classify_file(url, error_message=str(e))

        if download_result is None:
            logger.warning(f"Skipping {filename}: access denied or not found")
            return _classify_file(url, error_message="forbidden or not found")

        bucket_path = f"{bucket_path_prefix}{filename}"
        upload_result = self._upload(
            source_path=str(download_result.file_path),
            bucket_path=bucket_path,
            file_hash=download_result.hash_value,
            hash_type=download_result.hash_type,
            bucket_name=bucket_name,
        )

        return _classify_file(
            url=url,
            download_result=download_result,
            upload_result=upload_result,
        )

    def _download(self, url: str) -> Optional[DownloadResult]:
        """Download a file from URL.

        Args:
            url: The URL of the file to download.

        Returns:
            DownloadResult if successful, None if access denied.
        """
        try:
            return download_file(url, self.download_dir, self.hasher)
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            raise

    def _upload(
        self,
        source_path: str,
        bucket_path: str,
        file_hash: str,
        hash_type: str,
        bucket_name: str,
    ) -> UploadResult:
        """Upload a file to S3.

        Args:
            source_path: Local path to the file.
            bucket_path: Destination key in the bucket.
            file_hash: Hash of the file.
            hash_type: Hash algorithm used.
            bucket_name: Name of the S3 bucket.

        Returns:
            UploadResult with the outcome.
        """
        return upload_file(
            source_path=source_path,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
            bucket_name=bucket_name,
        )
