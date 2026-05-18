"""LCOM (Lack of Cohesion of Methods) calculator using AST.

Implements Haack's LCOM index:
  LCOM = |{methods accessing X} ∩ {methods accessing Y}| = 0  for all pairs X,Y
  where X, Y are instance attributes.

  LCOM = (number of non-overlapping pairs) - (number of fully overlapping pairs)

  Result: negative = cohesive, positive = incohesive (split recommended)
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ClassMetrics:
    """Metrics for a single class."""

    name: str
    file: str
    lcom: int
    num_methods: int
    num_attrs: int
    overlapping_pairs: int
    non_overlapping_pairs: int


def _get_instance_vars(node: ast.ClassDef) -> set[str]:
    """Extract instance variable names from __init__ assignments."""
    vars: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.FunctionDef) or item.name != "__init__":
            continue
        for stmt in ast.walk(item):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and isinstance(
                        target.value, ast.Name
                    ):
                        if target.value.id == "self":
                            vars.add(target.attr)
            elif isinstance(stmt, ast.AnnAssign):
                if (
                    stmt.target
                    and isinstance(stmt.target, ast.Attribute)
                    and isinstance(stmt.target.value, ast.Name)
                    and stmt.target.value.id == "self"
                ):
                    vars.add(stmt.target.attr)
    return vars


def _get_attr_accesses(func_node: ast.FunctionDef) -> set[str]:
    """Get all self.attr accesses in a method."""
    accesses: set[str] = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Attribute) and isinstance(
            node.value, ast.Name
        ):
            if node.value.id == "self":
                accesses.add(node.attr)
    return accesses


def _calculate_lcom(class_node: ast.ClassDef, source_file: str) -> ClassMetrics:
    """Calculate LCOM for a single class using Haack's index."""
    instance_vars = _get_instance_vars(class_node)
    if not instance_vars:
        return ClassMetrics(
            name=class_node.name,
            file=source_file,
            lcom=0,
            num_methods=0,
            num_attrs=0,
            overlapping_pairs=0,
            non_overlapping_pairs=0,
        )

    # Get methods (exclude dunder methods except __init__)
    methods: list[ast.FunctionDef] = []
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and not item.name.startswith("__"):
            methods.append(item)

    if len(methods) < 2:
        return ClassMetrics(
            name=class_node.name,
            file=source_file,
            lcom=0,
            num_methods=len(methods),
            num_attrs=len(instance_vars),
            overlapping_pairs=0,
            non_overlapping_pairs=0,
        )

    # Get attribute accesses per method
    method_attrs: dict[str, set[str]] = {}
    for method in methods:
        method_attrs[method.name] = _get_attr_accesses(method)

    # Count overlapping and non-overlapping pairs
    overlapping = 0
    non_overlapping = 0

    for i in range(len(methods)):
        for j in range(i + 1, len(methods)):
            name_i = methods[i].name
            name_j = methods[j].name
            attrs_i = method_attrs[name_i]
            attrs_j = method_attrs[name_j]

            if attrs_i & attrs_j:  # shared attributes
                overlapping += 1
            if not (attrs_i & attrs_j):  # no shared attributes
                non_overlapping += 1

    # Haack's LCOM
    lcom = non_overlapping - overlapping

    return ClassMetrics(
        name=class_node.name,
        file=source_file,
        lcom=lcom,
        num_methods=len(methods),
        num_attrs=len(instance_vars),
        overlapping_pairs=overlapping,
        non_overlapping_pairs=non_overlapping,
    )


def analyze_file(file_path: str) -> list[ClassMetrics]:
    """Analyze all classes in a Python file."""
    source = Path(file_path).read_text()
    tree = ast.parse(source, filename=file_path)

    metrics: list[ClassMetrics] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            metrics.append(_calculate_lcom(node, file_path))

    return metrics


def analyze_directory(directory: str) -> list[ClassMetrics]:
    """Analyze all Python files in a directory recursively."""
    all_metrics: list[ClassMetrics] = []
    for py_file in Path(directory).rglob("*.py"):
        if "test" in py_file.parts or "conftest" in py_file.name:
            continue
        all_metrics.extend(analyze_file(str(py_file)))
    return all_metrics


def format_report(metrics: list[ClassMetrics]) -> str:
    """Format LCOM analysis results as a report."""
    lines = ["LCOM Analysis (Haack's Index)", "=" * 50]
    lines.append("")

    if not metrics:
        lines.append("No classes found.")
        return "\n".join(lines)

    problem_classes = [m for m in metrics if m.lcom > 0]
    cohesive_classes = [m for m in metrics if m.lcom <= 0]

    for m in sorted(metrics, key=lambda x: x.lcom, reverse=True):
        status = "SPLIT" if m.lcom > 2 else ("OK" if m.lcom <= 0 else "WARN")
        lines.append(
            f"  {m.file}:{m.name}"
        )
        lines.append(
            f"    LCOM: {m.lcom:+d}  "
            f"methods: {m.num_methods}  "
            f"attrs: {m.num_attrs}  "
            f"overlap: {m.overlapping_pairs}  "
            f"non-overlap: {m.non_overlapping_pairs}  "
            f"[{status}]"
        )
        lines.append("")

    lines.append("=" * 50)
    lines.append(f"Total classes: {len(metrics)}")
    lines.append(f"Cohesive (LCOM <= 0): {len(cohesive_classes)}")
    lines.append(f"Warning (0 < LCOM <= 2): {len(metrics) - len(cohesive_classes) - len(problem_classes)}")
    lines.append(f"Split recommended (LCOM > 2): {len(problem_classes)}")

    return "\n".join(lines)


def check_threshold(metrics: list[ClassMetrics], threshold: int = 2) -> list[ClassMetrics]:
    """Return classes exceeding the LCOM threshold."""
    return [m for m in metrics if m.lcom > threshold]


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python lcom.py <directory> [threshold]")
        sys.exit(1)

    directory = sys.argv[1]
    threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    metrics = analyze_directory(directory)
    print(format_report(metrics))

    failed = check_threshold(metrics, threshold)
    if failed:
        print(f"\nFAIL: {len(failed)} class(es) exceed LCOM threshold of {threshold}")
        for m in failed:
            print(f"  {m.file}:{m.name} (LCOM={m.lcom})")
        sys.exit(1)
    else:
        print(f"\nPASS: All classes within LCOM threshold of {threshold}")
        sys.exit(0)


if __name__ == "__main__":
    main()
