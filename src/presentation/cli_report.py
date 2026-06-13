from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED, DOUBLE
from src.models.report import SynthesisReport
from src.models.contradiction import ContradictionPair

console = Console()

def format_claim_details(claim) -> Text:
    """Format claim details with colors for CLI panels."""
    text = Text()
    text.append("Claim: ", style="bold cyan")
    text.append(f"{claim.text}\n", style="white")
    
    authors_str = ", ".join(claim.authors) if claim.authors else "Unknown"
    text.append("Source: ", style="bold green")
    text.append(f"{authors_str} ({claim.year}) [PMID: {claim.paper_id}]\n", style="dim")
    
    text.append("Population: ", style="bold yellow")
    text.append(f"{claim.population}\n", style="yellow")
    
    text.append("Context: ", style="bold magenta")
    text.append(f"{claim.context}\n", style="magenta")
    
    text.append("Quote Anchor: ", style="bold blue")
    text.append(f'"{claim.quote_anchor}"', style="italic dim blue")
    return text

def print_cli_report(
    report: SynthesisReport,
    query: str,
    time_elapsed: float = 0.0,
    cost_estimate: float = 0.0,
):
    """Render a beautiful terminal report of the synthesis results using rich."""
    
    # 1. Header Title Panel
    title_text = Text()
    title_text.append("🔬 RESEARCH SYNTHESIS & CONTRADICTION ENGINE\n", style="bold magenta")
    title_text.append(f"Query: ", style="bold cyan")
    title_text.append(query, style="italic cyan")
    
    console.print(Panel(
        title_text,
        border_style="magenta",
        box=DOUBLE,
        padding=(1, 2)
    ))
    console.print()

    # 2. Stats Panel
    stats_table = Table(box=ROUNDED, border_style="cyan")
    stats_table.add_column("Ingested Papers", justify="center", style="bold green")
    stats_table.add_column("Extracted Claims", justify="center", style="bold green")
    stats_table.add_column("Detected Contradictions", justify="center", style="bold yellow")
    stats_table.add_column("Genuine Contradictions", justify="center", style="bold green")
    stats_table.add_column("Time Elapsed", justify="center", style="bold blue")
    stats_table.add_column("Estimated Cost", justify="center", style="bold red")

    genuine_count = sum(1 for c in report.contradictions if c.is_genuine)
    cost = cost_estimate if cost_estimate > 0 else report.metadata.get("cost_estimate", 0.0)
    duration = time_elapsed if time_elapsed > 0 else report.metadata.get("time_elapsed", 0.0)

    stats_table.add_row(
        str(report.total_papers),
        str(report.total_claims),
        str(len(report.contradictions)),
        str(genuine_count),
        f"{duration:.2f}s",
        f"${cost:.4f}"
    )
    console.print(Panel(stats_table, title="[bold cyan]Pipeline Execution Statistics[/bold cyan]", border_style="cyan"))
    console.print()

    # 3. Grounded Summary
    summary_text = report.summary if report.summary else "No grounded summary generated yet. (Phase 3 Synthesis)"
    console.print(Panel(
        summary_text,
        title="[bold green]Grounded Synthesis Narrative[/bold green]",
        border_style="green",
        box=ROUNDED,
        padding=(1, 1)
    ))
    console.print()

    # 4. Contradiction Summary Table
    if not report.contradictions:
        console.print("[yellow]No contradictions were found in the analyzed papers.[/yellow]")
        return

    table = Table(title="[bold yellow]Ranked Contradictions Overview[/bold yellow]", box=ROUNDED, border_style="yellow")
    table.add_column("#", justify="center", style="dim")
    table.add_column("Claim A", ratio=3, overflow="ellipsis")
    table.add_column("Claim B", ratio=3, overflow="ellipsis")
    table.add_column("Score", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Genuineness", justify="center")

    for i, c in enumerate(report.contradictions, 1):
        gen_text = "[green]Genuine[/green]" if c.is_genuine else "[yellow]Scope Mismatch[/yellow]"
        table.add_row(
            str(i),
            c.claim_a.text,
            c.claim_b.text,
            f"{c.contradiction_score:.2f}",
            c.contradiction_type.name,
            gen_text
        )
    console.print(table)
    console.print()

    # 5. Detailed Contradiction Displays (Side-by-Side)
    console.print("[bold cyan]=========================== Contradiction Drill-Down ===========================[/bold cyan]")
    console.print()
    
    for i, c in enumerate(report.contradictions[:5], 1):
        # Header for this contradiction
        gen_badge = "[bold green]GENUINE CONTRADICTION[/bold green]" if c.is_genuine else "[bold yellow]SCOPE MISMATCH / PSEUDO-CONTRADICTION[/bold yellow]"
        console.print(f"[bold cyan]Contradiction #{i}:[/bold cyan] {gen_badge} | Type: [magenta]{c.contradiction_type.name}[/magenta] | Score: [bold green]{c.contradiction_score:.2f}[/bold green]")
        console.print("-" * 100)

        # Format both claims
        claim_a_text = format_claim_details(c.claim_a)
        claim_b_text = format_claim_details(c.claim_b)

        # Put them in panels
        panel_a = Panel(claim_a_text, title=f"Claim A [dim]({c.claim_a.authors[0] if c.claim_a.authors else 'Unknown'}, {c.claim_a.year})[/dim]", border_style="cyan")
        panel_b = Panel(claim_b_text, title=f"Claim B [dim]({c.claim_b.authors[0] if c.claim_b.authors else 'Unknown'}, {c.claim_b.year})[/dim]", border_style="cyan")

        # Display side-by-side using an borderless table (works better than Columns on narrow screens)
        layout_table = Table.grid(expand=True)
        layout_table.add_column(ratio=1)
        layout_table.add_column(width=2)  # spacer
        layout_table.add_column(ratio=1)
        layout_table.add_row(panel_a, "", panel_b)

        console.print(layout_table)

        # Judge analysis explanation panel
        judge_explanation = Text()
        judge_explanation.append("Analysis: ", style="bold green")
        judge_explanation.append(f"{c.explanation}\n", style="white")
        if c.scope_note:
            judge_explanation.append("Scope Difference: ", style="bold yellow")
            judge_explanation.append(f"{c.scope_note}", style="white")

        console.print(Panel(
            judge_explanation,
            title="[bold green]LLM Judge Analysis[/bold green]",
            border_style="green",
            box=ROUNDED
        ))
        console.print()

    if len(report.contradictions) > 5:
        console.print(f"[dim]... and {len(report.contradictions) - 5} more contradictions. See exported JSON report for full details.[/dim]\n")

    # 6. Footer
    console.print(Panel(
        Text("Data sources: PubMed Central & NCBI E-utilities | Model: Gemini API & Sentence Transformers\n"
             "Local cross-encoder: cross-encoder/nli-deberta-v3-large", justify="center", style="dim"),
        border_style="magenta",
        box=ROUNDED
    ))
