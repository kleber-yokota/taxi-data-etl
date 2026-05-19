#!/usr/bin/env bash
set -euo pipefail

# Generic quality checks CI script
# Auto-discovers modules and runs coverage, radon, xenon, cohesion, vulture, lcom.
#
# Usage:
#   ./scripts/run_quality_ci.sh [changed_files...]

CHANGED_FILES=("$@")

echo "=== Quality Checks CI ==="
echo ""

# Discover all source modules: any top-level dir with Python source files.
# Excludes: mutants/, .venv/, build/, dist/, __pycache__, scripts/, tests/
ALL_MODULES=()
for dir in */; do
    dir="${dir%/}"
    case "$dir" in
        mutants|.venv|build|dist|__pycache__|scripts|tests) continue ;;
    esac
    if [ "$(find "$dir" -maxdepth 2 -name "*.py" -not -name "conftest.py" 2>/dev/null | head -1)" ]; then
        ALL_MODULES+=("$dir")
    fi
done

if [ ${#ALL_MODULES[@]} -eq 0 ]; then
    echo "No modules found"
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

    CORE_DIR="${module}/"
    MODULE_FAILED=0

    # 1. Coverage (≥ 85%)
    echo "  Running coverage..."
    if ! uv run python -m coverage run --include="${CORE_DIR}*.py" -m pytest tests/unit/ tests/e2e/ -q 2>&1; then
        echo "  FAIL: pytest failed for ${module}"
        FAILED_MODULES+=("$module")
        continue
    fi

    COVERAGE_REPORT=$(uv run python -m coverage report --show-missing 2>&1)
    COVERAGE_TOTAL=$(echo "$COVERAGE_REPORT" | grep "^TOTAL" | awk '{print $NF}' | tr -d '%')

    echo "  Coverage: ${COVERAGE_TOTAL}%"
    if python3 -c "import sys; sys.exit(0 if float('${COVERAGE_TOTAL:-0}') >= 85 else 1)"; then
        echo "  PASS: Coverage ${COVERAGE_TOTAL}% >= 85%"
    else
        echo "  FAIL: Coverage ${COVERAGE_TOTAL}% is below 85%"
        MODULE_FAILED=1
    fi

    rm -rf .coverage .coverage.* .pytest_cache/ __pycache__/

    # 2. Radon CC — informational only, no hard gate
    echo "  Running radon cc..."
    RADON_CC_OUTPUT=$(uv run radon cc "${CORE_DIR}" -a -nb 2>&1 || true)
    # radon outputs "Average complexity: A (1.5)" — extract the number in parens
    RADON_CC_AVG=$(echo "$RADON_CC_OUTPUT" | grep -oP 'Average complexity: \w+ \(\K[0-9.]+' || echo "n/a")
    echo "  Radon CC average: ${RADON_CC_AVG}"

    # 3. Radon MI — informational only
    echo "  Running radon mi..."
    RADON_MI_OUTPUT=$(uv run radon mi "${CORE_DIR}" 2>&1 || true)
    # radon mi outputs lines like "extract/foo.py - A"
    echo "  Radon MI: $(echo "$RADON_MI_OUTPUT" | grep -v '^$' | head -5 || echo 'n/a')"

    # 4. Xenon — hard gate
    echo "  Running xenon..."
    if ! uv run xenon --max-absolute B --max-modules B --max-average A "${CORE_DIR}" 2>&1; then
        echo "  FAIL: Xenon complexity gates failed for ${module}"
        MODULE_FAILED=1
    else
        echo "  PASS: Xenon gates passed"
    fi

    # 5. Cohesion — hard gate
    echo "  Running cohesion..."
    if ! uv run cohesion -d "${CORE_DIR}" 2>&1; then
        echo "  FAIL: Cohesion check failed for ${module}"
        MODULE_FAILED=1
    else
        echo "  PASS: Cohesion check passed"
    fi

    # 6. Vulture — hard gate
    echo "  Running vulture..."
    # --exclude takes glob patterns; --ignore-dirs is not a valid flag
    VULTURE_OUTPUT=$(uv run vulture "${CORE_DIR}" --min-confidence 90 --exclude "*/__pycache__/*" 2>&1 || true)
    # Only count actual findings (file:line: pattern), ignore stderr noise
    VULTURE_FINDINGS=$(echo "$VULTURE_OUTPUT" | grep -E "^[^:]+:[0-9]+:" || true)
    if [ -n "$VULTURE_FINDINGS" ]; then
        VULTURE_COUNT=$(echo "$VULTURE_FINDINGS" | wc -l | tr -d ' ')
        echo "  FAIL: Vulture found ${VULTURE_COUNT} dead code item(s):"
        echo "$VULTURE_FINDINGS" | sed 's/^/    /'
        MODULE_FAILED=1
    else
        echo "  PASS: No dead code found"
    fi

    # 7. LCOM — hard gate
    echo "  Running LCOM analysis..."
    LCOM_OUTPUT=$(uv run python scripts/lcom.py "${CORE_DIR}" 5 2>&1 || true)
    if echo "$LCOM_OUTPUT" | grep -q "^FAIL:"; then
        echo "$LCOM_OUTPUT" | grep -E "^FAIL:|^\s+" | sed 's/^/    /'
        echo "  FAIL: Classes exceed LCOM threshold"
        MODULE_FAILED=1
    else
        echo "  PASS: All classes within LCOM threshold"
    fi

    if [ "$MODULE_FAILED" -eq 1 ]; then
        FAILED_MODULES+=("$module")
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
