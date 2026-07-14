"""
demo_ui/generator.py — Static HTML generator for the PR Grounding Gate dashboard.

Reads all /runs/*.json files and produces demo_ui/index.html:
  - git-log-style list: one line per run, colored dot (green/red/amber)
  - Each run links to a per-run Mermaid.js flow graph showing:
      Proposer → [Coverage Check, Consistency Check, Test Exec] → Verdict → Explainer
    with each node colored pass/fail
"""

import json
import os
from pathlib import Path
from datetime import datetime

RUNS_DIR    = Path(__file__).parent.parent / "runs"
OUTPUT_PATH = Path(__file__).parent / "index.html"

VERDICT_DOT_COLOR = {
    "grounded":     "#22c55e",  # green
    "ungrounded":   "#ef4444",  # red
    "needs-review": "#f59e0b",  # amber
}

VERDICT_LABEL_COLOR = {
    "grounded":     "style=filled,fillcolor=\"#22c55e\",fontcolor=white",
    "ungrounded":   "style=filled,fillcolor=\"#ef4444\",fontcolor=white",
    "needs-review": "style=filled,fillcolor=\"#f59e0b\",fontcolor=white",
}

CHECK_PASS_STYLE = "style=filled,fillcolor=\"#bbf7d0\",color=\"#22c55e\""
CHECK_FAIL_STYLE = "style=filled,fillcolor=\"#fecaca\",color=\"#ef4444\""
NODE_DEFAULT     = "style=filled,fillcolor=\"#1e293b\",color=\"#475569\",fontcolor=\"#94a3b8\""


def _mermaid_graph(run: dict) -> str:
    """Generate a Mermaid flowchart for one run."""
    gate     = run.get("gate", {})
    verdict  = run.get("verdict", {}).get("verdict", "unknown")
    cov      = gate.get("coverage",    {})
    cons     = gate.get("consistency", {})
    tex      = gate.get("test_exec",   {})

    cov_ok  = "✓ Coverage"    if cov.get("pass")  else "✗ Coverage"
    cons_ok = "✓ Consistency" if cons.get("pass") else "✗ Consistency"
    tex_ok  = "✓ Test Exec"   if tex.get("pass")  else "✗ Test Exec"

    cov_style  = "style Cov  fill:#bbf7d0,stroke:#22c55e,color:#166534" if cov.get("pass")  else "style Cov  fill:#fecaca,stroke:#ef4444,color:#7f1d1d"
    cons_style = "style Cons fill:#bbf7d0,stroke:#22c55e,color:#166534" if cons.get("pass") else "style Cons fill:#fecaca,stroke:#ef4444,color:#7f1d1d"
    tex_style  = "style Tex  fill:#bbf7d0,stroke:#22c55e,color:#166534" if tex.get("pass")  else "style Tex  fill:#fecaca,stroke:#ef4444,color:#7f1d1d"

    vcolor = {"grounded": "fill:#22c55e,stroke:#15803d,color:white",
              "ungrounded": "fill:#ef4444,stroke:#b91c1c,color:white",
              "needs-review": "fill:#f59e0b,stroke:#d97706,color:white"}.get(verdict, "fill:#64748b,color:white")

    explanation = run.get("explanation", "")[:120]

    return f"""flowchart TD
    P["🤖 Proposer\\n(Single-shot LLM)"]
    Cov["{cov_ok}"]
    Cons["{cons_ok}"]
    Tex["{tex_ok}"]
    V["⚖️ Verdict: {verdict.upper()}"]
    E["📝 Explainer\\n{explanation}"]

    P --> Cov
    P --> Cons
    P --> Tex
    Cov --> V
    Cons --> V
    Tex --> V
    V --> E

    style P fill:#3b82f6,stroke:#1d4ed8,color:white
    {cov_style}
    {cons_style}
    {tex_style}
    style V {vcolor}
    style E fill:#6366f1,stroke:#4338ca,color:white"""


def _run_card_html(run: dict) -> str:
    """Generate the HTML for one run in the git-log list."""
    name      = run.get("sample_name", "unknown")
    verdict   = run.get("verdict", {}).get("verdict", "unknown")
    explain   = run.get("explanation", "")
    ts        = run.get("run_timestamp", "")
    dot_color = VERDICT_DOT_COLOR.get(verdict, "#94a3b8")

    # Shorten timestamp for display
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        ts_display = dt.strftime("%H:%M:%S UTC")
    except Exception:
        ts_display = ts[:19]

    failing_html = ""
    failing = run.get("verdict", {}).get("failing_checks", [])
    if failing:
        badges = "".join(f'<span class="badge">{c}</span>' for c in failing)
        failing_html = f'<span class="failing-badges">{badges}</span>'

    graph_id = f"graph-{name}"
    mermaid  = _mermaid_graph(run)

    return f"""
    <div class="run-card" onclick="toggleGraph('{graph_id}')">
      <span class="dot" style="color:{dot_color}">●</span>
      <span class="run-name">{name}</span>
      <span class="verdict-label" style="color:{dot_color}">{verdict.upper()}</span>
      {failing_html}
      <span class="ts">{ts_display}</span>
      <span class="chevron" id="chevron-{graph_id}">▶</span>
    </div>
    <div class="graph-container" id="{graph_id}" style="display:none;">
      <div class="explain-box">{explain}</div>
      <div class="mermaid">{mermaid}</div>
    </div>"""


