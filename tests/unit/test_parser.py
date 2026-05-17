import pytest
from extract.parser import generate_parquet_urls

def test_generate_parquet_urls_correct_count():
    """Test that the number of generated URLs is correct (datasets * years * months)."""
    datasets = ["yellow", "green"]
    years = [2023]
    months = [1, 2]
    
    urls = generate_parquet_urls(datasets, years, months)
    
    # 2 datasets * 1 year * 2 months = 4 urls
    assert len(urls) == 4

def test_generate_parquet_urls_pattern():
    """Test that the generated URLs follow the expected S3 pattern."""
    datasets = ["yellow"]
    years = [2023]
    months = [1]
    
    urls = generate_parquet_urls(datasets, years, months)
    expected_url = "https://d37ci68n02y6s.cloudfront.net/trip-data/yellow_tripdata_2023-01.parquet"
    
    assert expected_url in urls

def test_generate_parquet_urls_month_formatting():
    """Test that months are correctly formatted as two digits (e.g., 1 -> 01)."""
    datasets = ["green"]
    years = [2022]
    months = [5]
    
    urls = generate_parquet_urls(datasets, years, months)
    expected_url = "https://d37ci68n02y6s.cloudfront.net/trip-data/green_tripdata_2022-05.parquet"
    
    assert expected_url in urls
