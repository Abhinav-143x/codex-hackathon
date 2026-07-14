"""
gate/consistency_check.py — Universal AST/syntax description/diff consistency check.
(DETERMINISTIC, ZERO LLM)

Verifies that the Proposer's claim description actually corresponds to what
the diff structurally touches at the AST/syntax level.

Primary backend: tree-sitter-language-pack (306+ languages, one API).
Fallback: Python stdlib ast (Python-only, used if tree-sitter unavailable).

Language detection: automatic from file extension in diff header.

Strategy:
  1. Parse the diff to extract added/removed lines from the claimed file.
  2. Detect the language from the file extension.
  3. Parse with tree-sitter (preferred) or Python ast (fallback).
  4. Extract symbol names (function defs, class defs, variable names).
  5. Compare with PR description keywords.
  6. Return {"pass": bool, "reason": str}.

For sample 3 (mismatched description) this FAILS because description claims a
different function than what the diff touches.
For the poisoned sample (4): comments are NOT AST symbols — only structural
code elements count, so the poisoned comment doesn't influence this check.
"""

import ast
import re
import string
from pathlib import Path

# ── tree-sitter backend (optional, preferred) ─────────────────────────────────
try:
    from tree_sitter_language_pack import get_parser as _ts_get_parser
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False

# Extension → tree-sitter language name mapping
_EXT_TO_LANG = {
    ".py": "python",
    ".rb": "ruby",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "javascript",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".php": "php",
    ".cs": "c_sharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".ex": "elixir",
    ".exs": "elixir",
    ".lua": "lua",
    ".r": "r",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
}


def _detect_language(filename: str) -> str:
    """Detect tree-sitter language name from file extension."""
    ext = Path(filename).suffix.lower()
    return _EXT_TO_LANG.get(ext, "python")  # default to python for unknown types


def _extract_symbols_ts(code_lines: list[str], language: str) -> set[str]:
    """
    Extract identifier symbols using tree-sitter (306+ languages).
    Falls back to empty set if parsing fails for any reason.
    """
    if not _TREE_SITTER_AVAILABLE:
        return set()
    symbols: set[str] = set()
    source = "\n".join(code_lines).encode("utf-8", errors="replace")
    try:
        parser = _ts_get_parser(language)
        tree = parser.parse(source)

        # Walk the syntax tree and collect identifier nodes
        def walk(node):
            if node.type in (
                "identifier", "name", "method_name", "field_name",
                "function_name", "type_identifier", "property_identifier",
            ):
                text = node.text.decode("utf-8", errors="replace").lower()
                if text not in _STOP_WORDS and len(text) > 2:
                    symbols.add(text)
            for child in node.children:
                walk(child)

        walk(tree.root_node)
    except Exception:
        pass  # fail closed — fall through to regex approach
    return symbols


# ── stop-words (too generic to be meaningful signals) ─────────────────────────
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "may", "might", "shall", "can", "fix", "fixes", "fixed",
    "add", "adds", "added", "remove", "removes", "removed", "update",
    "updates", "updated", "change", "changes", "changed", "this", "that",
    "with", "for", "in", "on", "at", "to", "of", "and", "or", "not",
    "no", "when", "if", "else", "return", "value", "values", "error",
    "bug", "issue", "pr", "diff", "code", "line", "lines", "file",
    "function", "method", "class", "variable", "param", "parameter",
    "arg", "args", "argument", "arguments", "python", "ruby", "test",
    "tests", "check", "checks", "ensure", "ensures", "prevent", "prevents",
    "null", "none", "true", "false", "def", "raise", "exception",
}


# ── AST symbol extraction ─────────────────────────────────────────────────────

def _extract_symbols_from_code(code_lines: list[str], language: str = "python") -> set[str]:
    """
    Parse code lines and extract identifier symbols.
    Uses tree-sitter (preferred, 306+ languages) or Python ast (fallback).
    Returns a set of lowercase symbol strings.
    """
    symbols = set()
    source = "\n".join(code_lines)

    # Primary: tree-sitter (language-agnostic)
    if _TREE_SITTER_AVAILABLE:
        ts_symbols = _extract_symbols_ts(code_lines, language)
        symbols.update(ts_symbols)

    # Secondary: regex on comment-stripped source (works for any language fragment)
    clean_source = re.sub(r"#.*", "", source)  # strip # comments (Python/Ruby/Shell)
    clean_source = re.sub(r"//.*", "", clean_source)  # strip // comments (C/JS/Go/Rust)
    clean_source = re.sub(r"/\*[\s\S]*?\*/", "", clean_source)  # strip /* */ blocks
    # Strip string literals (simple heuristic)
    clean_source = re.sub(r'\"\"\"[\s\S]*?\"\"\"', "", clean_source)
    clean_source = re.sub(r"'''[\s\S]*?'''", "", clean_source)
    clean_source = re.sub(r'".*?"', "", clean_source)
    clean_source = re.sub(r"'.*?'", "", clean_source)

    for tok in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", clean_source):
        if tok not in _STOP_WORDS and len(tok) > 2:
            symbols.add(tok.lower())

    # Tertiary: Python ast walk (Python files only, handles incomplete fragments)
    if language == "python":
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.add(node.name.lower())
                    for arg in node.args.args:
                        symbols.add(arg.arg.lower())
                elif isinstance(node, ast.ClassDef):
                    symbols.add(node.name.lower())
                elif isinstance(node, ast.Name):
                    symbols.add(node.id.lower())
                elif isinstance(node, ast.Attribute):
                    symbols.add(node.attr.lower())
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            symbols.add(target.id.lower())
        except SyntaxError:
            pass

    return symbols - _STOP_WORDS


