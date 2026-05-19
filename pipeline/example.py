"""Simples exemplo de uso do pipeline refatorado."""

from pathlib import Path

from pipeline import PipelineOrchestrator
from pipeline.result import FileStatus
from extract.hasher import Sha256Hasher


def run_pipeline_2009():
    """Executa o pipeline apenas para dados de 2009."""
    
    # 1. Criar o orchestrator com composição
    orchestrator = PipelineOrchestrator(
        hasher=Sha256Hasher(),
        download_dir=Path("/tmp/nyc_taxi_data"),
        bucket_name="raw-data",
        bucket_path_prefix="",
    )
    
    # 2. Executar com filtro de ano
    result = orchestrator.run(years=[2009])
    
    # 3. Exibir resultados
    print(f"\nTotal: {result.total}")
    print(f"Sucesso: {result.succeeded}")
    print(f"Skipped: {result.skipped}")
    print(f"Failed: {result.failed}")
    
    return result


if __name__ == "__main__":
    run_pipeline_2009()
