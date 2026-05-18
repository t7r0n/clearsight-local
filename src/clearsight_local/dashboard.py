from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, select_autoescape

from clearsight_local.models import SuiteSummary, project_root
from clearsight_local.runner import outputs_dir, run_suite


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clearsight Intent Dashboard</title>
  <style>
    :root { color-scheme: light; --bg:#f8faf7; --panel:#fff; --text:#17211d; --muted:#63716b; --line:#dce8e2; --blue:#426fd2; --green:#22966d; --red:#d85c5c; --track:#edf3ef; }
    html[data-theme="dark"] { color-scheme: dark; --bg:#101614; --panel:#18211e; --text:#eef7f2; --muted:#a5b4ad; --line:#2d3b35; --track:#26332e; }
    * { box-sizing:border-box; }
    body { margin:0; overflow-x:hidden; background:var(--bg); color:var(--text); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width:1180px; margin:0 auto; padding:32px 20px 48px; }
    header { display:flex; justify-content:space-between; gap:16px; align-items:end; margin-bottom:26px; }
    h1 { margin:0 0 8px; font-size:32px; line-height:1.08; letter-spacing:0; }
    h2 { margin:0 0 14px; font-size:22px; letter-spacing:0; }
    p { margin:0; color:var(--muted); }
    .actions { display:flex; gap:10px; align-items:center; }
    .pill,.toggle { border:1px solid var(--line); border-radius:999px; padding:8px 12px; background:var(--panel); color:var(--text); font:inherit; font-size:13px; white-space:nowrap; }
    .toggle { cursor:pointer; }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; }
    .metric span { color:var(--muted); font-size:13px; }
    .metric strong { display:block; margin-top:8px; font-size:28px; }
    .wide { grid-column:span 2; }
    .full { grid-column:1/-1; }
    .bar { display:grid; grid-template-columns:minmax(210px, 0.8fr) 1fr 72px; gap:12px; align-items:center; margin:12px 0; }
    .bar span { overflow-wrap:anywhere; }
    .track { height:13px; border-radius:999px; background:var(--track); overflow:hidden; }
    .fill { height:100%; border-radius:999px; background:var(--blue); }
    .ok { color:var(--green); font-weight:700; }
    .bad { color:var(--red); font-weight:700; }
    .table-wrap { width:100%; overflow-x:auto; }
    table { width:100%; border-collapse:collapse; margin-top:8px; font-size:14px; }
    th,td { text-align:left; border-bottom:1px solid var(--line); padding:11px 8px; vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    @media (max-width:860px) { header { display:block; } .actions { margin-top:16px; } .grid { grid-template-columns:1fr; } .wide { grid-column:auto; } }
  </style>
  <script>
    const savedTheme = localStorage.getItem("clearsight-theme") || "light";
    document.documentElement.dataset.theme = savedTheme;
    function toggleTheme() {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("clearsight-theme", next);
      document.querySelector(".toggle").textContent = next === "dark" ? "Light" : "Dark";
    }
    window.addEventListener("DOMContentLoaded", () => {
      document.querySelector(".toggle").textContent =
        document.documentElement.dataset.theme === "dark" ? "Light" : "Dark";
    });
  </script>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Clearsight Intent Dashboard</h1>
      <p>Pre-signature decode, simulation, risk flags, signed intent receipts, and audit envelopes over synthetic wallet requests.</p>
    </div>
    <div class="actions"><button class="toggle" onclick="toggleTheme()" type="button">Dark</button><div class="pill">Run {{ summary.run_id }}</div></div>
  </header>
  <section class="grid">
    <div class="panel metric"><span>Requests</span><strong>{{ summary.request_count }}</strong></div>
    <div class="panel metric"><span>Signature validity</span><strong>{{ "%.0f"|format(summary.signature_validity * 100) }}%</strong></div>
    <div class="panel metric"><span>Risky requests</span><strong>{{ summary.risky_request_count }}</strong></div>
    <div class="panel metric"><span>p95 latency</span><strong>{{ summary.p95_latency_ms }} ms</strong></div>
    <div class="panel wide">
      <h2>Method Mix</h2>
      {% for method, count in method_rows %}
      <div class="bar"><span>{{ method }}</span><div class="track"><div class="fill" style="width: {{ widths[method] }}%"></div></div><strong>{{ count }}</strong></div>
      {% endfor %}
    </div>
    <div class="panel wide">
      <h2>Safety Gates</h2>
      <table><tbody>
      {% for label, ok in gates.items() %}
        <tr><td>{{ label }}</td><td class="{{ 'ok' if ok else 'bad' }}">{{ "PASS" if ok else "FAIL" }}</td></tr>
      {% endfor %}
      </tbody></table>
    </div>
    <div class="panel full">
      <h2>Intent Receipts</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Request</th><th>Method</th><th>Summary</th><th>Policy</th><th>Risks</th></tr></thead>
          <tbody>
          {% for receipt in receipts %}
            <tr><td>{{ receipt.request_id }}</td><td>{{ receipt.method }}</td><td>{{ receipt.summary }}</td><td class="{{ 'ok' if receipt.policy_pass else 'bad' }}">{{ "pass" if receipt.policy_pass else "blocked" }}</td><td>{{ ", ".join(receipt.risk_flags) or "none" }}</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </section>
</main>
</body>
</html>
"""


def build_dashboard() -> Path:
    if not (outputs_dir() / "summary.json").exists():
        run_suite()
    summary = SuiteSummary.model_validate_json((outputs_dir() / "summary.json").read_text(encoding="utf-8"))
    receipts = json.loads((outputs_dir() / "receipts.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for receipt in receipts:
        counts[receipt["method"]] = counts.get(receipt["method"], 0) + 1
    max_count = max(counts.values()) if counts else 1
    widths = {method: round(count / max_count * 100, 2) for method, count in counts.items()}
    gates = {
        "Every receipt signature verifies": summary.signature_validity == 1.0,
        "Decode coverage is complete": summary.decode_coverage == 1.0,
        "Risky request detected": summary.risky_request_count > 0,
        "Policy block detected": summary.policy_block_count > 0,
        "Overall pass": summary.pass_gates,
    }
    env = Environment(autoescape=select_autoescape(enabled_extensions=("html", "xml")), trim_blocks=True, lstrip_blocks=True)
    path = project_root() / "outputs" / "dashboard.html"
    path.write_text(
        env.from_string(TEMPLATE).render(
            summary=summary,
            receipts=receipts,
            method_rows=sorted(counts.items()),
            widths=widths,
            gates=gates,
        ),
        encoding="utf-8",
    )
    return path
