import logging
from pathlib import Path
from typing import Iterable, Optional

from extract.hasher import Hasher, Sha256Hasher
from extract.parser import generate_parquet_urls
from orchestrator.aggregator import ResultAggregator
from orchestrator.processor import FileProcessor
from orchestrator.result import FileOutcome, PipelineResult, FileStatus

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the pipeline execution using composition."""

    def __init__(
        self,
        hasher: Hasher = Sha256Hasher(),
        download_dir: Path = Path("/tmp/nyc_taxi_data"),
        bucket_name: str = "raw-data",
        bucket_path_prefix: str = "",
    ):
        self.processor = FileProcessor(download_dir, hasher)
        self.aggregator = ResultAggregator()
        self.bucket_name = bucket_name
        self.bucket_path_prefix = bucket_path_prefix

    def run(
        self,
        datasets: Optional[Iterable[str]] = None,
        years: Optional[Iterable[int]] = None,
        months: Optional[Iterable[int]] = None,
        bucket_name: str = "raw-data",
        bucket_path_prefix: str = "",
    ) -> PipelineResult:
        """Run the pipeline with the given filters.

        Args:
            datasets: Iterable of dataset names (yellow, green, fhv, hvfhv).
            years: Iterable of years to process.
            months: Iterable of months to process (1-12).
            bucket_name: Name of the S3 bucket.
            bucket_path_prefix: Prefix for the bucket path.

        Returns:
            PipelineResult with aggregated outcomes.
        """
        urls = generate_parquet_urls(datasets=datasets, years=years, months=months)

        if not urls:
            logger.warning("No URLs generated. Nothing to process.")
            return PipelineResult(total=0, succeeded=0, skipped=0, failed=0)

        logger.info(f"Processing {len(urls)} files")

        for i, url in enumerate(urls):
            logger.info(f"[{i + 1}/{len(urls)}] Processing {url}")
            try:
                outcome = self.processor.process_file(
                    url=url,
                    bucket_name=bucket_name,
                    bucket_path_prefix=bucket_path_prefix,
                )
                self.aggregator.add_outcome(outcome)
            except Exception as e:
                logger.error(f"Unexpected error processing {url}: {e}")
                outcome = self._create_error_outcome(url, str(e))
                self.aggregator.add_outcome(outcome)

        return self.aggregator.get_result()

    def _create_error_outcome(self, url: str, error_message: str) -> FileOutcome:
        """Create a FileOutcome for an unexpected error.

        Args:
            url: The URL that failed.
            error_message: The error message.

        Returns:
            FileOutcome with DOWNLOAD_ERROR status.
        """

        return FileOutcome(
            url=url,
            status=FileStatus.DOWNLOAD_ERROR,
            error_message=error_message,
        )