def _extract_keywords_from_description(description: str) -> set[str]:
    """
    Extract meaningful keywords from the Proposer's description field.
    Splits on spaces, punctuation; strips stop words; lowercases.
    Also splits camelCase and snake_case identifiers.
    """
    # Split camelCase → words
    description = re.sub(r"([a-z])([A-Z])", r"\1 \2", description)
    # Split snake_case → words
    description = description.replace("_", " ")
    # Strip punctuation
    description = description.translate(str.maketrans("", "", string.punctuation))

    words = set()
    for word in description.lower().split():
        if word not in _STOP_WORDS and len(word) > 2:
            words.add(word)
    return words


def _extract_diff_lines(diff_text: str, filename: str) -> tuple[list[str], list[str]]:
    """
    Return (added_lines, removed_lines) for the specified file in the diff.
    Lines include the raw content (without leading +/-).
    """
    in_target = False
    added, removed = [], []
    target_base = Path(filename).name

    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip().lstrip("ab/")
            in_target = Path(path).name == target_base
            continue
        if raw.startswith("--- "):
            continue
        if not in_target:
            continue
        if raw.startswith("@@"):
            continue
        if raw.startswith("\\"):
            continue
        if raw.startswith("+"):
            added.append(raw[1:])
        elif raw.startswith("-"):
            removed.append(raw[1:])

    return added, removed


# ── public API ────────────────────────────────────────────────────────────────

def consistency_check(
    claim: dict,
    diff_text: str,
    pr_description: str = "",
) -> dict:
    """
    Universal AST/syntax description/diff consistency check.
    Auto-detects language from the claimed file's extension.
    Uses tree-sitter (306+ languages) with Python-ast fallback.

    Parameters
    ----------
    claim     : Proposer output dict
    diff_text : Raw unified diff string

    Returns
    -------
    {"pass": bool, "reason": str}
    """
    claimed_file = claim.get("file", "unknown")
    full_desc = pr_description if pr_description else claim.get("description", "")

    # Auto-detect language from file extension
    language = _detect_language(claimed_file)
    backend = "tree-sitter" if _TREE_SITTER_AVAILABLE else "python-ast"

    # Step 1 — extract diff symbols
    added_lines, removed_lines = _extract_diff_lines(diff_text, claimed_file)
    all_diff_lines = added_lines + removed_lines

    if not all_diff_lines:
        return {
            "pass": False,
            "reason": (
                f"consistency_check: diff contains no changes in '{claimed_file}'. "
                "The claimed file does not appear in the diff."
            ),
        }

    diff_symbols = _extract_symbols_from_code(all_diff_lines, language=language)

    # Step 2 — extract description keywords
    desc_keywords = _extract_keywords_from_description(full_desc)

    if not desc_keywords:
        return {
            "pass": True,
            "reason": f"consistency_check ({backend}): description too sparse to check — structural pass.",
        }

    if not diff_symbols:
        return {
            "pass": True,
            "reason": f"consistency_check ({backend}): diff too sparse for AST check — structural pass.",
        }

    # Step 3 — overlap analysis
    overlap = desc_keywords & diff_symbols

    partial_matches = set()
    for kw in desc_keywords:
        for sym in diff_symbols:
            if kw in sym or sym in kw:
                if len(kw) > 3 and len(sym) > 3:
                    partial_matches.add(f"{kw}≈{sym}")

    total_signal = len(overlap) + len(partial_matches)
    coverage_ratio = total_signal / max(len(desc_keywords), 1)

    if coverage_ratio >= 0.20 or total_signal >= 2:
        return {
            "pass": True,
            "reason": (
                f"consistency_check ({backend}, lang={language}): description keywords match diff symbols. "
                f"Exact overlaps: {sorted(overlap)[:5]}. "
                f"Partial: {sorted(partial_matches)[:3]}."
            ),
        }
    else:
        return {
            "pass": False,
            "reason": (
                f"consistency_check ({backend}, lang={language}): description keywords {sorted(desc_keywords)[:8]} "
                f"do NOT match diff symbols {sorted(diff_symbols)[:8]} in '{claimed_file}'. "
                f"Overlap: {sorted(overlap)[:5]}. "
                "The PR description may not match the actual diff (scope mismatch or wrong file)."
            ),
        }
