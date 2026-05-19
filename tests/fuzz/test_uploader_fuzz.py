"""
Fuzz test for upload.uploader

Exercises:
- _extract_file_info with random path inputs
- upload_file source-not-found path (no S3 needed)
- UploadResult dataclass edge cases
"""

import sys
from pathlib import Path

import atheris

with atheris.instrument_imports():
    from upload.uploader import (
        UploadResult,
        UploadStatus,
        _extract_file_info,
        upload_file,
    )

EXPECTED_EXCEPTIONS = (TypeError, ValueError, AttributeError, OSError, FileNotFoundError)


# ── Strategy 1: _extract_file_info with random strings ────────────────────────


def fuzz_extract_file_info(data):
    """Exercises _extract_file_info with random source and bucket paths."""
    fdp = atheris.FuzzedDataProvider(data)

    source_path = fdp.ConsumeUnicode(sys.maxsize)
    bucket_path = fdp.ConsumeUnicode(sys.maxsize)

    try:
        source, file_name = _extract_file_info(source_path, bucket_path)

        assert isinstance(source, Path), f"source should be Path, got {type(source)}"
        assert isinstance(file_name, str), (
            f"file_name should be str, got {type(file_name)}"
        )

        # Path normalizes input (e.g. "//" -> "/", "" -> "."), so compare as Path
        assert source == Path(source_path), (
            f"Path mismatch: {source!r} != Path({source_path!r})"
        )

        expected_file_name = bucket_path.rstrip("/").split("/")[-1]
        assert file_name == expected_file_name, (
            f"file_name {file_name!r} != expected {expected_file_name!r} "
            f"for bucket_path {bucket_path!r}"
        )

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Strategy 2: upload_file source-not-found path ────────────────────────────


def fuzz_upload_source_not_found(data):
    """
    Tests upload_file with source_path that does not exist.
    This path returns early without creating an S3 client.
    """
    fdp = atheris.FuzzedDataProvider(data)

    source_path = fdp.ConsumeUnicode(4096)
    bucket_path = fdp.ConsumeUnicode(4096)
    file_hash = fdp.ConsumeUnicode(256)
    hash_type = fdp.ConsumeUnicode(64)

    try:
        if Path(source_path).is_file():
            return

        result = upload_file(
            source_path=source_path,
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
        )

        assert result.status is UploadStatus.ERROR
        assert isinstance(result.error_message, str)
        assert "Source file not found" in result.error_message
        assert result.file_name == bucket_path.rstrip("/").split("/")[-1]
        assert result.original_path == source_path

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Strategy 3: UploadResult dataclass edge cases ─────────────────────────────


def fuzz_upload_result_creation(data):
    """Tests UploadResult creation with random values."""
    fdp = atheris.FuzzedDataProvider(data)

    file_name = fdp.ConsumeUnicode(512)
    original_path = fdp.ConsumeUnicode(512)
    hash_value = fdp.ConsumeUnicode(256)
    hash_type = fdp.ConsumeUnicode(64)
    error_message = fdp.ConsumeUnicode(1024)

    status_pick = fdp.ConsumeIntInRange(0, 2)
    status_map = [UploadStatus.SUCCESS, UploadStatus.SKIPPED, UploadStatus.ERROR]
    status = status_map[status_pick]

    try:
        result = UploadResult(
            file_name=file_name,
            original_path=original_path,
            status=status,
            hash_value=hash_value,
            hash_type=hash_type,
            error_message=error_message,
        )

        assert result.file_name == file_name
        assert result.original_path == original_path
        assert result.status is status
        assert result.hash_value == hash_value
        assert result.hash_type == hash_type
        assert result.error_message == error_message

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Strategy 4: upload_file empty-input edge cases ────────────────────────────


def fuzz_upload_empty_inputs(data):
    """Tests upload_file with empty or boundary input values."""
    fdp = atheris.FuzzedDataProvider(data)

    case = fdp.ConsumeIntInRange(0, 3)

    try:
        if case == 0:
            # Empty source_path + random bucket_path
            bucket_path = fdp.ConsumeUnicode(256)
            result = upload_file(
                source_path="",
                bucket_path=bucket_path,
                file_hash=fdp.ConsumeUnicode(64),
            )
            assert result.status is UploadStatus.ERROR

        elif case == 1:
            # Empty bucket_path + random source_path
            source_path = fdp.ConsumeUnicode(256)
            if Path(source_path).is_file():
                return
            result = upload_file(
                source_path=source_path,
                bucket_path="",
                file_hash=fdp.ConsumeUnicode(64),
            )
            assert result.status is UploadStatus.ERROR
            assert result.file_name == ""

        elif case == 2:
            # Empty file_hash + random source_path
            source_path = fdp.ConsumeUnicode(256)
            if Path(source_path).is_file():
                return
            bucket_path = fdp.ConsumeUnicode(256)
            result = upload_file(
                source_path=source_path,
                bucket_path=bucket_path,
                file_hash="",
                hash_type=fdp.ConsumeUnicode(64),
            )
            assert result.status is UploadStatus.ERROR

        elif case == 3:
            # Empty hash_type (default used)
            source_path = fdp.ConsumeUnicode(256)
            if Path(source_path).is_file():
                return
            result = upload_file(
                source_path=source_path,
                bucket_path=fdp.ConsumeUnicode(256),
                file_hash=fdp.ConsumeUnicode(64),
                hash_type="",
            )
            assert result.status is UploadStatus.ERROR

    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Strategy 5: _extract_file_info with boundary paths ────────────────────────


def fuzz_extract_file_info_boundaries(data):
    """Exercises _extract_file_info with boundary cases like slashes, dots."""
    fdp = atheris.FuzzedDataProvider(data)

    special_chars = ["/", "\\", ".", "..", "", " ", "\n", "\t", "\0", "a/b/c", "/a/b/c/"]
    source_path = fdp.PickValueInList(special_chars)
    bucket_path = fdp.PickValueInList(special_chars)

    try:
        source, file_name = _extract_file_info(source_path, bucket_path)
        assert isinstance(source, Path)
        assert isinstance(file_name, str)
    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


# ── Entry point ───────────────────────────────────────────────────────────────


def test_one_input(data):
    """
    Runs all strategies in each execution.
    libFuzzer mutates bytes seeking to increase coverage in any of them.
    """
    fuzz_extract_file_info(data)
    fuzz_upload_source_not_found(data)
    fuzz_upload_result_creation(data)
    fuzz_upload_empty_inputs(data)
    fuzz_extract_file_info_boundaries(data)


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
