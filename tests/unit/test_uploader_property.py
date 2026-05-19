from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from upload.uploader import (
    UploadResult,
    UploadStatus,
    _extract_file_info,
    upload_file,
)


def _has_aws_env() -> bool:
    """Check whether real AWS credentials are set."""
    import os
    return bool(os.environ.get("AWS_ENDPOINT_URL"))


# ── _extract_file_info ────────────────────────────────────────────────────────


class TestExtractFileInfo:
    @given(source_path=st.text(), bucket_path=st.text())
    def test_returns_tuple_with_path_and_str(self, source_path, bucket_path):
        source, file_name = _extract_file_info(source_path, bucket_path)
        assert isinstance(source, Path)
        assert isinstance(file_name, str)

    @given(source_path=st.text(), bucket_path=st.text())
    def test_file_name_from_bucket_path(self, source_path, bucket_path):
        _, file_name = _extract_file_info(source_path, bucket_path)
        expected = bucket_path.rstrip("/").split("/")[-1]
        assert file_name == expected

    @given(source_path=st.text(), bucket_path=st.text())
    def test_source_path_preserved(self, source_path, bucket_path):
        source, _ = _extract_file_info(source_path, bucket_path)
        # Path normalizes input (e.g. "//" -> "/", "" -> "."), so compare as Path
        assert source == Path(source_path)

    @given(
        source_path=st.text(min_size=1),
        bucket_path=st.just("single_file.parquet"),
    )
    def test_file_name_no_directory(self, source_path, bucket_path):
        _, file_name = _extract_file_info(source_path, bucket_path)
        assert file_name == "single_file.parquet"

    @given(
        source_path=st.text(min_size=1),
        segments=st.lists(
            st.text(min_size=1).filter(lambda s: "/" not in s),
            min_size=1, max_size=5,
        ),
    )
    def test_file_name_nested_path(self, source_path, segments):
        bucket_path = "/".join(segments)
        _, file_name = _extract_file_info(source_path, bucket_path)
        assert file_name == segments[-1]

    @given(
        source_path=st.text(min_size=1),
        bucket_path=st.sampled_from(["dir/", "a/b/", "foo/bar/", "/", "///"]),
    )
    def test_bucket_path_trailing_slash(self, source_path, bucket_path):
        _, file_name = _extract_file_info(source_path, bucket_path)
        assert file_name == bucket_path.rstrip("/").split("/")[-1]


# ── UploadResult dataclass ────────────────────────────────────────────────────


class TestUploadResult:
    @given(status=st.sampled_from(list(UploadStatus)))
    def test_status_is_enum(self, status):
        assert isinstance(status, UploadStatus)
        assert status in UploadStatus

    @given(
        file_name=st.text(),
        original_path=st.text(),
        status=st.sampled_from([UploadStatus.SUCCESS, UploadStatus.SKIPPED]),
        hash_value=st.text(),
        hash_type=st.text(),
    )
    def test_success_skipped_have_hash(self, file_name, original_path, status, hash_value, hash_type):
        result = UploadResult(file_name, original_path, status, hash_value=hash_value, hash_type=hash_type)
        assert result.status is status
        assert result.hash_value == hash_value
        assert result.hash_type == hash_type

    @given(
        file_name=st.text(),
        original_path=st.text(),
        error_message=st.text(min_size=1),
    )
    def test_error_has_message(self, file_name, original_path, error_message):
        result = UploadResult(file_name, original_path, UploadStatus.ERROR, error_message=error_message)
        assert result.status is UploadStatus.ERROR
        assert result.error_message == error_message

    @given(
        file_name=st.text(),
        original_path=st.text(),
        error_message=st.text(),
    )
    def test_success_has_no_error_message(self, file_name, original_path, error_message):
        result = UploadResult(file_name, original_path, UploadStatus.SUCCESS, error_message=error_message)
        assert result.status is UploadStatus.SUCCESS
        assert result.error_message == error_message


# ── UploadResult defaults ─────────────────────────────────────────────────────


class TestUploadResultDefaults:
    def test_default_hash_empty(self):
        result = UploadResult("f.txt", "/path/f.txt", UploadStatus.SUCCESS)
        assert result.hash_value == ""
        assert result.hash_type == ""

    def test_default_error_message_empty(self):
        result = UploadResult("f.txt", "/path/f.txt", UploadStatus.SUCCESS)
        assert result.error_message == ""

    @given(
        file_name=st.text(),
        original_path=st.text(),
    )
    def test_defaults_not_none(self, file_name, original_path):
        result = UploadResult(file_name, original_path, UploadStatus.SUCCESS)
        assert result.hash_value == ""
        assert result.hash_type == ""
        assert result.error_message == ""


# ── upload_file (early return / source-not-found path) ────────────────────────


class TestUploadFileProperties:
    @given(
        source_path=st.text(min_size=1).filter(lambda p: not Path(p).is_file()),
        bucket_path=st.text(min_size=1),
        file_hash=st.text(),
        hash_type=st.text(min_size=1),
    )
    def test_source_not_found_returns_error(self, source_path, bucket_path, file_hash, hash_type):
        result = upload_file(
            source_path=source_path,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
        )
        assert result.status is UploadStatus.ERROR
        assert "Source file not found" in result.error_message
        assert result.file_name == bucket_path.rstrip("/").split("/")[-1]
        assert result.original_path == source_path

    @given(
        bucket_path=st.text(min_size=1),
        file_hash=st.text(),
        hash_type=st.text(min_size=1),
    )
    def test_source_not_found_with_empty_path(self, bucket_path, file_hash, hash_type):
        result = upload_file(
            source_path="",
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
        )
        assert result.status is UploadStatus.ERROR
        assert "Source file not found" in result.error_message

    @given(
        source_path=st.text().filter(lambda p: not Path(p).is_file()),
        bucket_path=st.text(),
        file_hash=st.text(),
        hash_type=st.text(),
    )
    def test_error_result_always_has_file_name(
        self, source_path, bucket_path, file_hash, hash_type
    ):
        result = upload_file(
            source_path=source_path,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
        )
        assert result.status is UploadStatus.ERROR
        assert isinstance(result.file_name, str)
        assert isinstance(result.original_path, str)


# ── upload_file with real S3 (integration check) ──────────────────────────────

@pytest.mark.skipif(not _has_aws_env(), reason="No AWS_ENDPOINT_URL set")
class TestUploadFileIntegrationProperties:
    """These run only when a real S3-compatible endpoint is configured."""

    @given(
        bucket_path=st.text(min_size=1),
        file_hash=st.text(min_size=1),
        hash_type=st.text(min_size=1),
    )
    def test_success_always_returns_file_name(self, bucket_path, file_hash, hash_type, tmp_path):
        source = tmp_path / "test.parquet"
        source.write_bytes(b"fake content")
        result = upload_file(
            source_path=str(source),
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
        )
        assert result.file_name == bucket_path.rstrip("/").split("/")[-1]
        assert result.original_path == str(source)
