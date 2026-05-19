import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import atheris

with atheris.instrument_imports():
    from orchestrator.pipeline import FileOutcome, FileStatus, PipelineResult, run_pipeline
    from upload.uploader import UploadResult, UploadStatus

EXPECTED_EXCEPTIONS = (TypeError, ValueError, RuntimeError)


def _consume_urls(fdp):
    num = fdp.ConsumeIntInRange(0, 5)
    return [
        f"http://example.com/{fdp.ConsumeBytes(10).hex()}.parquet" for _ in range(num)
    ]


def _assert_pipeline_invariants(result, urls):
    assert isinstance(result, PipelineResult)
    assert result.total == len(urls)
    assert result.succeeded >= 0
    assert result.skipped >= 0
    assert result.failed >= 0
    assert result.succeeded + result.skipped + result.failed == result.total
    assert isinstance(result.files, list)
    assert len(result.files) == result.total
    for f in result.files:
        assert isinstance(f, FileOutcome)
        assert isinstance(f.status, FileStatus)


def fuzz_empty_urls(data):
    fdp = atheris.FuzzedDataProvider(data)
    fdp.ConsumeInt(1)
    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=[]),
    ):
        result = run_pipeline(hasher=MagicMock())
    assert result.total == 0
    assert result.succeeded == 0
    assert result.skipped == 0
    assert result.failed == 0
    assert result.files == []


def fuzz_download_none(data):
    fdp = atheris.FuzzedDataProvider(data)
    urls = _consume_urls(fdp)
    if not urls:
        return

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=urls),
        patch("orchestrator.pipeline.download_file", return_value=None),
    ):
        result = run_pipeline(hasher=MagicMock())

    _assert_pipeline_invariants(result, urls)
    assert result.succeeded == 0
    assert result.total == result.failed
    for f in result.files:
        assert f.status == FileStatus.DOWNLOAD_FAILED


def fuzz_download_exception(data):
    fdp = atheris.FuzzedDataProvider(data)
    urls = _consume_urls(fdp)
    if not urls:
        return

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=urls),
        patch(
            "orchestrator.pipeline.download_file",
            side_effect=RuntimeError("fuzz error"),
        ),
    ):
        result = run_pipeline(hasher=MagicMock())

    _assert_pipeline_invariants(result, urls)
    assert result.succeeded == 0
    assert result.total == result.failed
    for f in result.files:
        assert f.status == FileStatus.DOWNLOAD_ERROR


def fuzz_upload_error(data):
    fdp = atheris.FuzzedDataProvider(data)
    urls = _consume_urls(fdp)
    if not urls:
        return

    mock_download = MagicMock()
    mock_download.file_path = Path(fdp.ConsumeUnicode(50) or "/tmp/fuzz.parquet")
    mock_download.hash_value = fdp.ConsumeUnicode(32)
    mock_download.hash_type = "sha256"

    upload_error = UploadResult(
        file_name="fuzz.parquet",
        original_path=str(mock_download.file_path),
        status=UploadStatus.ERROR,
        error_message=fdp.ConsumeUnicode(100),
    )

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=urls),
        patch("orchestrator.pipeline.download_file", return_value=mock_download),
        patch("orchestrator.pipeline.upload_file", return_value=upload_error),
    ):
        result = run_pipeline(hasher=MagicMock())

    _assert_pipeline_invariants(result, urls)
    assert result.succeeded == 0
    assert result.total == result.failed
    for f in result.files:
        assert f.status == FileStatus.UPLOAD_FAILED
        assert isinstance(f.error_message, str)


def fuzz_upload_skipped(data):
    fdp = atheris.FuzzedDataProvider(data)
    urls = _consume_urls(fdp)
    if not urls:
        return

    mock_download = MagicMock()
    mock_download.file_path = Path("/tmp/fuzz.parquet")
    mock_download.hash_value = fdp.ConsumeUnicode(32)
    mock_download.hash_type = "sha256"

    upload_skipped = UploadResult(
        file_name="fuzz.parquet",
        original_path="/tmp/fuzz.parquet",
        status=UploadStatus.SKIPPED,
        hash_value=mock_download.hash_value,
        hash_type="sha256",
    )

    with (
        patch("orchestrator.pipeline.generate_parquet_urls", return_value=urls),
        patch("orchestrator.pipeline.download_file", return_value=mock_download),
        patch("orchestrator.pipeline.upload_file", return_value=upload_skipped),
    ):
        result = run_pipeline(hasher=MagicMock())

    _assert_pipeline_invariants(result, urls)
    assert result.failed == 0
    assert result.total == result.skipped
    for f in result.files:
        assert f.status == FileStatus.SKIPPED
        assert isinstance(f.error_message, str)


def fuzz_mixed_statuses(data):
    fdp = atheris.FuzzedDataProvider(data)

    n_total = fdp.ConsumeIntInRange(0, 8)
    n_error = fdp.ConsumeIntInRange(0, n_total) if n_total else 0
    n_skip = (
        fdp.ConsumeIntInRange(0, n_total - n_error) if n_total > n_error else 0
    )
    n_success = n_total - n_error - n_skip

    urls = [f"http://example.com/f{i}.parquet" for i in range(n_total)]

    def mock_download_side_effect(url, *args, **kwargs):
        idx = urls.index(url)
        if idx < n_error:
            raise RuntimeError("Network error")
        mock = MagicMock()
        mock.file_path = Path(f"/tmp/f{idx}.parquet")
        mock.hash_value = f"hash{idx}"
        mock.hash_type = "sha256"
        return mock

    def mock_upload_side_effect(source_path, *args, **kwargs):
        idx_with_success = n_error + n_success
        for i in range(n_total):
            if source_path == f"/tmp/f{i}.parquet":
                if i < n_error:
                    raise RuntimeError("should not reach")
                elif i < idx_with_success:
                    return UploadResult(
                        file_name=f"f{i}.parquet",
                        original_path=source_path,
                        status=UploadStatus.SUCCESS,
                        hash_value=f"hash{i}",
                        hash_type="sha256",
                    )
                else:
                    return UploadResult(
                        file_name=f"f{i}.parquet",
                        original_path=source_path,
                        status=UploadStatus.SKIPPED,
                        hash_value=f"hash{i}",
                        hash_type="sha256",
                    )
        return UploadResult(
            file_name="unknown.parquet",
            original_path=source_path,
            status=UploadStatus.ERROR,
        )

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

    _assert_pipeline_invariants(result, urls)
    assert result.succeeded == n_success
    assert result.skipped == n_skip
    assert result.failed == n_error


def test_one_input(data):
    fdp = atheris.FuzzedDataProvider(data)
    case = fdp.ConsumeIntInRange(0, 5)

    try:
        if case == 0:
            fuzz_empty_urls(data)
        elif case == 1:
            fuzz_download_none(data)
        elif case == 2:
            fuzz_download_exception(data)
        elif case == 3:
            fuzz_upload_error(data)
        elif case == 4:
            fuzz_upload_skipped(data)
        elif case == 5:
            fuzz_mixed_statuses(data)
    except EXPECTED_EXCEPTIONS:
        pass
    except Exception as e:
        raise e


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
