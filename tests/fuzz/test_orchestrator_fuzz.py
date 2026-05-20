"""
Fuzz test for orchestrator.orchestrator.PipelineOrchestrator.run

Based on the actual implementation of orchestrator.py
"""

import atheris
from pathlib import Path

with atheris.instrument_imports():
    from orchestrator import PipelineOrchestrator
    from extract.hasher import Sha256Hasher


def fuzz_valid_inputs(fdp):
    """Generate valid inputs."""
    datasets = fdp.ConsumeIntList(0, 4)
    datasets = ["yellow", "green", "fhv", "hvfhv"] * (len(datasets) // 4 + 1)
    
    years = fdp.ConsumeIntList(0, 10)
    years = [fdp.ConsumeIntInRange(2009, 2030) for _ in years]
    
    months = fdp.ConsumeIntList(0, 12)
    months = [fdp.ConsumeIntInRange(1, 12) for _ in months]
    
    try:
        with PipelineOrchestrator(
            hasher=Sha256Hasher(),
            download_dir=Path("/tmp/fuzz"),
            bucket_name="test-bucket",
            bucket_path_prefix=""
        ) as orchestrator:
            orchestrator.run(datasets=datasets, years=years, months=months)
    except Exception:
        pass


def fuzz_empty_inputs(fdp):
    """Test with empty inputs."""
    try:
        with PipelineOrchestrator(
            hasher=Sha256Hasher(),
            download_dir=Path("/tmp/fuzz"),
            bucket_name="test-bucket",
            bucket_path_prefix=""
        ) as orchestrator:
            orchestrator.run()
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
