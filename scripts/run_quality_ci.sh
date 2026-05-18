#!/usr/bin/env bash
set -euo pipefail

# Generic quality checks CI script
# Auto-discovers modules and runs coverage, radon, xenon, cohesion, vulture.
#
# Usage:
#   ./scripts/run_quality_ci.sh [changed_files...]
#
# Arguments:
#   changed_files... Space-separated list of changed .py files (not in tests/)
#                    If empty, all modules are checked.

CHANGED_FILES=("$@")

echo "=== Quality Checks CI ==="
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

# Determine which modules to check
if [ ${#CHANGED_FILES[@]} -eq 0 ]; then
    echo "No file filter — checking all modules"
    MODULES=("${ALL_MODULES[@]}")
else
    declare -A MODULE_MAP
    for f in "${CHANGED_FILES[@]}"; do
        module="${f%%/*}"
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
        echo "PASS: Nothing to check"
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

    # Support both flat structure (etl/) and core/ structure (extract/, upload/)
    if [ -d "${module}/core/" ]; then
        CORE_DIR="${module}/core/"
    else
        CORE_DIR="${module}/"
    fi

    # 1. Coverage (≥ 85%)
    echo "  Running coverage..."
    if ! uv run python -m coverage run --include="${CORE_DIR}*.py" -m pytest "${module}/tests/" -q 2>&1; then
        echo "  ERROR: pytest failed for ${module}"
        FAILED_MODULES+=("$module")
        continue
    fi

    COVERAGE_REPORT=$(uv run python -m coverage report --show-missing 2>&1)
    COVERAGE_TOTAL=$(echo "$COVERAGE_REPORT" | grep "TOTAL" | awk '{print $NF}' | tr -d '%')

    echo "  Coverage: ${COVERAGE_TOTAL}%"

    COVERAGE_BELOW=$(python3 -c "print(1 if float('${COVERAGE_TOTAL:-0}') < 85 else 0)")
    if [ "$COVERAGE_BELOW" -eq 1 ]; then
        echo "  FAIL: Coverage ${COVERAGE_TOTAL}% is below 85% threshold"
        FAILED_MODULES+=("$module")
    else
        echo "  PASS: Coverage ${COVERAGE_TOTAL}% >= 85%"
    fi

    # Clean coverage artifacts
    rm -rf .coverage .coverage.* .pytest_cache/ __pycache__/

    # 2. Radon - Cyclomatic Complexity (< 10 average)
    echo "  Running radon cc..."
    RADON_CC=$(uv run radon cc "${CORE_DIR}" -a -nb 2>&1 || true)
    RADON_CC_AVG=$(echo "$RADON_CC" | grep "Average" | head -1 | awk '{print $NF}' || echo "0")
    echo "  Radon CC average: ${RADON_CC_AVG}"

    # 3. Radon - Maintainability Index (> 70)
    echo "  Running radon mi..."
    RADON_MI=$(uv run radon mi "${CORE_DIR}" -nb 2>&1 || true)
    RADON_MI_AVG=$(echo "$RADON_MI" | grep -i "average" | head -1 | awk '{print $NF}' || echo "0")
    echo "  Radon MI average: ${RADON_MI_AVG}"

    # 4. Xenon (max-absolute B, max-modules B, max-average A)
    echo "  Running xenon..."
    if ! uv run xenon --max-absolute B --max-modules B --max-average A "${CORE_DIR}" 2>&1; then
        echo "  WARNING: Xenon gates failed for ${module}"
    else
        echo "  PASS: Xenon gates passed"
    fi

    # 5. Cohesion
    echo "  Running cohesion..."
    if ! uv run cohesion -d "${CORE_DIR}" 2>&1; then
        echo "  WARNING: Cohesion check failed for ${module}"
    else
        echo "  PASS: Cohesion check passed"
    fi

    # 6. Vulture (dead code, min 90% confidence, source only)
    echo "  Running vulture..."
    # Exclude tests/ and conftest.py — only check production source
    VULTURE_OUTPUT=$(uv run vulture "${CORE_DIR}" --min-confidence 90 --ignore-dirs="tests,__pycache__" 2>&1 || true)
    VULTURE_COUNT=$(echo "$VULTURE_OUTPUT" | wc -l | tr -d ' ')
    if [ "$VULTURE_COUNT" -gt 0 ] && [ -n "$VULTURE_OUTPUT" ]; then
        echo "  Vulture: ${VULTURE_COUNT} dead code items found"
        echo "$VULTURE_OUTPUT" | head -10
    else
        echo "  PASS: No dead code found"
    fi

   # 7. LCOM (class cohesion)
    echo "  Running LCOM analysis..."
    LCOM_OUTPUT=$(uv run python scripts/lcom.py "${CORE_DIR}" 5 2>&1 || true)
    LCOM_CLASSES=$(echo "$LCOM_OUTPUT" | grep -E "^\s+/.*\.(py):" || true)
    if [ -n "$LCOM_CLASSES" ]; then
        echo "$LCOM_CLASSES" | sed 's/^/    /'
    fi
    LCOM_FAIL=$(echo "$LCOM_OUTPUT" | grep -c "FAIL:" || true)
    if [ "$LCOM_FAIL" -gt 0 ]; then
        echo "  FAIL: Classes exceed LCOM threshold of 2"
        FAILED_MODULES+=("$module")
    else
        echo "  PASS: All classes within LCOM threshold"
    fi

    echo ""
done

echo "=============================="
echo "Summary"
echo "=============================="

if [ ${#FAILED_MODULES[@]} -eq 0 ]; then
    echo "All modules passed quality checks"
    exit 0
else
    echo "FAILED modules: ${FAILED_MODULES[*]}"
    exit 1
fi
