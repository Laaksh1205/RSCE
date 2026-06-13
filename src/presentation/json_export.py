import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models.report import SynthesisReport

def generate_query_slug(query: str) -> str:
    """Generate a clean URL-friendly/file-friendly slug from the query."""
    # Remove non-alphanumeric characters (except spaces)
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", query)
    # Convert spaces/hyphens to single underscores, convert to lowercase
    clean = clean.strip().lower()
    slug = re.sub(r"[\s-]+", "_", clean)
    # Truncate to a reasonable length
    return slug[:50]

def export_report_to_json(
    report: SynthesisReport,
    query: str,
    output_dir: Optional[str] = None
) -> str:
    """Export the SynthesisReport to a structured JSON file.
    
    Saves to: {output_dir}/{query_slug}_{timestamp}.json.
    Returns: The absolute string path of the written file.
    """
    slug = generate_query_slug(query)
    if not slug:
        slug = "synthesis_report"
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_{timestamp}.json"
    
    if output_dir is None:
        # Resolve path relative to project root
        project_root = Path(__file__).resolve().parents[2]
        output_path = project_root / "data" / "sample_runs" / filename
    else:
        output_path = Path(output_dir) / filename
        
    # Ensure directory exists
    os.makedirs(output_path.parent, exist_ok=True)
    
    # Serialize Pydantic v2 model to JSON
    json_data = report.model_dump_json(indent=2)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_data)
        
    return str(output_path.resolve())
