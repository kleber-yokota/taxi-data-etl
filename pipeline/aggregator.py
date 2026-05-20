import logging
from typing import List

from pipeline.result import FileOutcome, FileStatus, PipelineResult

logger = logging.getLogger(__name__)


class ResultAggregator:
    """Aggregates file processing results."""

    def __init__(self):
        self.outcomes: List[FileOutcome] = []
        self.succeeded = 0
        self.skipped = 0
        self.failed = 0

    def add_outcome(self, outcome: FileOutcome):
        """Add an outcome and update counters.

        Args:
            outcome: The FileOutcome to add.
        """
        self.outcomes.append(outcome)
        if outcome.status == FileStatus.SUCCESS:
            self.succeeded += 1
        elif outcome.status == FileStatus.SKIPPED:
            self.skipped += 1
        else:
            self.failed += 1

    def get_result(self) -> PipelineResult:
        """Get the aggregated PipelineResult.

        Returns:
            PipelineResult with totals and all outcomes.
        """
        return PipelineResult(
            total=len(self.outcomes),
            succeeded=self.succeeded,
            skipped=self.skipped,
            failed=self.failed,
            files=self.outcomes,
        )
