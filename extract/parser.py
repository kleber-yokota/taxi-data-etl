import httpx
from bs4 import BeautifulSoup
from typing import Set
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TLCParser:
    """
    Responsible for parsing the NYC TLC website to discover available 
    trip record data in Parquet format.
    """
    
    def __init__(self, base_url: str):
        """
        Initialize the parser.

        Args:
            base_url (str): The URL of the NYC TLC trip record data page.
        """
        self.base_url = base_url
        self.client = httpx.Client(follow_redirects=True, timeout=30.0)

    def fetch_parquet_urls(self) -> Set[str]:
        """
        Scrapes the NYC TLC page to find all links ending in .parquet.

        Returns:
            Set[str]: A set of absolute URLs to Parquet files.
        """
        logger.info(f"Fetching Parquet URLs from: {self.base_url}")
        try:
            response = self.client.get(self.base_url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Error fetching URLs from {self.base_url}: {e}")
            raise

        soup = BeautifulSoup(response.text, "html.parser")
        links = set()
        
        for a in soup.find_all("a", href=True):
            url = a["href"]
            if url.endswith(".parquet"):
                if url.startswith("/"):
                    url = f"https://www.nyc.gov{url}"
                links.add(url)
                
        logger.info(f"Found {len(links)} Parquet files.")
        return links
