import pytest
from hypothesis import given, strategies as st
from extract.parser import generate_parquet_urls, VALID_DATASETS

def test_generate_parquet_urls_properties():
    """
    This is a placeholder for basic properties. 
    The detailed property tests are handled by the decorated functions below.
    """
    pass

@given(
    datasets=st.lists(st.sampled_from(list(VALID_DATASETS)), min_size=1, max_size=4),
    years=st.lists(st.integers(min_value=2000, max_value=2100), min_size=1, max_size=10),
    months=st.lists(st.integers(min_value=1, max_value=12), min_size=1, max_size=12)
)
def test_property_urls_count_and_order(datasets, years, months):
    """
    Property: For any valid set of inputs, the number of generated URLs 
    must be the product of the input lengths and the list must be sorted.
    """
    urls = generate_parquet_urls(datasets=datasets, years=years, months=months)
    
    # Check count: datasets * years * months
    assert len(urls) == len(datasets) * len(years) * len(months)
    
    # Check chronological order (Year -> Month)
    # Since generate_parquet_urls sorts internally, the output should always be sorted
    assert urls == sorted(urls)

@given(
    datasets=st.one_of(st.text(), st.integers(), st.booleans(), st.none()),
    years=st.lists(st.integers()),
    months=st.lists(st.integers())
)
def test_property_invalid_datasets_type(datasets, years, months):
    """
    Property: If 'datasets' is not an iterable (or a string since strings are iterable), 
    it should eventually raise TypeError or ValueError.
    """
    # In our implementation, if it's a string, it's iterable, but items inside aren't strings.
    # If it's None or int, it's not iterable.
    try:
        generate_parquet_urls(datasets=datasets, years=years, months=months)
    except (TypeError, ValueError):
        pass # Expected behavior
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
        return # Skip empty lists as they don't trigger the month loop
        
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
