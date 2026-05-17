from typing import List, Set, Iterable
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_S3_URL = "https://d37ci68n02y6s.cloudfront.net/trip-data/"
VALID_DATASETS = {"yellow", "green", "manhattan", "fhv"}

def _validate_datasets(datasets: Iterable[str]) -> List[str]:
    """Validates and sorts dataset names."""
    if not isinstance(datasets, Iterable):
        raise TypeError("datasets must be iterable.")
    
    validated = []
    for d in datasets:
        if not isinstance(d, str):
            raise TypeError(f"Dataset name must be a string, got {type(d).__name__}")
        if d not in VALID_DATASETS:
            raise ValueError(f"Invalid dataset '{d}'. Must be one of {VALID_DATASETS}")
        validated.append(d)
    
    return sorted(validated)

def _validate_years(years: Iterable[int]) -> List[int]:
    """Validates and sorts year values."""
    if not isinstance(years, Iterable):
        raise TypeError("years must be iterable.")
    
    validated = []
    for y in years:
        if not isinstance(y, int):
            raise TypeError(f"Year must be an integer, got {type(y).__name__}")
        validated.append(y)
        
    return sorted(validated)

def _validate_months(months: Iterable[int]) -> List[int]:
    """Validates and sorts month values."""
    if not isinstance(months, Iterable):
        raise TypeError("months must be iterable.")
    
    validated = []
    for m in months:
        if not isinstance(m, int):
            raise TypeError(f"Month must be an integer, got {type(m).__name__}")
        if not (1 <= m <= 12):
            raise ValueError(f"Month {m} is out of valid range (1-12)")
        validated.append(m)
        
    return sorted(validated)

def generate_parquet_urls(
    datasets: Iterable[str] = None, 
    years: Iterable[int] = range(2015, 2025), 
    months: Iterable[int] = range(1, 13)
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
    # Handle default datasets
    if datasets is None:
        datasets = VALID_DATASETS

    # 1. Separate Validation Logic
    v_datasets = _validate_datasets(datasets)
    v_years = _validate_years(years)
    v_months = _validate_months(months)

    # 2. Core Generation Logic
    urls = []
    for year in v_years:
        for month in v_months:
            for dataset in v_datasets:
                url = f"{BASE_S3_URL}{dataset}_tripdata_{year}-{month:02d}.parquet"
                urls.append(url)
                
    logger.info(f"Generated {len(urls)} potential URLs in chronological order.")
    return urls
