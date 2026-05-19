from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orchestrator.pipeline import FileOutcome, FileStatus, PipelineResult, run_pipeline
from upload.uploader import UploadResult, UploadStatus

# ── FileStatus enum ──────────────────────────────────────────────────────────


@given(status=st.sampled_from(list(FileStatus)))
def test_file_status_is_enum(status):
    assert isinstance(status, FileStatus)
    assert status in FileStatus


@given(status=st.sampled_from(list(FileStatus)))
def test_file_status_value_is_string(status):
    assert isinstance(status.value, str)


def test_file_status_values_match_expected():
    assert FileStatus.SUCCESS.value == "success"
    assert FileStatus.SKIPPED.value == "skipped"
    assert FileStatus.DOWNLOAD_FAILED.value == "download_failed"
    assert FileStatus.DOWNLOAD_ERROR.value == "download_error"
    assert FileStatus.UPLOAD_FAILED.value == "upload_failed"


# ── FileOutcome dataclass ────────────────────────────────────────────────────


@given(url=st.text(), error_message=st.text())
def test_file_outcome_defaults(url, error_message):
    outcome = FileOutcome(url=url, status=FileStatus.SUCCESS, error_message=error_message)
    assert outcome.url == url
    assert outcome.status == FileStatus.SUCCESS
    assert outcome.download_result is None
    assert outcome.upload_result is None
    assert outcome.error_message == error_message


@given(
    url=st.text(),
    status=st.sampled_from(list(FileStatus)),
    error_message=st.text(),
)
def test_file_outcome_roundtrip(url, status, error_message):
    outcome = FileOutcome(url=url, status=status, error_message=error_message)
    assert outcome.url == url
    assert outcome.status == status
    assert outcome.error_message == error_message


# ── PipelineResult dataclass ─────────────────────────────────────────────────


@given(
    succeeded=st.integers(min_value=0, max_value=10),
    skipped=st.integers(min_value=0, max_value=10),
    failed=st.integers(min_value=0, max_value=10),
    n_files=st.integers(min_value=0, max_value=10),
)
def test_pipeline_result_counts(succeeded, skipped, failed, n_files):
    total = succeeded + skipped + failed

    files = [
        FileOutcome(
            url=f"http://example.com/f{i}.parquet",
            status=FileStatus.SUCCESS if i < succeeded else (
                FileStatus.SKIPPED if i < succeeded + skipped else FileStatus.DOWNLOAD_FAILED
            ),
        )
        for i in range(min(n_files, total))
    ]

    result = PipelineResult(
        total=total,
        succeeded=succeeded,
        skipped=skipped,
        failed=failed,
        files=files,
    )

    assert result.total == total
    assert result.succeeded == succeeded
    assert result.skipped == skipped
    assert result.failed == failed
    assert list(result.files) == files


@given(
    succeeded=st.integers(min_value=0, max_value=10),
    skipped=st.integers(min_value=0, max_value=10),
    failed=st.integers(min_value=0, max_value=10),
)
def test_pipeline_result_zero_files_default(succeeded, skipped, failed):
    total = succeeded + skipped + failed
    result = PipelineResult(
        total=total,
        succeeded=succeeded,
        skipped=skipped,
        failed=failed,
    )
    assert result.total == total
    assert result.files == []


# ── run_pipeline invariants ──────────────────────────────────────────────────


@given(
    n_success=st.integers(min_value=0, max_value=4),
    n_skipped=st.integers(min_value=0, max_value=4),
    n_download_fail=st.integers(min_value=0, max_value=4),
    n_download_error=st.integers(min_value=0, max_value=4),
    n_upload_fail=st.integers(min_value=0, max_value=4),
)
def test_run_pipeline_status_counts(
    n_success, n_skipped, n_download_fail, n_download_error, n_upload_fail
):
    total = n_success + n_skipped + n_download_fail + n_download_error + n_upload_fail
    if total == 0:
        return

    urls = [f"http://example.com/f{i}.parquet" for i in range(total)]

    upload_ok = UploadResult(
        file_name="f.parquet",
        original_path="/tmp/f.parquet",
        status=UploadStatus.SUCCESS,
    )
    upload_skip = UploadResult(
        file_name="f.parquet",
        original_path="/tmp/f.parquet",
        status=UploadStatus.SKIPPED,
        hash_value="abc",
        hash_type="sha256",
    )
    upload_err = UploadResult(
        file_name="f.parquet",
        original_path="/tmp/f.parquet",
        status=UploadStatus.ERROR,
        error_message="upload error",
    )

    state = ["success"] * n_success + ["skipped"] * n_skipped \
        + ["download_fail"] * n_download_fail \
        + ["download_error"] * n_download_error \
        + ["upload_fail"] * n_upload_fail
    state = state[:total]

    def mock_download_side_effect(url, *args, **kwargs):
        idx = urls.index(url)
        s = state[idx]
        if s == "download_error":
            raise RuntimeError("Network error")
        if s == "download_fail":
            return None
        mock = MagicMock()
        mock.file_path = Path(f"/tmp/f{idx}.parquet")
        mock.hash_value = f"hash{idx}"
        mock.hash_type = "sha256"
        return mock

    def mock_upload_side_effect(source_path, *args, **kwargs):
        for i in range(total):
            if source_path == f"/tmp/f{i}.parquet":
                s = state[i]
                if s == "upload_fail":
                    return upload_err
                if s == "skipped":
                    return upload_skip
                return upload_ok
        return upload_err

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=urls),
        patch(
            "orchestrator.pipeline.download_file",
            side_effect=mock_download_side_effect,
        ),
        patch(
            "orchestrator.pipeline.upload_file",
            side_effect=mock_upload_side_effect,
        ),
    ):
        result = run_pipeline(hasher=MagicMock())

    assert result.total == total
    assert result.succeeded == n_success
    assert result.skipped == n_skipped
    expected_failed = n_download_fail + n_download_error + n_upload_fail
    assert result.failed == expected_failed

    for outcome in result.files:
        assert isinstance(outcome.status, FileStatus)
