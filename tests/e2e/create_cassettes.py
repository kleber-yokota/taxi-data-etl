"""
Script para gerar os cassettes VCR dos testes E2E.

Execute UMA VEZ em uma máquina com acesso à internet:

    python tests/e2e/create_cassettes.py

Os cassettes gerados em tests/e2e/cassettes/ devem ser commitados no repositório.
A partir daí os testes E2E rodam offline sem rede e sem patches.
"""

import hashlib
import sys
from pathlib import Path

import httpx
import yaml

CASSETTE_DIR = Path("tests/e2e/cassettes")
SAMPLE_BYTES = 5 * 1024 * 1024  # 5 MB

try:
    from extract.parser import generate_parquet_urls

    TEST_URL = generate_parquet_urls(datasets=["yellow"], years=[2015], months=[1])[0]
except Exception as e:
    print(f"Erro ao importar generate_parquet_urls: {e}")
    sys.exit(1)


def fetch_head(client: httpx.Client, url: str) -> dict:
    print(f"  HEAD {url}")
    resp = client.head(url)
    resp.raise_for_status()
    # Cap Content-Length to SAMPLE_BYTES so is_download_required() sees the
    # same size as the file on disk during idempotency checks.
    headers = dict(resp.headers)
    headers["content-length"] = str(SAMPLE_BYTES)
    return {
        "status": {"code": resp.status_code, "message": "OK"},
        "headers": {k: [v] for k, v in headers.items()},
        "body": {"string": b""},
        "url": str(resp.url),
    }


def fetch_get_sample(client: httpx.Client, url: str) -> dict:
    print(f"  GET  {url}  (primeiros {SAMPLE_BYTES // 1024 // 1024} MB)")
    resp = client.get(url, headers={"Range": f"bytes=0-{SAMPLE_BYTES - 1}"})
    resp.raise_for_status()
    body = resp.content[:SAMPLE_BYTES]
    headers = dict(resp.headers)
    headers["content-length"] = str(len(body))
    return {
        "status": {"code": resp.status_code, "message": resp.reason_phrase},
        "headers": {k: [v] for k, v in headers.items()},
        "body": {"string": body},
        "url": str(resp.url),
    }


def make_request(method: str, url: str, headers: dict | None = None) -> dict:
    return {
        "method": method,
        "uri": url,
        "body": None,
        "headers": headers or {},
    }


def interaction(request: dict, response: dict) -> dict:
    return {"request": request, "response": response}


def mock_error_response(url: str, status_code: int, status_text: str) -> dict:
    return {
        "status": {"code": status_code, "message": status_text},
        "headers": {},
        "body": {"string": b""},
        "url": url,
    }


def write_cassette(path: Path, interactions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(
            {"version": 1, "interactions": interactions},
            f,
            allow_unicode=True,
            default_flow_style=False,
        )
    print(f"  -> {path}  ({path.stat().st_size // 1024} KB)\n")


def main():
    print(f"URL: {TEST_URL}\n")

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        head = fetch_head(client, TEST_URL)
        get = fetch_get_sample(client, TEST_URL)

    # --- downloader_success.yaml ---
    # Fluxo normal: HEAD + GET
    print("[1/5] downloader_success.yaml")
    write_cassette(
        CASSETTE_DIR / "downloader_success.yaml",
        interactions=[
            interaction(make_request("HEAD", TEST_URL), head),
            interaction(make_request("GET", TEST_URL), get),
        ],
    )

    # --- downloader_idempotency.yaml ---
    # 1st call: HEAD + GET
    # 2nd call: HEAD only (file already exists with correct size)
    print("[2/5] downloader_idempotency.yaml")
    write_cassette(
        CASSETTE_DIR / "downloader_idempotency.yaml",
        interactions=[
            interaction(make_request("HEAD", TEST_URL), head),
            interaction(make_request("GET", TEST_URL), get),
            interaction(make_request("HEAD", TEST_URL), head),  # 2nd call, no GET
        ],
    )

    # --- downloader_checksum_fail.yaml ---
    # HEAD + GET, mas o teste passa um hash errado — ValueError esperado
    print("[3/5] downloader_checksum_fail.yaml")
    write_cassette(
        CASSETTE_DIR / "downloader_checksum_fail.yaml",
        interactions=[
            interaction(make_request("HEAD", TEST_URL), head),
            interaction(make_request("GET", TEST_URL), get),
        ],
    )

    # --- downloader_not_found.yaml ---
    # Simula 404 Not Found no HEAD request
    print("[4/5] downloader_not_found.yaml")
    write_cassette(
        CASSETTE_DIR / "downloader_not_found.yaml",
        interactions=[
            interaction(
                make_request("HEAD", TEST_URL),
                mock_error_response(TEST_URL, 404, "Not Found"),
            ),
        ],
    )

    # --- downloader_forbidden.yaml ---
    # Simula 403 Forbidden no HEAD request
    print("[5/5] downloader_forbidden.yaml")
    write_cassette(
        CASSETTE_DIR / "downloader_forbidden.yaml",
        interactions=[
            interaction(
                make_request("HEAD", TEST_URL),
                mock_error_response(TEST_URL, 403, "Forbidden"),
            ),
        ],
    )

    print("Cassettes gerados. Commit tests/e2e/cassettes/ para usar offline.")


if __name__ == "__main__":
    main()
