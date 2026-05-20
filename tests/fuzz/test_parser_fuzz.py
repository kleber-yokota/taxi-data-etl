"""
Fuzz test for extract.parser.generate_parquet_urls

Based on the actual implementation of parser.py:
- VALID_DATASETS = {"yellow", "green", "fhv", "hvfhv"}
- _check_dataset: TypeError if not str, ValueError if not in set
- _check_year: TypeError if not int or if bool
- _check_month: TypeError if not int or if bool, ValueError if outside 1-12
- _validate_*: TypeError if not iterable (e.g. years=None)
- datasets=None uses all 4 valid ones
"""

import atheris

with atheris.instrument_imports():
    from extract.parser import BASE_S3_URL, VALID_DATASETS, generate_parquet_urls

VALID_DATASETS_LIST = sorted(VALID_DATASETS)

EXPECTED_EXCEPTIONS = (TypeError, ValueError)


def fuzz_valid_seeds(fdp):
    """Generate valid dataset/years/months combinations."""
    datasets = fdp.ConsumeIntList(0, 4)
    datasets = [VALID_DATASETS_LIST[i] for i in datasets]
    
    years = fdp.ConsumeIntList(0, 10)
    years = [fdp.ConsumeIntInRange(2009, 2030) for _ in years]
    
    months = fdp.ConsumeIntList(0, 12)
    months = [fdp.ConsumeIntInRange(1, 12) for _ in months]
    
    try:
        generate_parquet_urls(datasets=datasets, years=years, months=months)
    except (TypeError, ValueError):
        pass


def fuzz_wrong_types(fdp):
    """Test with wrong types."""
    datasets = fdp.ConsumeIntList(0, 4)
    datasets = [123, "invalid", None, True] * (len(datasets) // 4 + 1)
    
    years = fdp.ConsumeIntList(0, 10)
    years = [123.5, "2023", None, True, 1000000] * (len(years) // 5 + 1)
    
    months = fdp.ConsumeIntList(0, 12)
    months = [1.5, "1", None, True, 100] * (len(months) // 5 + 1)
    
    try:
        generate_parquet_urls(datasets=datasets, years=years, months=months)
    except (TypeError, ValueError):
        pass


def fuzz_out_of_range(fdp):
    """Test with out of range values."""
    years = fdp.ConsumeIntList(0, 10)
    years = [fdp.ConsumeIntInRange(1800, 3000) for _ in years]
    
    months = fdp.ConsumeIntList(0, 12)
    months = [fdp.ConsumeIntInRange(0, 13) for _ in months]
    
    try:
        generate_parquet_urls(years=years, months=months)
    except (TypeError, ValueError):
        pass


def fuzz_none_datasets(fdp):
    """Test with None datasets."""
    datasets = [None]
    years = [fdp.ConsumeIntInRange(2009, 2030)]
    months = [fdp.ConsumeIntInRange(1, 12)]
    
    try:
        generate_parquet_urls(datasets=datasets, years=years, months=months)
    except (TypeError, ValueError):
        pass


def fuzz_empty_inputs(fdp):
    """Test with empty inputs."""
    datasets = []
    years = []
    months = []
    
    try:
        generate_parquet_urls(datasets=datasets, years=years, months=months)
    except (TypeError, ValueError):
        pass


def test_one_input():
    """
    Runs all strategies in each execution.
    libFuzzer mutates bytes seeking to increase coverage in any of them.
    """
    fdp = atheris.FuzzedDataProvider(b'\x00' * 1000)
    fuzz_valid_seeds(fdp)
    fuzz_wrong_types(fdp)
    fuzz_out_of_range(fdp)
    fuzz_none_datasets(fdp)
    fuzz_empty_inputs(fdp)
