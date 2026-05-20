import logging
from datetime import date
from typing import Iterable, List

logger = logging.getLogger(__name__)

BASE_S3_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/"
VALID_DATASETS = {"yellow", "green", "fhv", "hvfhv"}


def _check_dataset(d) -> str:
    """Validates a single dataset item.
    
    Args:
        d: Dataset name string.
        
    Returns:
        str: Validated dataset name.
        
    Raises:
        TypeError: If d is not a string.
        ValueError: If d is not in VALID_DATASETS.
    """
    if not isinstance(d, str):
        raise TypeError(f"Dataset name must be a string, got {type(d).__name__}")
    if d not in VALID_DATASETS:
        raise ValueError(f"Invalid dataset '{d}'. Must be one of {VALID_DATASETS}")
    return d


def _check_year(y) -> int:
    """Validates a single year item. Explicitly rejects booleans.
    
    Args:
        y: Year as integer.
        
    Returns:
        int: Validated year.
        
    Raises:
        TypeError: If y is not an integer (including booleans).
    """
    if not isinstance(y, int) or isinstance(y, bool):
        raise TypeError(f"Year must be an integer, got {type(y).__name__}")
    return y


def _check_month(m) -> int:
    """Validates a single month item. Explicitly rejects booleans.
    
    Args:
        m: Month as integer (1-12).
        
    Returns:
        int: Validated month.
        
    Raises:
        TypeError: If m is not an integer (including booleans).
        ValueError: If m is not in range 1-12.
    """
    if not isinstance(m, int) or isinstance(m, bool):
        raise TypeError(f"Month must be an integer, got {type(m).__name__}")
    if not (1 <= m <= 12):
        raise ValueError(f"Month {m} is out of valid range (1-12)")
    return m


def _validate_datasets(datasets: Iterable[str]) -> List[str]:
    """Validates and normalizes a collection of dataset names.
    
    Removes duplicates, validates each dataset name, and returns sorted list.
    
    Args:
        datasets: Iterable of dataset name strings.
        
    Returns:
        List[str]: Sorted list of unique, validated dataset names.
        
    Raises:
        TypeError: If datasets is not iterable.
    """
    if not isinstance(datasets, Iterable):
        raise TypeError("datasets must be iterable.")
    # Use set to avoid duplicates and sort for deterministic order
    return sorted(list({_check_dataset(d) for d in datasets}))


def _validate_years(years: Iterable[int]) -> List[int]:
    """Validates and normalizes a collection of years.
    
    Removes duplicates, validates each year, and returns sorted list.
    
    Args:
        years: Iterable of year integers.
        
    Returns:
        List[int]: Sorted list of unique, validated years.
        
    Raises:
        TypeError: If years is not iterable.
    """
    if not isinstance(years, Iterable):
        raise TypeError("years must be iterable.")
    # Use set to avoid duplicates and sort for chronological order
    return sorted(list({_check_year(y) for y in years}))


def _validate_months(months: Iterable[int]) -> List[int]:
    """Validates and normalizes a collection of months.
    
    Removes duplicates, validates each month, and returns sorted list.
    
    Args:
        months: Iterable of month integers (1-12).
        
    Returns:
        List[int]: Sorted list of unique, validated months.
        
    Raises:
        TypeError: If months is not iterable.
    """
    if not isinstance(months, Iterable):
        raise TypeError("months must be iterable.")
    # Use set to avoid duplicates and sort for chronological order
    return sorted(list({_check_month(m) for m in months}))


def generate_parquet_urls(
    datasets: Iterable[str] = None,
    years: Iterable[int] = range(2009, date.today().year + 1),
    months: Iterable[int] = range(1, 13),
) -> List[str]:
    """
    Generates a list of Parquet URLs based on the known NYC TLC pattern,
    ordered chronologically.

    Args:
        datasets: Iterable of dataset names. If None, uses all 4 valid types.
        years: Iterable of years.
        months: Iterable of months (1-12).

    Returns:
        List[str]: A chronologically ordered list of absolute URLs.
    """
    if datasets is None:
        datasets = VALID_DATASETS
    if years is None:
        years = range(2015, date.today().year + 1)
    if months is None:
        months = range(1, 13)

    v_datasets = _validate_datasets(datasets)
    v_years = _validate_years(years)
    v_months = _validate_months(months)

    urls = [
        f"{BASE_S3_URL}{dataset}_tripdata_{year}-{month:02d}.parquet"
        for year in v_years
        for month in v_months
        for dataset in v_datasets
    ]

    logger.info(f"Generated {len(urls)} potential URLs in chronological order.")
    return urls
