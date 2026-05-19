import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv

from extract.downloader import DownloadResult
from extract.hasher import Hasher
from extract.parser import generate_parquet_urls
from upload.uploader import UploadResult, UploadStatus, upload_file

load_dotenv()

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
