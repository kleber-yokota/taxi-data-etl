import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class UploadStatus(Enum):
    """Represents the result status of an upload operation."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class UploadResult:
    """Holds the outcome of a file upload to S3-compatible storage.

    Attributes:
        file_name: The name of the file extracted from the bucket path.
        original_path: The local source path of the uploaded file.
        status: The final status (SUCCESS, SKIPPED, or ERROR).
        hash_value: The hash digest provided for the file.
        hash_type: The hash algorithm used (e.g. sha256, md5).
        error_message: A description of the error, if status is ERROR.
    """

    file_name: str
    original_path: str
    status: UploadStatus
    hash_value: str = ""
    hash_type: str = ""
    error_message: str = ""


class UploadError(Exception):
    """Raised when the S3 client cannot be built due to missing configuration."""

    pass


def _extract_file_info(source_path: str, bucket_path: str) -> tuple[Path, str]:
    """Parse source and bucket paths into a Path object and file name.

    Args:
        source_path: Local filesystem path to the file.
        bucket_path: Destination key inside the bucket (includes file name).

    Returns:
        A tuple of (source Path, file name string).
    """
    source = Path(source_path)
    file_name = bucket_path.rstrip("/").split("/")[-1]
    return source, file_name


def _build_s3_client() -> boto3.client:
    """Create a boto3 S3 client configured for an S3-compatible service.

    Reads configuration from environment variables:
        AWS_ENDPOINT_URL  (required)
        AWS_ACCESS_KEY_ID
        AWS_SECRET_ACCESS_KEY
        AWS_REGION         (default: us-east-1)

    Returns:
        A configured boto3 S3 client.

    Raises:
        UploadError: If AWS_ENDPOINT_URL is not set.
    """
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint_url:
        raise UploadError(
            "AWS_ENDPOINT_URL environment variable is required for S3-compatible "
            "storage (e.g. Garage, MinIO)."
        )

    config = BotoConfig(
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        signature_version="v4",
        retries={"max_attempts": 3, "mode": "standard"},
    )

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        config=config,
    )


def _get_remote_metadata(
    s3_client: boto3.client, bucket: str, key: str
) -> Optional[dict]:
    """Fetch metadata from an existing S3 object, if it exists.

    Args:
        s3_client: An active boto3 S3 client.
        bucket: The bucket name.
        key: The object key.

    Returns:
        The Metadata dict if the object exists, None if it does not (404),
        or raises ClientError for other HTTP errors (e.g. 403).
    """
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        return response.get("Metadata", {})
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return None
        raise


def _do_upload(
    s3_client: boto3.client,
    source: Path,
    bucket: str,
    key: str,
    file_hash: str,
    hash_type: str,
) -> None:
    """Upload a local file to S3-compatible storage with hash metadata.

    Args:
        s3_client: An active boto3 S3 client.
        source: Local Path to the file to upload.
        bucket: Target bucket name.
        key: Target object key inside the bucket.
        file_hash: Hash digest of the file content.
        hash_type: Algorithm used to compute the hash (e.g. sha256).

    Raises:
        ClientError: If the S3 service returns an error.
        BotoCoreError: If a network or client configuration error occurs.
    """
    s3_client.upload_file(
        str(source),
        bucket,
        key,
        ExtraArgs={"Metadata": {"hash": file_hash, "hash_type": hash_type}},
    )


def upload_file(
    source_path: str,
    bucket_path: str,
    file_hash: str,
    hash_type: str = "sha256",
    bucket_name: str = "raw-data",
) -> UploadResult:
    """Upload a file to an S3-compatible bucket with deduplication by hash.

    The function checks whether an object already exists at the given
    bucket path. If it does and both the stored hash and hash type match
    the provided values, the upload is skipped.

    Args:
        source_path: Local path to the file to upload.
        bucket_path: Destination key inside the bucket (must include file name).
        file_hash: Hash digest of the file content.
        hash_type: Algorithm used for file_hash (default: sha256).
        bucket_name: Target S3 bucket name (default: raw-data).

    Returns:
        An UploadResult with the outcome of the operation.
    """
    source, file_name = _extract_file_info(source_path, bucket_path)

    if not source.is_file():
        return UploadResult(
            file_name=file_name,
            original_path=source_path,
            status=UploadStatus.ERROR,
            error_message=f"Source file not found: {source_path}",
        )

    try:
        s3_client = _build_s3_client()
    except UploadError as e:
        return UploadResult(
            file_name=file_name,
            original_path=source_path,
            status=UploadStatus.ERROR,
            error_message=str(e),
        )

    try:
        existing_metadata = _get_remote_metadata(s3_client, bucket_name, bucket_path)
    except (ClientError, BotoCoreError) as e:
        return UploadResult(
            file_name=file_name,
            original_path=source_path,
            status=UploadStatus.ERROR,
            error_message=f"Failed to check remote object: {e}",
        )

    if existing_metadata is not None:
        if (
            existing_metadata.get("hash") == file_hash
            and existing_metadata.get("hash_type") == hash_type
        ):
            logger.info(
                "File %s already exists with the same hash. Skipping upload.",
                bucket_path,
            )
            return UploadResult(
                file_name=file_name,
                original_path=source_path,
                status=UploadStatus.SKIPPED,
                hash_value=file_hash,
                hash_type=hash_type,
            )

    try:
        _do_upload(s3_client, source, bucket_name, bucket_path, file_hash, hash_type)
    except (ClientError, BotoCoreError) as e:
        return UploadResult(
            file_name=file_name,
            original_path=source_path,
            status=UploadStatus.ERROR,
            error_message=f"Upload failed: {e}",
        )

    logger.info(
        "Successfully uploaded %s to s3://%s/%s", file_name, bucket_name, bucket_path
    )
    return UploadResult(
        file_name=file_name,
        original_path=source_path,
        status=UploadStatus.SUCCESS,
        hash_value=file_hash,
        hash_type=hash_type,
    )
