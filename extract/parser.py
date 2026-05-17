import logging
from typing import Iterable, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_S3_URL = "https://d37ci68n02y6s.cloudfront.net/trip-data/"
VALID_DATASETS = {"yellow", "green", "manhattan", "fhv"}


def generate_parquet_urls(
    datasets: Iterable[str] = None,
    years: Iterable[int] = range(2015, 2026),
    months: Iterable[int] = range(1, 13),
) -> List[str]:
    """
    Generates a list of Parquet URLs based on the known NYC TLC pattern,
    ordered chronologically.

    Pattern: {BASE_S3_URL}{dataset}_tripdata_{year}-{month}.parquet

    Args:
        datasets: Iterable of dataset names. If None, all 4 valid datasets are used.
        years: Iterable of years.
        months: Iterable of months (1-12).

    Returns:
        List[str]: A chronologically ordered list of absolute URLs.

    Raises:
        TypeError: If any of the inputs are not iterable.
        ValueError: If any month is outside the range [1, 12] or a dataset is invalid.
    """
    # Use all valid datasets if none provided
    if datasets is None:
        datasets = sorted(list(VALID_DATASETS))

    if not all(isinstance(i, Iterable) for i in [datasets, years, months]):
        raise TypeError("datasets, years, and months must all be iterable.")

    # Sort inputs to ensure chronological order
    sorted_years = sorted(years)
    sorted_months = sorted(months)
    sorted_datasets = sorted(datasets)

    urls = []

    for year in sorted_years:
        for month in sorted_months:
            if not isinstance(month, int):
                raise TypeError(f"Month must be an integer, got {type(month).__name__}")
            if not (1 <= month <= 12):
                raise ValueError(f"Month {month} is out of valid range (1-12)")

            for dataset in sorted_datasets:
                if not isinstance(dataset, str):
                    raise TypeError(
                        f"Dataset name must be a string, got {type(dataset).__name__}"
                    )
                if dataset not in VALID_DATASETS:
                    raise ValueError(
                        f"Invalid dataset '{dataset}'. Must be one of {VALID_DATASETS}"
                    )

                url = f"{BASE_S3_URL}{dataset}_tripdata_{year}-{month:02d}.parquet"
                urls.append(url)

    logger.info(f"Generated {len(urls)} potential URLs in chronological order.")
    return urls
