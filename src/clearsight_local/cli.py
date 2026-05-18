from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from clearsight_local.dashboard import build_dashboard
from clearsight_local.engine import explain_request
from clearsight_local.fixtures import load_fixtures
from clearsight_local.runner import benchmark, export_demo_pack, init_demo, run_suite, verify_outputs


app = typer.Typer(help="Offline pre-signature intent receipt simulator.")
console = Console()


@app.command("init-demo")
def init_demo_command(force: bool = typer.Option(False, "--force")) -> None:
    init_demo(force=force)
    console.print("[green]Initialized synthetic intent receipt store.[/green]")


@app.command("explain")
def explain_command(request_id: str) -> None:
    console.print_json(explain_request(request_id).model_dump_json(indent=2))


@app.command("run-suite")
def run_suite_command(iterations: int = typer.Option(1, "--iterations", min=1)) -> None:
    summary = run_suite(iterations=iterations)
    console.print_json(summary.model_dump_json(indent=2))
    if not summary.pass_gates:
        raise typer.Exit(1)


@app.command("verify")
def verify_command() -> None:
    ok, checks = verify_outputs()
    table = Table(title="Verification")
    table.add_column("Gate")
    table.add_column("Status")
    for gate, status in checks.items():
        table.add_row(gate, "PASS" if status else "FAIL")
    console.print(table)
    if not ok:
        raise typer.Exit(1)


@app.command("dashboard")
def dashboard_command() -> None:
    path = build_dashboard()
    console.print(f"[green]Dashboard written:[/green] {path}")


@app.command("benchmark")
def benchmark_command(iterations: int = typer.Option(100, "--iterations", min=1)) -> None:
    summary = benchmark(iterations=iterations)
    table = Table(title="Benchmark")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("receipts", str(summary.receipt_count))
    table.add_row("signature validity", f"{summary.signature_validity:.0%}")
    table.add_row("decode coverage", f"{summary.decode_coverage:.0%}")
    table.add_row("policy blocks", str(summary.policy_block_count))
    table.add_row("p95 latency", f"{summary.p95_latency_ms} ms")
    table.add_row("pass gates", str(summary.pass_gates))
    console.print(table)
    if not summary.pass_gates:
        raise typer.Exit(1)


@app.command("export-demo-pack")
def export_demo_pack_command() -> None:
    path = export_demo_pack()
    console.print(f"[green]Demo pack exported:[/green] {path}")


@app.command("tool-loop")
def tool_loop_command() -> None:
    data = load_fixtures()
    for line in sys.stdin:
        if not line.strip():
            continue
        payload = json.loads(line)
        tool = str(payload["tool"])
        args = dict(payload.get("arguments", {}))
        if tool == "explain":
            print(explain_request(str(args["request_id"]), fixtures=data).model_dump_json())
        else:
            raise typer.BadParameter(f"unknown tool: {tool}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

