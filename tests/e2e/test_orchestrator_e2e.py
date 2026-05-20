import hashlib
import logging
import os
from pathlib import Path

import boto3
import pytest
import vcr as vcrpy
from botocore.exceptions import ClientError
from testcontainers.minio import MinioContainer

from extract.hasher import Sha256Hasher
from extract.parser import generate_parquet_urls
from orchestrator import FileStatus, PipelineOrchestrator

CASSETTE_DIR = Path("tests/e2e/cassettes")
TEST_URL = generate_parquet_urls(datasets=["yellow"], years=[2015], months=[1])[0]
SAMPLE_BYTES = 5 * 1024 * 1024

BUCKET_NAME = "raw-data"

vcr = vcrpy.VCR(
    cassette_library_dir=str(CASSETTE_DIR),
    record_mode="none",
    ignore_hosts=["localhost"],
)


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


def test_pipeline_e2e_success(tmp_path, env_vars, setup_bucket):
    download_dir = tmp_path / "downloads"
    hasher = Sha256Hasher()

    with vcr.use_cassette("downloader_success.yaml"):
        orchestrator = PipelineOrchestrator(hasher=hasher, download_dir=download_dir, bucket_name=BUCKET_NAME)
        result = orchestrator.run(
            datasets=["yellow"],
            years=[2015],
            months=[1],

            bucket_name=BUCKET_NAME,
        )

    assert result.total == 1
    assert result.succeeded == 1
    assert result.skipped == 0
    assert result.failed == 0

    outcome = result.files[0]
    assert outcome.status == FileStatus.SUCCESS
    assert outcome.url == TEST_URL
    assert outcome.download_result is not None
    assert outcome.upload_result is not None
    assert outcome.upload_result.status.value == "success"

    downloaded_file = outcome.download_result.file_path
    assert downloaded_file.exists()
    assert downloaded_file.stat().st_size <= SAMPLE_BYTES

    content = downloaded_file.read_bytes()
    assert outcome.download_result.hash_value == hashlib.sha256(content).hexdigest()

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["AWS_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )

    bucket_path = downloaded_file.name
    response = client.get_object(Bucket=BUCKET_NAME, Key=bucket_path)
    uploaded_content = response["Body"].read()
    assert uploaded_content == content

    metadata = response.get("Metadata", {})
    assert metadata.get("hash") == outcome.download_result.hash_value
    assert metadata.get("hash_type") == "sha256"


def test_pipeline_e2e_skipped_on_duplicate(tmp_path, env_vars, setup_bucket):
    download_dir = tmp_path / "downloads_dup"
    hasher = Sha256Hasher()

    with vcr.use_cassette("downloader_success.yaml"):
        orchestrator = PipelineOrchestrator(hasher=hasher, download_dir=download_dir, bucket_name=BUCKET_NAME)
        result1 = orchestrator.run(
            datasets=["yellow"],
            years=[2015],
            months=[1],
            bucket_name=BUCKET_NAME,
        )

    assert result1.total == 1
    assert result1.skipped == 1
    assert result1.files[0].status == FileStatus.SKIPPED


def test_pipeline_e2e_not_found(tmp_path, env_vars, setup_bucket, caplog):
    download_dir = tmp_path / "downloads_nf"
    hasher = Sha256Hasher()

    with caplog.at_level(logging.WARNING):
        with vcr.use_cassette("downloader_not_found.yaml"):
            orchestrator = PipelineOrchestrator(hasher=hasher, download_dir=download_dir, bucket_name=BUCKET_NAME)
            result = orchestrator.run(
                datasets=["yellow"],
                years=[2015],
                months=[1],

                bucket_name=BUCKET_NAME,
            )

    assert result.total == 1
    assert result.failed == 1
    assert result.files[0].status == FileStatus.DOWNLOAD_FAILED


def test_pipeline_e2e_forbidden(tmp_path, env_vars, setup_bucket, caplog):
    download_dir = tmp_path / "downloads_fb"
    hasher = Sha256Hasher()

    with caplog.at_level(logging.WARNING):
        with vcr.use_cassette("downloader_forbidden.yaml"):
            orchestrator = PipelineOrchestrator(hasher=hasher, download_dir=download_dir, bucket_name=BUCKET_NAME)
            result = orchestrator.run(
                datasets=["yellow"],
                years=[2015],
                months=[1],

                bucket_name=BUCKET_NAME,
            )

    assert result.total == 1
    assert result.failed == 1
    assert result.files[0].status == FileStatus.DOWNLOAD_FAILED
