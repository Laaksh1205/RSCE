import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
import typer
from rich.console import Console

from src.config import settings
from src.pipeline import run_full_pipeline
from src.presentation import print_cli_report, export_report_to_json


# Configure logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

app = typer.Typer(help="Research Synthesis & Contradiction Engine (RSCE) CLI")
console = Console()

async def run_pipeline(query: str, max_papers: int, output_json: bool):
    """Orchestrate the end-to-end pipeline stages:
    Ingestion & Extraction -> Contradiction Detection -> CLI/JSON Presentation
    """
    if not settings.gemini_api_key and not settings.openai_api_key:
        console.print(
            "[bold red]Error:[/bold red] No LLM API keys configured. "
            "Please set GEMINI_API_KEY or OPENAI_API_KEY in your .env file.",
            style="red"
        )
        sys.exit(1)

    # 1. Run full pipeline
    with console.status(f"[bold green]Running end-to-end research synthesis pipeline for: '{query}'...[/bold green]") as status:
        try:
            state = await run_full_pipeline(query, max_papers=max_papers)
        except Exception as e:
            console.print(f"[bold red]Pipeline execution failed: {e}[/bold red]")
            sys.exit(1)

    if not state.papers:
        console.print("[yellow]No papers were found for the given query. Exiting.[/yellow]")
        return

    # 2. Print Rich Terminal Report
    if state.report:
        time_elapsed = state.report.metadata.get("time_elapsed", 0.0)
        cost_estimate = state.report.metadata.get("cost_estimate", 0.0)
        print_cli_report(
            report=state.report,
            query=query,
            time_elapsed=time_elapsed,
            cost_estimate=cost_estimate
        )
    else:
        console.print("[bold red]Error: No report was generated.[/bold red]")
        sys.exit(1)

    # 3. Optional JSON Export & Graph Export (Phase 3)
    if output_json:
        try:
            saved_path = export_report_to_json(state.report, query)
            console.print(f"\n[green]✔ Full synthesis report exported to:[/green] [bold cyan]{saved_path}[/bold cyan]")
            
            # Export graph as well
            from src.graph.claim_graph import build_claim_graph
            from src.graph.graph_export import export_graph_to_cytoscape_json, export_graph_to_gexf
            from src.presentation.json_export import generate_query_slug
            
            G = build_claim_graph(state.claims, state.contradictions, state.papers)
            slug = generate_query_slug(query) or "claim_graph"
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[1]
            
            json_graph_path = project_root / "data" / "sample_runs" / f"{slug}_graph.json"
            gexf_graph_path = project_root / "data" / "sample_runs" / f"{slug}_graph.gexf"
            
            export_graph_to_cytoscape_json(G, str(json_graph_path))
            export_graph_to_gexf(G, str(gexf_graph_path))
            
            console.print(f"[green]✔ Claim-evidence graph exported to:[/green] [bold cyan]{json_graph_path}[/bold cyan] and [bold cyan]{gexf_graph_path}[/bold cyan]\n")
        except Exception as e:
            console.print(f"[red]Failed to export JSON report/graph: {e}[/red]")


@app.command()
def analyze(
    query: str = typer.Argument(..., help="Research question to analyze"),
    max_papers: int = typer.Option(settings.max_papers, "--max-papers", "-n", help="Maximum papers to fetch"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Export report output to a structured JSON file"),
):
    """Analyze a research question for contradictory claims across papers."""
    asyncio.run(run_pipeline(query, max_papers, output_json))

if __name__ == "__main__":
    app()
