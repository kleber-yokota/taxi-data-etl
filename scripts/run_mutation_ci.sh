#!/usr/bin/env bash
set -euo pipefail

# Incremental mutation testing CI script
# Only mutates modules containing changed source files.
#
# Usage:
#   ./scripts/run_mutation_ci.sh [threshold] [changed_files...]
#
# Arguments:
#   threshold        Minimum mutation score percentage (default: 85)
#   changed_files... Space-separated list of changed .py files (not in tests/)
#                    If empty, all modules are mutated (main push).

THRESHOLD="${1:-85}"
shift || true

CHANGED_FILES=("$@")

echo "=== Incremental Mutation Testing CI ==="
echo "Threshold: ${THRESHOLD}%"
echo ""

# Discover all modules: any top-level dir with Python source files and tests/
# Excludes: mutants/, .venv/, build/, dist/, __pycache__, scripts/
ALL_MODULES=()
for dir in */; do
    dir="${dir%/}"
    case "$dir" in
        mutants|.venv|build|dist|__pycache__|scripts|tests) continue ;;
    esac
    if [ -d "${dir}/tests" ] && [ "$(find "$dir" -maxdepth 2 -name "*.py" -not -path "*/tests/*" -not -name "conftest.py" 2>/dev/null | head -1)" ]; then
        ALL_MODULES+=("$dir")
    fi
done

if [ ${#ALL_MODULES[@]} -eq 0 ]; then
    echo "No modules found (directories with core/ subdir, excluding mutants/)"
    exit 1
fi

# Determine which modules to mutate
if [ ${#CHANGED_FILES[@]} -eq 0 ]; then
    echo "No file filter — mutating all modules (main push)"
    MODULES=("${ALL_MODULES[@]}")
else
    # Map changed source files to their parent modules
    declare -A MODULE_MAP
    for f in "${CHANGED_FILES[@]}"; do
        # Extract top-level module (e.g. "extract/foo.py" -> "extract")
        module="${f%%/*}"
        # Only care about known modules
        for m in "${ALL_MODULES[@]}"; do
            if [ "$module" = "$m" ]; then
                MODULE_MAP["$m"]=1
                break
            fi
        done
    done

    MODULES=("${!MODULE_MAP[@]}")

    if [ ${#MODULES[@]} -eq 0 ]; then
        echo "No Python source files changed in any module"
        echo "PASS: Nothing to mutate"
        exit 0
    fi

    echo "Changed files: ${CHANGED_FILES[*]}"
    echo "Affected modules: ${MODULES[*]}"
fi

echo ""

FAILED_MODULES=()

for module in "${MODULES[@]}"; do
    echo "=============================="
    echo "Module: ${module}"
    echo "=============================="

    rm -rf mutants/

    TEST_DIR="${module}/tests/"
    if [ ! -d "$TEST_DIR" ]; then
        echo "  WARNING: No tests/ directory, skipping"
        continue
    fi

    # Find unit test files
    UNIT_TESTS=()
    while IFS= read -r -d '' f; do
        basename_f=$(basename "$f")
        case "$basename_f" in
            test_fuzz.py|test_e2e*.py|test_properties.py|test_helpers.py|test_mutant_killing.py)
                continue ;;
            test_*.py)
                UNIT_TESTS+=("$f") ;;
        esac
    done < <(find "$TEST_DIR" -name "test_*.py" -type f -print0)

    if [ ${#UNIT_TESTS[@]} -eq 0 ]; then
        echo "  WARNING: No unit test files found, skipping"
        continue
    fi

    echo "  Unit tests: ${UNIT_TESTS[*]}"
    TEST_CMD="python -m pytest ${UNIT_TESTS[*]} -q"

    # Save original pyproject.toml
    ORIGINAL_PYPROJECT=$(cat pyproject.toml)

    cat > pyproject.toml <<PYEOF
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "nyc-taxi-clickhouse-etl"
version = "0.1.0"
requires-python = ">=3.11"

[tool.mutmut]
paths_to_mutate = ["${module}"]
do_not_mutate = ["*/tests/*", "*/conftest.py", "*/test_*.py", "*/__init__.py"]
runner = "${TEST_CMD}"
exclude_dirs = ["__pycache__", ".venv", "mutants"]
PYEOF

    echo "  Running mutmut (parallel)..."
    MUTMUT_OUTPUT=$(mktemp)
    if ! mutmut run --max-children 8 >"$MUTMUT_OUTPUT" 2>&1; then
        echo "  ERROR: mutmut run failed for ${module}"
        cat "$MUTMUT_OUTPUT"
        rm -f "$MUTMUT_OUTPUT"
        rm -f pyproject.toml
        echo "$ORIGINAL_PYPROJECT" > pyproject.toml
        FAILED_MODULES+=("$module")
        continue
    fi
    rm -f "$MUTMUT_OUTPUT"

    mutmut export-cicd-stats 2>/dev/null || true

    # Restore original pyproject.toml
    rm -f pyproject.toml
    echo "$ORIGINAL_PYPROJECT" > pyproject.toml

    # Calculate and check score
    if [ -f "mutants/mutmut-cicd-stats.json" ]; then
        SCORE_OUTPUT=$(python3 -c "
import json
with open('mutants/mutmut-cicd-stats.json') as f:
    d = json.load(f)
    killed = d['killed']
    total = d['killed'] + d['survived'] + d['timeout'] + d['skipped']
    score = killed / total * 100 if total else 0
    print(f'{score:.1f}')
    print(f'  Killed: {killed}/{total}')
")
        SCORE=$(echo "$SCORE_OUTPUT" | head -1)
        DETAILS=$(echo "$SCORE_OUTPUT" | tail -n +2)
    else
        SCORE="0.0"
        DETAILS="  Killed: 0/0 (no mutants generated)"
    fi

    echo "  Mutation score: ${SCORE}%"
    echo "$DETAILS"

    BELOW=$(python3 -c "print(1 if float('${SCORE}') < ${THRESHOLD} else 0)")
    if [ "$BELOW" -eq 1 ]; then
        echo "  FAIL: Score ${SCORE}% is below ${THRESHOLD}% threshold"
        FAILED_MODULES+=("$module")
    else
        echo "  PASS: Score ${SCORE}% >= ${THRESHOLD}%"
    fi
    echo ""
done

echo "=============================="
echo "Summary"
echo "=============================="

if [ ${#FAILED_MODULES[@]} -eq 0 ]; then
    echo "All modules passed mutation testing (>= ${THRESHOLD}%)"
    exit 0
else
    echo "FAILED modules: ${FAILED_MODULES[*]}"
    exit 1
fi
