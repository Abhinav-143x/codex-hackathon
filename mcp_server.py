"""
mcp_server.py — FastMCP server exposing all Gate checks as MCP tools.

Any MCP-compatible agent (Claude Code, Codex, Cursor, etc.) can call these tools
to verify a PR diff without embedding the Gate logic itself.

Run: python mcp_server.py
Then add to your MCP client config:
  {
    "mcpServers": {
      "prgg-gate": {
        "command": "python",
        "args": ["path/to/mcp_server.py"]
      }
    }
  }
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastmcp import FastMCP

mcp = FastMCP(
    name="prgg-gate",
    version="0.1.0",
)


@mcp.tool
def coverage_check_tool(claim: dict, diff_text: str) -> dict:
    """
    Check whether the PR's diff actually improves coverage on the claimed lines.
    Deterministic — no LLM involved.
    Returns {"pass": bool, "reason": str}.
    """
    from gate.coverage_check import coverage_check
    return coverage_check(claim, diff_text)


@mcp.tool
def consistency_check_tool(claim: dict, diff_text: str, pr_description: str = "") -> dict:
    """
    Check whether the PR description's keywords match the AST symbols in the diff.
    Catches description-vs-diff scope mismatches. Deterministic — no LLM.
    Returns {"pass": bool, "reason": str}.
    """
    from gate.consistency_check import consistency_check
    return consistency_check(claim, diff_text, pr_description=pr_description)


@mcp.tool
def test_exec_check_tool(claim: dict, diff_text: str, sample_name: str = "") -> dict:
    """
    Run the project's real test suite against the claimed fix.
    For the protobuf Ruby sample: runs the actual test command live.
    Returns {"pass": bool, "reason": str}.
    """
    from gate.test_exec_check import test_exec_check
    return test_exec_check(claim, diff_text, sample_name=sample_name)


@mcp.tool
def blind_spot_check_tool(diff_text: str) -> dict:
    """
    Detect binary/image files in the diff that cannot be fully inspected.
    Per GhostCommit (June 2026): this exact blind spot let CodeRabbit and Cursor Bugbot
    miss a real exploit hidden in a PNG. Never lets unreadable files default to safe.
    Returns {"pass": bool, "reason": str}.
    """
    from gate.blind_spot_check import blind_spot_check
    return blind_spot_check(diff_text)


@mcp.tool
def invisible_unicode_check_tool(diff_text: str, pr_description: str = "") -> dict:
    """
    Detect invisible Unicode (tag block, zero-width, bidi override) in diff or description.
    These are documented prompt-injection vectors. Fail-closed — never silently passes.
    Returns {"pass": bool, "reason": str}.
    """
    from gate.invisible_unicode_check import invisible_unicode_check
    return invisible_unicode_check(diff_text, pr_description)


@mcp.tool
def run_full_gate(claim: dict, diff_text: str, pr_description: str = "", sample_name: str = "") -> dict:
    """
    Run ALL Gate checks in sequence and return a complete verdict.
    This is the full Proposer → Gate → Verdict pipeline in one tool call.
    Returns the full verdict dict with check results, failing_checks, and verdict string.
    """
    import concurrent.futures
    from gate.coverage_check import coverage_check
    from gate.consistency_check import consistency_check
    from gate.test_exec_check import test_exec_check
    from gate.blind_spot_check import blind_spot_check
    from gate.invisible_unicode_check import invisible_unicode_check
    import verdict as verdict_mod

    def safe(fn, *args, name="check", **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            return {"pass": False, "reason": f"{name}: error — {type(exc).__name__}: {exc}"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        f_cov   = pool.submit(safe, coverage_check, claim, diff_text, name="coverage_check")
        f_cons  = pool.submit(safe, consistency_check, claim, diff_text, pr_description, name="consistency_check")
        f_tex   = pool.submit(safe, test_exec_check, claim, diff_text, name="test_exec_check")
        f_blind = pool.submit(safe, blind_spot_check, diff_text, name="blind_spot_check")
        f_uni   = pool.submit(safe, invisible_unicode_check, diff_text, pr_description, name="invisible_unicode_check")

        cov_r  = f_cov.result()
        cons_r = f_cons.result()
        tex_r  = f_tex.result()
        blind_r = f_blind.result()
        uni_r  = f_uni.result()

    return verdict_mod.compute_verdict(
        cov_r, cons_r, tex_r,
        claim=claim,
        sample_name=sample_name,
        blind_spot_result=blind_r,
        unicode_result=uni_r,
    )


if __name__ == "__main__":
    mcp.run()
