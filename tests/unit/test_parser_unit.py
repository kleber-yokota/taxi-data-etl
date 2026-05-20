import pytest

from extract.parser import (
    _check_dataset,
    _check_month,
    _check_year,
    _validate_datasets,
    _validate_months,
    _validate_years,
    generate_parquet_urls,
)


def test_generate_parquet_urls_correct_count():
    """Test that the number of generated URLs is correct."""
    datasets = ["yellow", "green"]
    years = [2023]
    months = [1, 2]
    urls = generate_parquet_urls(datasets, years, months)
    # 2 datasets * 1 year * 2 months = 4 urls
    assert len(urls) == 4
    assert isinstance(urls, list)


def test_generate_parquet_urls_chronological_order():
    """Test that URLs are generated in chronological order (year then month)."""
    datasets = ["yellow"]
    years = [2022, 2023]
    months = [12, 1]

    # We expect: 2022-01, 2022-12, 2023-01, 2023-12
    urls = generate_parquet_urls(datasets, years, months)

    expected_order = [
        "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2022-01.parquet",
        "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2022-12.parquet",
        "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-01.parquet",
        "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-12.parquet",
    ]
    assert urls == expected_order


def test_generate_parquet_urls_dataset_constraints():
    """Test that providing a dataset not in the valid list raises ValueError."""
    with pytest.raises(ValueError, match="Invalid dataset"):
        generate_parquet_urls(["invalid_taxi"], [2023], [1])


def test_generate_parquet_urls_default_datasets():
    """Test that providing None as datasets uses all 4 valid types."""
    years = [2023]
    months = [1]
    urls = generate_parquet_urls(datasets=None, years=years, months=months)

    # Should contain 4 urls (yellow, green, fhv, hvfhv)
    assert len(urls) == 4
    # Use split("/")[-1] first to get the filename, then split("_")[0] to get the dataset
    datasets_found = {url.split("/")[-1].split("_")[0] for url in urls}
    assert datasets_found == {"yellow", "green", "fhv", "hvfhv"}


def test_generate_parquet_urls_empty_inputs():
    """Test that empty inputs return an empty list."""
    assert generate_parquet_urls([], [2023], [1]) == []
    assert generate_parquet_urls(["yellow"], [], [1]) == []
    assert generate_parquet_urls(["yellow"], [2023], []) == []


def test_generate_parquet_urls_invalid_types():
    """Test that invalid types raise TypeError."""
    # Test with non-iterable to trigger validation
    with pytest.raises(TypeError, match="years must be iterable"):
        generate_parquet_urls(["yellow"], 123, [1])

    with pytest.raises(TypeError, match="Month must be an integer"):
        generate_parquet_urls(["yellow"], [2023], "1")


def test_generate_parquet_urls_invalid_month_range():
    """Test that months outside [1, 12] raise ValueError."""
    with pytest.raises(ValueError, match="out of valid range"):
        generate_parquet_urls(["yellow"], [2023], [13])


@pytest.mark.parametrize(
    "value, expected_exception, match",
    [
        (123, TypeError, r"Dataset name must be a string, got int"),
        ("invalid", ValueError, r"Invalid dataset 'invalid'. Must be one of"),
    ],
)
def test_check_dataset_errors(value, expected_exception, match):
    """Verify dataset validation error messages."""
    with pytest.raises(expected_exception, match=match):
        _check_dataset(value)


@pytest.mark.parametrize(
    "value, expected_exception, match",
    [
        ("2023", TypeError, r"Year must be an integer, got str"),
        (True, TypeError, r"Year must be an integer, got bool"),
    ],
)
def test_check_year_errors(value, expected_exception, match):
    """Verify year validation error messages."""
    with pytest.raises(expected_exception, match=match):
        _check_year(value)


@pytest.mark.parametrize(
    "value, expected_exception, match",
    [
        ("1", TypeError, r"Month must be an integer, got str"),
        (13, ValueError, r"Month 13 is out of valid range \(1-12\)"),
    ],
)
def test_check_month_errors(value, expected_exception, match):
    """Verify month validation error messages."""
    with pytest.raises(expected_exception, match=match):
        _check_month(value)


@pytest.mark.parametrize(
    "func, value, match",
    [
        (_validate_datasets, None, r"^datasets must be iterable\.$"),
        (_validate_years, None, r"^years must be iterable\.$"),
        (_validate_months, None, r"^months must be iterable\.$"),
    ],
)
def test_validate_iterable_errors(func, value, match):
    """Verify that iterable check functions raise correct errors."""
    with pytest.raises(TypeError, match=match):
        func(value)


def test_generate_parquet_urls_log(caplog):
    """Test that generate_parquet_urls logs the number of generated URLs to kill mutation survivors."""
    import logging

    with caplog.at_level(logging.INFO):
        generate_parquet_urls(["yellow"], [2023], [1])
    assert "Generated 1 potential URLs in chronological order." in caplog.text
