#!/usr/bin/env python3
"""
summarise.py – hide bodies of functions/methods in a .py file

Usage:
    python summarise.py path/to/module.py

Requires Python ≥ 3.9 (for ast.unparse and lineno/end_lineno support).
"""

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #
def is_docstring(node: ast.AST) -> bool:
    """Return True if `node` is a standalone string literal (PEP 257 doc-string)."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def collect_body_ranges(tree: ast.AST):
    """
    Walk the AST and return a list of (start_line, end_line) tuples covering
    every function / method body.  These are used to filter out comments that
    appear *inside* bodies.
    """
    ranges = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if getattr(n, "end_lineno", None) is None:       # <3.8 fallback
                continue
            start = n.body[0].lineno if n.body else n.lineno + 1
            ranges.append((start, n.end_lineno))
    return ranges


def get_toplevel_comments(src: str, body_ranges):
    """
    Return a list of comment lines (text *including* the leading "#") that are
    • at indentation column 0, and
    • NOT located inside any recorded body range.
    """
    body_lines = set()
    for s, e in body_ranges:
        body_lines.update(range(s, e + 1))

    keep = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            line_no = tok.start[0]
            if line_no not in body_lines and tok.start[1] == 0:
                keep.append(tok.line.rstrip("\n"))
    return keep


# --------------------------------------------------------------------------- #
# AST transformer                                                             #
# --------------------------------------------------------------------------- #
class Outline(ast.NodeTransformer):
    """Remove bodies and drop everything except class / function signatures."""

    # ---- module ----
    def visit_Module(self, node: ast.Module):
        new_body = []
        if node.body and is_docstring(node.body[0]):               # keep module doc-string
            new_body.append(node.body[0])

        for child in node.body:
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self.visit(child))
        node.body = new_body
        return node

    # ---- class ----
    def visit_ClassDef(self, node: ast.ClassDef):
        new_body = []
        if node.body and is_docstring(node.body[0]):               # keep class doc-string
            new_body.append(node.body[0])

        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self.visit(child))
        node.body = new_body
        return node

    # ---- functions / methods ----
    def _strip_fn(self, node):
        new_body = []

        # keep the original doc-string, if any
        if node.body and is_docstring(node.body[0]):
            new_body.append(node.body[0])

        # insert the placeholder literal instead of `pass`
        placeholder = ast.Expr(
            value=ast.Constant(value="(implementation not shown)", kind=None)
        )
        new_body.append(placeholder)
        node.body = new_body
        return node

    visit_FunctionDef = _strip_fn
    visit_AsyncFunctionDef = _strip_fn


# --------------------------------------------------------------------------- #
# main driver                                                                 #
# --------------------------------------------------------------------------- #
def summarise(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, type_comments=True)

    # record body line-ranges *before* we mutate the tree
    body_ranges = collect_body_ranges(tree)

    # transform AST: filter nodes & strip bodies
    tree = Outline().visit(tree)
    ast.fix_missing_locations(tree)

    # gather comments to keep
    comments = get_toplevel_comments(source, body_ranges)

    # rebuild code
    pieces = []
    if comments:
        pieces.append("\n".join(comments))
    pieces.append(ast.unparse(tree))

    return "\n\n".join(pieces)

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="summarise-py",
        description="Print an outline of a Python module (function signatures only)",
    )
    parser.add_argument("path", type=Path, help="file to summarise")
    args = parser.parse_args()

    print(summarise(args.path))


if __name__ == "__main__":
    main()
