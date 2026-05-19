import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from upload.uploader import UploadStatus, upload_file


@pytest.fixture
def temp_file():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as f:
        f.write(b"fake parquet content")
        tmp_path = f.name
    yield tmp_path
    os.unlink(tmp_path)


@pytest.fixture
def s3_client_mock():
    with patch("upload.uploader._build_s3_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


def make_client_error(code: str, message: str = "error") -> ClientError:
    error_response = {
        "Error": {"Code": code, "Message": message},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }
    return ClientError(error_response, "HeadObject")


def test_success(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = make_client_error("404")

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abcdef123456",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SUCCESS
    assert result.file_name == "yellow_tripdata_2024-01.parquet"
    assert result.original_path == temp_file
    assert result.hash_value == "abcdef123456"
    assert result.hash_type == "sha256"
    assert result.error_message == ""
    s3_client_mock.upload_file.assert_called_once()


def test_skipped_when_hash_matches(temp_file, s3_client_mock):
    s3_client_mock.head_object.return_value = {
        "Metadata": {"hash": "abcdef123456", "hash_type": "sha256"}
    }

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abcdef123456",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SKIPPED
    assert result.file_name == "yellow_tripdata_2024-01.parquet"
    assert result.original_path == temp_file
    assert result.hash_value == "abcdef123456"
    assert result.hash_type == "sha256"
    s3_client_mock.upload_file.assert_not_called()


def test_upload_when_hash_differs(temp_file, s3_client_mock):
    s3_client_mock.head_object.return_value = {
        "Metadata": {"hash": "oldhash", "hash_type": "sha256"}
    }

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="newhash",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SUCCESS
    s3_client_mock.upload_file.assert_called_once()


def test_upload_when_no_metadata(temp_file, s3_client_mock):
    s3_client_mock.head_object.return_value = {}

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="newhash",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SUCCESS
    s3_client_mock.upload_file.assert_called_once()


def test_source_not_found(s3_client_mock):
    result = upload_file(
        source_path="/tmp/nonexistent/file.parquet",
        bucket_path="raw/2024/file.parquet",
        file_hash="abc123",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.ERROR
    assert "Source file not found" in result.error_message
    assert result.file_name == "file.parquet"
    s3_client_mock.upload_file.assert_not_called()


def test_network_error_on_head(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = BotoCoreError()

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abcdef123456",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.ERROR
    assert "Failed to check remote object" in result.error_message


def test_network_error_on_upload(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = make_client_error("404")
    s3_client_mock.upload_file.side_effect = BotoCoreError()

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abcdef123456",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.ERROR
    assert "Upload failed" in result.error_message


def test_head_object_403_raises(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = make_client_error("403")

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/yellow_tripdata_2024-01.parquet",
        file_hash="abcdef123456",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.ERROR
    assert "Failed to check remote object" in result.error_message


def test_bucket_path_with_filename(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = make_client_error("404")

    result = upload_file(
        source_path=temp_file,
        bucket_path="data/file.parquet",
        file_hash="abc",
        bucket_name="raw-data",
    )

    assert result.file_name == "file.parquet"


def test_upload_includes_metadata(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = make_client_error("404")

    upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/test.parquet",
        file_hash="mysha256hash",
        bucket_name="raw-data",
    )

    s3_client_mock.upload_file.assert_called_once_with(
        str(Path(temp_file)),
        "raw-data",
        "raw/2024/test.parquet",
        ExtraArgs={"Metadata": {"hash": "mysha256hash", "hash_type": "sha256"}},
    )


def test_upload_custom_hash_type(temp_file, s3_client_mock):
    s3_client_mock.head_object.side_effect = make_client_error("404")

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/test.parquet",
        file_hash="md5hash123",
        hash_type="md5",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SUCCESS
    assert result.hash_value == "md5hash123"
    assert result.hash_type == "md5"

    s3_client_mock.upload_file.assert_called_once_with(
        str(Path(temp_file)),
        "raw-data",
        "raw/2024/test.parquet",
        ExtraArgs={"Metadata": {"hash": "md5hash123", "hash_type": "md5"}},
    )


def test_skipped_custom_hash_type(temp_file, s3_client_mock):
    s3_client_mock.head_object.return_value = {
        "Metadata": {"hash": "abc", "hash_type": "sha1"}
    }

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/test.parquet",
        file_hash="abc",
        hash_type="sha1",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SKIPPED
    s3_client_mock.upload_file.assert_not_called()


def test_not_skipped_when_hash_type_differs(temp_file, s3_client_mock):
    s3_client_mock.head_object.return_value = {
        "Metadata": {"hash": "abc", "hash_type": "sha256"}
    }

    result = upload_file(
        source_path=temp_file,
        bucket_path="raw/2024/test.parquet",
        file_hash="abc",
        hash_type="md5",
        bucket_name="raw-data",
    )

    assert result.status is UploadStatus.SUCCESS
    s3_client_mock.upload_file.assert_called_once()
