"""Example usage of the refactored pipeline with composition."""

import logging
from pathlib import Path

from orchestrator import PipelineOrchestrator, FileProcessor, ResultAggregator
from orchestrator.result import FileStatus
from extract.hasher import Sha256Hasher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Run the pipeline for 2009 data."""
    # Criar os componentes com composição
    processor = FileProcessor(
        download_dir=Path("/tmp/nyc_taxi_data"),
        hasher=Sha256Hasher(),
    )

    aggregator = ResultAggregator()

    # Orquestrador usa composição dos componentes
    orchestrator = PipelineOrchestrator(
        processor=processor,
        aggregator=aggregator,
    )

    # Executar pipeline apenas para 2009
    result = orchestrator.run(years=[2009])

    # Exibir resultados
    logger.info(f"\n{'='*60}")
    logger.info(f"Pipeline Resultado:")
    logger.info(f"{'='*60}")
    logger.info(f"Total: {result.total}")
    logger.info(f"Sucesso: {result.succeeded}")
    logger.info(f"Skipped: {result.skipped}")
    logger.info(f"Failed: {result.failed}")

    # Detalhes de falhas
    if result.failed > 0:
        logger.info(f"\n{'='*60}")
        logger.info("Falhas:")
        for outcome in result.files:
            if outcome.status in (FileStatus.DOWNLOAD_FAILED, FileStatus.DOWNLOAD_ERROR, FileStatus.UPLOAD_FAILED):
                logger.error(f"  {outcome.url}: {outcome.error_message}")

    return result


if __name__ == "__main__":
    main()