def generate_html(runs_dir: Path = RUNS_DIR, output: Path = OUTPUT_PATH):
    """Read all /runs/*.json and generate demo_ui/index.html."""
    run_files = sorted(runs_dir.glob("*.json"))
    runs = []
    for f in run_files:
        try:
            runs.append(json.loads(f.read_text()))
        except Exception:
            pass

    grounded   = sum(1 for r in runs if r.get("verdict", {}).get("verdict") == "grounded")
    ungrounded = sum(1 for r in runs if r.get("verdict", {}).get("verdict") == "ungrounded")
    review     = sum(1 for r in runs if r.get("verdict", {}).get("verdict") == "needs-review")

    cards = "\n".join(_run_card_html(r) for r in runs) if runs else "<p class='empty'>No runs yet. Run: python run_sample.py --all</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PR Grounding Gate — Run Log</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    :root {{
      --bg: #0f172a; --surface: #1e293b; --border: #334155;
      --text: #e2e8f0; --muted: #64748b; --accent: #3b82f6;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', 'Fira Code', monospace; min-height: 100vh; }}
    header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 20px 32px; display: flex; align-items: center; gap: 16px; }}
    header h1 {{ font-size: 1.4rem; color: #f8fafc; }}
    header p {{ color: var(--muted); font-size: 0.85rem; }}
    .stats {{ display: flex; gap: 24px; margin-left: auto; }}
    .stat {{ text-align: center; }}
    .stat .n {{ font-size: 1.8rem; font-weight: 700; }}
    .stat .l {{ font-size: 0.75rem; color: var(--muted); }}
    .log-container {{ max-width: 960px; margin: 32px auto; padding: 0 16px; }}
    .log-header {{ color: var(--muted); font-size: 0.8rem; padding: 8px 12px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }}
    .run-card {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 6px; cursor: pointer; transition: background .15s; border: 1px solid transparent; }}
    .run-card:hover {{ background: var(--surface); border-color: var(--border); }}
    .dot {{ font-size: 1.2rem; flex-shrink: 0; }}
    .run-name {{ flex: 1; font-size: 0.95rem; }}
    .verdict-label {{ font-size: 0.8rem; font-weight: 700; min-width: 120px; }}
    .failing-badges {{ display: flex; gap: 4px; }}
    .badge {{ background: #7f1d1d; color: #fca5a5; font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; }}
    .ts {{ color: var(--muted); font-size: 0.75rem; min-width: 100px; text-align: right; }}
    .chevron {{ color: var(--muted); font-size: 0.75rem; transition: transform .2s; }}
    .graph-container {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin: 4px 0 16px 0; }}
    .explain-box {{ background: #0f172a; border-left: 3px solid var(--accent); padding: 12px 16px; margin-bottom: 16px; font-size: 0.9rem; color: #cbd5e1; border-radius: 0 4px 4px 0; }}
    .mermaid {{ background: white; border-radius: 6px; padding: 16px; }}
    .empty {{ color: var(--muted); text-align: center; padding: 40px; }}
    footer {{ text-align: center; padding: 32px; color: var(--muted); font-size: 0.8rem; border-top: 1px solid var(--border); margin-top: 40px; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>⚖️ PR Grounding Gate</h1>
      <p>Deterministic claim verification · Proposer → Evidence Gate → Verdict</p>
    </div>
    <div class="stats">
      <div class="stat"><div class="n" style="color:#22c55e">{grounded}</div><div class="l">GROUNDED</div></div>
      <div class="stat"><div class="n" style="color:#ef4444">{ungrounded}</div><div class="l">UNGROUNDED</div></div>
      <div class="stat"><div class="n" style="color:#f59e0b">{review}</div><div class="l">NEEDS-REVIEW</div></div>
    </div>
  </header>
  <div class="log-container">
    <div class="log-header">sample · verdict · failing checks · timestamp</div>
    {cards}
  </div>
  <footer>PR Grounding Gate · Codex Community Hackathon, Gurugram, July 14 2026 · <a href="https://github.com/protocolbuffers/protobuf/pull/27848" style="color:#3b82f6">PR #27848</a></footer>
  <script>
    mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    function toggleGraph(id) {{
      const el = document.getElementById(id);
      const ch = document.getElementById('chevron-' + id);
      if (el.style.display === 'none') {{
        el.style.display = 'block';
        ch.style.transform = 'rotate(90deg)';
        mermaid.run({{ nodes: el.querySelectorAll('.mermaid') }});
      }} else {{
        el.style.display = 'none';
        ch.style.transform = '';
      }}
    }}
  </script>
</body>
</html>"""

    output.parent.mkdir(exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"[generator] Wrote {output} ({len(runs)} runs)")


if __name__ == "__main__":
    generate_html()
