import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional

from extract.downloader import DownloadResult, download_file
from extract.hasher import Hasher, Sha256Hasher
from extract.parser import generate_parquet_urls
from upload.uploader import UploadResult, UploadStatus, upload_file

logger = logging.getLogger(__name__)


class FileStatus(Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    DOWNLOAD_FAILED = "download_failed"
    DOWNLOAD_ERROR = "download_error"
    UPLOAD_FAILED = "upload_failed"


@dataclass
class FileOutcome:
    url: str
    status: FileStatus
    download_result: Optional[DownloadResult] = None
    upload_result: Optional[UploadResult] = None
    error_message: str = ""


@dataclass
class PipelineResult:
    total: int
    succeeded: int
    skipped: int
    failed: int
    files: List[FileOutcome] = field(default_factory=list)


def _classify_file(
    url: str,
    download_result: Optional[DownloadResult] = None,
    upload_result: Optional[UploadResult] = None,
    error_message: str = "",
) -> FileOutcome:
    if download_result is None:
        status = FileStatus.DOWNLOAD_FAILED
    elif upload_result is not None and upload_result.status is UploadStatus.ERROR:
        status = FileStatus.UPLOAD_FAILED
    elif upload_result is not None and upload_result.status is UploadStatus.SKIPPED:
        status = FileStatus.SKIPPED
    elif upload_result is not None:
        status = FileStatus.SUCCESS
    else:
        status = FileStatus.DOWNLOAD_FAILED
    return FileOutcome(
        url=url,
        status=status,
        download_result=download_result,
        upload_result=upload_result,
        error_message=error_message,
    )


def run_pipeline(
    hasher: Hasher = Sha256Hasher(),
    datasets: Optional[Iterable[str]] = None,
    years: Optional[Iterable[int]] = None,
    months: Optional[Iterable[int]] = None,
    download_dir: Path = Path("/tmp/nyc_taxi_data"),
    bucket_name: str = "raw-data",
    bucket_path_prefix: str = "",
) -> PipelineResult:
    urls = generate_parquet_urls(datasets=datasets, years=years, months=months)

    if not urls:
        logger.warning("No URLs generated. Nothing to process.")
        return PipelineResult(total=0, succeeded=0, skipped=0, failed=0)

    outcomes: List[FileOutcome] = []
    succeeded = 0
    skipped = 0
    failed = 0

    for i, url in enumerate(urls):
        logger.info(f"[{i + 1}/{len(urls)}] Processing {url}")
        filename = url.split("/")[-1]

        try:
            download_result = download_file(url, download_dir, hasher)
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            outcomes.append(
                FileOutcome(
                    url=url,
                    status=FileStatus.DOWNLOAD_ERROR,
                    error_message=str(e),
                )
            )
            failed += 1
            continue

        if download_result is None:
            logger.warning(f"Skipping {filename}: access denied or not found")
            outcomes.append(
                _classify_file(url, error_message="forbidden or not found")
            )
            failed += 1
            continue

        bucket_path = f"{bucket_path_prefix}{filename}"
        upload_result = upload_file(
            source_path=str(download_result.file_path),
            bucket_path=bucket_path,
            file_hash=download_result.hash_value,
            hash_type=download_result.hash_type,
            bucket_name=bucket_name,
        )

        if upload_result.status is UploadStatus.ERROR:
            logger.error(f"Upload failed for {filename}: {upload_result.error_message}")
            outcomes.append(
                _classify_file(
                    url,
                    download_result=download_result,
                    upload_result=upload_result,
                    error_message=upload_result.error_message,
                )
            )
            failed += 1
            continue

        if upload_result.status is UploadStatus.SKIPPED:
            logger.info(f"Skipped {filename}: already exists with same hash")
            outcomes.append(
                _classify_file(
                    url,
                    download_result=download_result,
                    upload_result=upload_result,
                )
            )
            skipped += 1
            continue

        logger.info(f"Successfully processed {filename}")
        outcomes.append(
            _classify_file(
                url,
                download_result=download_result,
                upload_result=upload_result,
            )
        )
        succeeded += 1

    return PipelineResult(
        total=len(urls),
        succeeded=succeeded,
        skipped=skipped,
        failed=failed,
        files=outcomes,
    )
