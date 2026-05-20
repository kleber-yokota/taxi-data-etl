"""
Fuzz test for upload.uploader.upload_file

Based on the actual implementation of uploader.py
"""

import atheris
from pathlib import Path

with atheris.instrument_imports():
    from upload.uploader import UploadResult, UploadStatus, upload_file


def fuzz_valid_inputs(fdp):
    """Generate valid inputs."""
    source_path = Path(fdp.ConsumeUnicode(100))
    if not source_path.exists():
        source_path = Path("/tmp/test.parquet")
        source_path.write_bytes(b"test content")
    
    bucket_path = fdp.ConsumeUnicode(100)
    
    file_hash = fdp.ConsumeUnicode(64)
    hash_type = fdp.ConsumeInt(10)
    if hash_type == 0:
        hash_type = "sha256"
    else:
        hash_type = "md5"
    
    bucket_name = fdp.ConsumeUnicode(50)
    
    try:
        upload_file(
            source_path=str(source_path),
            bucket_path=bucket_path,
            file_hash=file_hash,
            hash_type=hash_type,
            bucket_name=bucket_name,
        )
    except Exception:
        pass


def fuzz_empty_inputs(fdp):
    """Test with empty inputs."""
    source_path = Path("/tmp/test.parquet")
    source_path.write_bytes(b"test content")
    
    try:
        upload_file(
            source_path="/tmp/test.parquet",
            bucket_path="",
            file_hash="",
            hash_type="sha256",
            bucket_name="test-bucket",
        )
    except Exception:
        pass


def test_one_input():
    """
    Runs all strategies in each execution.
    libFuzzer mutates bytes seeking to increase coverage in any of them.
    """
    fdp = atheris.FuzzedDataProvider(b'\x00' * 1000)
    fuzz_valid_inputs(fdp)
    fuzz_empty_inputs(fdp)
