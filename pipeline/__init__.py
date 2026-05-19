"""Pipeline module for processing NYC taxi data files using composition."""

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.processor import FileProcessor
from pipeline.aggregator import ResultAggregator
from pipeline.result import FileOutcome, FileStatus, PipelineResult, _classify_file

__all__ = [
    "PipelineOrchestrator",
    "FileProcessor",
    "ResultAggregator",
    "FileOutcome",
    "FileStatus",
    "PipelineResult",
    "_classify_file",
]
