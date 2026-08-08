"""AST scan: no production device.confidence mutation outside approved modules."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APPROVED = {
    "entity_resolution/confidence_ledger.py",
    "entity_resolution/confidence_service.py",
}

# files that may construct Device(confidence=0) but not mutate later in production
SKIP_DIRS = {"tests", "demo", "__pycache__", "alembic", "migrations"}


class ConfidenceWriteVisitor(ast.NodeVisitor):
    def __init__(self):
        self.hits: list[tuple[int, str]] = []

    def visit_Assign(self, node: ast.Assign):
        for t in node.targets:
            self._check_target(t, node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        self._check_target(node.target, node.lineno)
        self.generic_visit(node)

    def _check_target(self, t, lineno: int):
        # device.confidence = ...  or  device.confidence += ...
        if isinstance(t, ast.Attribute) and t.attr == "confidence":
            # ignore knowledge result.confidence and similar non-device if we can
            self.hits.append((lineno, ast.dump(t)))


def scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    v = ConfidenceWriteVisitor()
    v.visit(tree)
    return v.hits


def test_no_illegal_confidence_writes():
    illegal = []
    scanned = 0
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel in APPROVED:
            continue
        scanned += 1
        for lineno, dump in scan_file(path):
            # filter: only attribute named confidence on something that looks like device
            # Allow EnrichedKnowledge / validation result style in knowledge/
            if rel.startswith("knowledge/") or rel.startswith("models/"):
                continue
            if rel.startswith("alerts/"):
                continue
            if "knowledge_confidence" in dump:
                continue
            illegal.append(f"{rel}:{lineno} {dump}")
    print(f"Production files scanned: {scanned}")
    print(f"Approved confidence writers: {len(APPROVED)}")
    print(f"Illegal writes: {len(illegal)}")
    for i in illegal:
        print("  ILLEGAL", i)
    assert not illegal, illegal


if __name__ == "__main__":
    test_no_illegal_confidence_writes()
    print("confidence write enforcement passed")
