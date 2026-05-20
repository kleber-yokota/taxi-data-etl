# taxi-data-etl

ETL pipeline that ingests NYC TLC taxi data into ClickHouse for OLAP analytics — built with a local LLM as a core part of the development workflow.

**Stack**: Python · AWS S3 · ClickHouse · Docker · GitHub Actions · opencode + Qwen (local)

---

## AI-assisted development

This project was built using [opencode](https://opencode.ai) with a locally-run Qwen model as a coding assistant — no cloud API, no SaaS, just a local LLM integrated into the development workflow.

The goal was to treat the LLM as a practical engineering tool, not a gimmick. Here's where it actually helped:

**Boilerplate and scaffolding** — generating the initial structure for modules like `extract/`, `upload/`, and test files. The LLM produced first drafts quickly; I refined and validated each one.

**Test case generation** — suggesting edge cases for fuzz and unit tests (malformed dates, empty fields, boundary values). Useful as a starting point, though several suggestions needed corrections or were discarded.

**Refactoring assistance** — proposing cleaner implementations during code review loops, particularly for error handling and module boundaries.

**Prompt engineering as a skill** — getting useful output consistently required well-structured prompts with explicit context about the codebase. Vague prompts produced generic code. This itself is a transferable skill: knowing how to direct an LLM toward a specific engineering goal.

What the LLM did not replace: architectural decisions, debugging non-obvious failures, understanding why mutmut survivors indicated weak assertions, and deciding what to test in the first place. Those required engineering judgment.

The workflow — LLM for speed, human review for correctness — is the pattern I'd apply in a team setting.

---

## What it does

1. **Extract** — downloads NYC TLC trip record files (Parquet) from the public dataset
2. **Upload** — stages raw files to AWS S3
3. **Orchestrate** — coordinates the pipeline steps and manages execution flow
4. **Load** — ingests data into ClickHouse for analytical queries

---

## Project structure

```
taxi-data-etl/
├── extract/          # Download and parse NYC TLC Parquet files
├── upload/           # Upload raw data to S3
├── orchestrator/     # Pipeline coordination
├── scripts/          # Utility scripts
├── tests/
│   ├── unit/         # Unit tests
│   ├── e2e/          # End-to-end tests using Testcontainers (MinIO)
│   └── fuzz/         # Fuzz tests via Hypothesis and Atheris
├── .github/workflows/ # CI/CD pipelines
└── pyproject.toml
```

---

## Testing strategy

The project uses a layered approach to testing, where each layer serves a different purpose:

**Unit tests** catch logic errors fast during development. Fast feedback loop.

**End-to-end tests** validate the full pipeline flow using real infrastructure locally via Testcontainers (MinIO as S3-compatible storage). If the E2E suite passes, the pipeline works end-to-end.

**Fuzz tests** (Hypothesis + Atheris) throw malformed and unexpected inputs at the pipeline to surface edge cases that manual tests miss — empty strings, null values, invalid date formats, negative numbers in numeric fields. Any input the real world might send.

**Mutation testing** (mutmut) verifies that the test suite actually catches bugs. It introduces small deliberate changes to the source code and checks whether at least one test fails. If tests pass with a mutation, that's a weak test worth fixing. Paths covered: `extract/` and `upload/`.

**Code quality analysis** uses radon, xenon, and cohesion to track cyclomatic complexity and module cohesion, making it easier to spot code that is becoming hard to maintain before it becomes a problem.

---

## Key dependencies

| Dependency | Purpose |
|---|---|
| `httpx` | HTTP client for downloading TLC data |
| `boto3` | AWS S3 integration |
| `python-dotenv` | Environment config |
| `pytest` + `pytest-cov` | Test runner and coverage |
| `mutmut` | Mutation testing |
| `hypothesis` | Property-based and fuzz testing |
| `atheris` | Coverage-guided fuzzing |
| `testcontainers[minio]` | Local S3-compatible storage for E2E tests |
| `vcrpy` + `respx` | HTTP mocking for unit tests |
| `radon` / `xenon` / `cohesion` | Code quality metrics |

---

## Setup

**Requirements**: Python 3.11+, Docker (for E2E tests), AWS credentials (or MinIO locally)

```bash
# Install dependencies
uv sync --all-groups

# Copy and fill in environment variables
cp .env.example .env

# Run unit tests
pytest tests/unit

# Run E2E tests (requires Docker)
pytest tests/e2e

# Run mutation tests
mutmut run
```

---

## CI/CD

GitHub Actions runs the test suite on every push. The pipeline covers unit tests and linting at minimum; E2E and mutation tests can be run manually or on schedule depending on resource cost.

---

## Why ClickHouse

ClickHouse is an OLAP database designed for fast analytical queries on large datasets. The NYC TLC dataset spans hundreds of millions of rows across several years. ClickHouse handles column-oriented scans on this scale efficiently — queries that would be slow on a row-oriented database like Postgres run in seconds.

---

## Contact

- LinkedIn: [linkedin.com/in/kleber-yokota](https://www.linkedin.com/in/kleber-yokota/)
- GitHub: [github.com/kleber-yokota](https://github.com/kleber-yokota)
