from typing import Set, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The observed pattern for NYC TLC Parquet files
BASE_S3_URL = "https://d37ci68n02y6s.cloudfront.net/trip-data/"

def generate_parquet_urls(
    datasets: List[str] = ["yellow", "green", "manhattan"], 
    years: List[int] = range(2015, 2025), 
    months: List[int] = range(1, 13)
) -> Set[str]:
    """
    Generates a set of potential Parquet URLs based on the known NYC TLC pattern.
    
    Pattern: {BASE_S3_URL}{dataset}_tripdata_{year}-{month}.parquet

    Args:
        datasets (List[str]): List of dataset types (e.g., 'yellow', 'green').
        years (List[int]): Range or list of years to generate.
        months (List[int]): Range or list of months to generate.

    Returns:
        Set[str]: A set of generated absolute URLs.
    """
    urls = set()
    
    for dataset in datasets:
        for year in years:
            for month in months:
                # Format month to always be two digits (e.g., 01, 02)
                url = f"{BASE_S3_URL}{dataset}_tripdata_{year}-{month:02d}.parquet"
                urls.add(url)
                
    logger.info(f"Generated {len(urls)} potential URLs based on the S3 pattern.")
    return urls
