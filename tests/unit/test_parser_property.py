import pytest
from hypothesis import given, strategies as st
from extract.parser import generate_parquet_urls, VALID_DATASETS

def extract_date(url: str):
    """Helper to extract (year, month) from a taxi data URL."""
    filename = url.split("/")[-1]
    date_part = filename.split("_tripdata_")[1].replace(".parquet", "")
    year, month = map(int, date_part.split("-"))
    return (year, month)

@given(
    datasets=st.lists(st.sampled_from(list(VALID_DATASETS)), min_size=1, max_size=4),
    years=st.lists(st.integers(min_value=2000, max_value=2100), min_size=1, max_size=10),
    months=st.lists(st.integers(min_value=1, max_value=12), min_size=1, max_size=12)
)
def test_property_urls_count_and_order(datasets, years, months):
    """
    Property: For any valid set of inputs, the number of generated URLs 
    must be the product of the UNIQUE input lengths and the list must be sorted chronologically.
    """
    urls = generate_parquet_urls(datasets=datasets, years=years, months=months)
    
    # 1. Check count: unique datasets * unique years * unique months
    expected_count = len(set(datasets)) * len(set(years)) * len(set(months))
    assert len(urls) == expected_count
    
    # 2. Check chronological order (Year -> Month)
    # Extract (year, month) tuples from URLs and ensure they are non-decreasing
    dates = [extract_date(url) for url in urls]
    assert dates == sorted(dates)

@given(
    datasets=st.one_of(st.text(), st.integers(), st.booleans(), st.none()),
    years=st.lists(st.integers()),
    months=st.lists(st.integers())
)
def test_property_invalid_datasets_type(datasets, years, months):
    """
    Property: If 'datasets' is not an iterable, it should raise TypeError.
    """
    try:
        generate_parquet_urls(datasets=datasets, years=years, months=months)
    except (TypeError, ValueError):
        pass
    except Exception as e:
        pytest.fail(f"Raised unexpected exception: {type(e).__name__}: {e}")

@given(
    datasets=st.lists(st.sampled_from(list(VALID_DATASETS))),
    years=st.lists(st.integers()),
    months=st.lists(st.integers(min_value=13, max_value=1000)) # Force invalid months
)
def test_property_invalid_month_range(datasets, years, months):
    """
    Property: Any month outside [1, 12] must raise a ValueError.
    """
    if not months:
        return
        
    with pytest.raises(ValueError, match="out of valid range"):
        generate_parquet_urls(datasets=datasets, years=years, months=months)

@given(
    datasets=st.lists(st.text().filter(lambda x: x not in VALID_DATASETS), min_size=1),
    years=st.lists(st.integers()),
    months=st.lists(st.integers(min_value=1, max_value=12))
)
def test_property_invalid_dataset_names(datasets, years, months):
    """
    Property: Any dataset name not in VALID_DATASETS must raise a ValueError.
    """
    with pytest.raises(ValueError, match="Invalid dataset"):
        generate_parquet_urls(datasets=datasets, years=years, months=months)

@given(
    datasets=st.lists(st.sampled_from(list(VALID_DATASETS))),
    years=st.lists(st.one_of(st.text(), st.floats(), st.booleans()), min_size=1),
    months=st.lists(st.integers(min_value=1, max_value=12))
)
def test_property_invalid_year_types(datasets, years, months):
    """
    Property: Any non-integer year must raise a TypeError.
    """
    with pytest.raises(TypeError, match="Year must be an integer"):
        generate_parquet_urls(datasets=datasets, years=years, months=months)
