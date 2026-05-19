import hashlib
import os
import tempfile
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from testcontainers.minio import MinioContainer

from upload.uploader import UploadStatus, upload_file

BUCKET_NAME = "raw-data"


@pytest.fixture(scope="module")
def minio_container():
    with MinioContainer() as container:
        yield container


@pytest.fixture(scope="module")
def s3_endpoint(minio_container):
    host = minio_container.get_container_host_ip()
    port = minio_container.get_exposed_port(minio_container.port)
    return f"http://{host}:{port}"


@pytest.fixture(scope="module")
def minio_credentials(minio_container):
    return {
        "access_key": minio_container.access_key,
        "secret_key": minio_container.secret_key,
    }


@pytest.fixture(scope="module")
def setup_bucket(s3_endpoint, minio_credentials):
    client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=minio_credentials["access_key"],
        aws_secret_access_key=minio_credentials["secret_key"],
    )
    client.create_bucket(Bucket=BUCKET_NAME)
    yield client
    # Teardown: remove all objects and delete bucket
    try:
        objects = client.list_objects_v2(Bucket=BUCKET_NAME)
        if objects.get("Contents"):
            client.delete_objects(
                Bucket=BUCKET_NAME,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects["Contents"]]},
            )
        client.delete_bucket(Bucket=BUCKET_NAME)
    except ClientError:
        pass


@pytest.fixture
def temp_file():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as f:
        f.write(b"fake parquet content for e2e test")
        tmp_path = f.name
    yield tmp_path
    os.unlink(tmp_path)


@pytest.fixture
def env_vars(s3_endpoint, minio_credentials):
    old = {
        "AWS_ENDPOINT_URL": os.environ.get("AWS_ENDPOINT_URL"),
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    }
    os.environ["AWS_ENDPOINT_URL"] = s3_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = minio_credentials["access_key"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = minio_credentials["secret_key"]
    yield
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class TestUploaderE2E:
    """End-to-end tests for upload_file using a real MinIO container."""

    def test_upload_success(self, temp_file, env_vars, setup_bucket):
        result = upload_file(
            source_path=temp_file,
            bucket_path="e2e/success/yellow_tripdata_2024-01.parquet",
            file_hash="abcdef123456",
            bucket_name=BUCKET_NAME,
        )

        assert result.status is UploadStatus.SUCCESS
        assert result.file_name == "yellow_tripdata_2024-01.parquet"
        assert result.original_path == temp_file
        assert result.hash_value == "abcdef123456"
        assert result.hash_type == "sha256"

    def test_upload_skipped_when_hash_matches(self, temp_file, env_vars, setup_bucket):
        bucket_path = "e2e/skipped/yellow_tripdata_2024-01.parquet"
        file_hash = "abcdef123456"

        result1 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            bucket_name=BUCKET_NAME,
        )
        assert result1.status is UploadStatus.SUCCESS

        result2 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            bucket_name=BUCKET_NAME,
        )
        assert result2.status is UploadStatus.SKIPPED
        assert result2.hash_value == file_hash
        assert result2.hash_type == "sha256"

    def test_upload_when_hash_differs(self, temp_file, env_vars, setup_bucket):
        bucket_path = "e2e/differs/yellow_tripdata_2024-01.parquet"
        file_hash = "abcdef123456"

        result1 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            bucket_name=BUCKET_NAME,
        )
        assert result1.status is UploadStatus.SUCCESS

        result2 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash="differenthash",
            bucket_name=BUCKET_NAME,
        )
        assert result2.status is UploadStatus.SUCCESS
        assert result2.hash_value == "differenthash"

    def test_upload_custom_hash_type(self, temp_file, env_vars, setup_bucket):
        bucket_path = "e2e/custom-hash/yellow_tripdata_2024-01.parquet"
        file_hash = "md5hash123"
        hash_type = "md5"

        result = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
            bucket_name=BUCKET_NAME,
        )

        assert result.status is UploadStatus.SUCCESS
        assert result.hash_value == file_hash
        assert result.hash_type == hash_type

    def test_upload_skipped_custom_hash_type(self, temp_file, env_vars, setup_bucket):
        bucket_path = "e2e/skipped-custom/yellow_tripdata_2024-01.parquet"
        file_hash = "abc123"
        hash_type = "sha1"

        result1 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
            bucket_name=BUCKET_NAME,
        )
        assert result1.status is UploadStatus.SUCCESS

        result2 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
            bucket_name=BUCKET_NAME,
        )
        assert result2.status is UploadStatus.SKIPPED
        assert result2.hash_value == file_hash
        assert result2.hash_type == hash_type

    def test_not_skipped_when_hash_type_differs(self, temp_file, env_vars, setup_bucket):
        bucket_path = "e2e/type-differs/yellow_tripdata_2024-01.parquet"
        file_hash = "abc"

        result1 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type="sha256",
            bucket_name=BUCKET_NAME,
        )
        assert result1.status is UploadStatus.SUCCESS

        result2 = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type="md5",
            bucket_name=BUCKET_NAME,
        )
        assert result2.status is UploadStatus.SUCCESS
        assert result2.hash_type == "md5"

    def test_source_not_found(self, env_vars, setup_bucket):
        result = upload_file(
            source_path="/tmp/nonexistent/file.parquet",
            bucket_path="e2e/notfound/file.parquet",
            file_hash="abc123",
            bucket_name=BUCKET_NAME,
        )

        assert result.status is UploadStatus.ERROR
        assert "Source file not found" in result.error_message
        assert result.file_name == "file.parquet"

    def test_upload_verify_content(self, temp_file, env_vars, setup_bucket):
        bucket_path = "e2e/verify/data.parquet"

        result = upload_file(
            source_path=temp_file,
            bucket_path=bucket_path,
            file_hash="verifycontent123",
            bucket_name=BUCKET_NAME,
        )
        assert result.status is UploadStatus.SUCCESS

        client = boto3.client(
            "s3",
            endpoint_url=os.environ["AWS_ENDPOINT_URL"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        )

        response = client.get_object(Bucket=BUCKET_NAME, Key=bucket_path)
        content = response["Body"].read()
        assert content == b"fake parquet content for e2e test"

        metadata = response.get("Metadata", {})
        assert metadata.get("hash") == "verifycontent123"
        assert metadata.get("hash_type") == "sha256"
