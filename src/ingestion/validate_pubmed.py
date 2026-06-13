import asyncio
import json
import os
from src.ingestion.pubmed import ingest_papers
from src.config import settings

async def validate():
    queries = [
        "metformin cancer risk",
        "intermittent fasting insulin sensitivity",
        "SSRI depression adolescents"
    ]
    
    os.makedirs("data/sample_runs", exist_ok=True)
    
    for query in queries:
        print(f"Ingesting papers for query: '{query}'...")
        try:
            papers = await ingest_papers(query, max_results=settings.max_papers)
            print(f"Successfully fetched {len(papers)} papers.")
            
            # Validate results
            if len(papers) < 15:
                print(f"Warning: Expected at least 15 papers, got {len(papers)}")
            
            # Check a few papers for completeness
            for idx, paper in enumerate(papers[:3]):
                print(f"  Sample Paper {idx+1}:")
                print(f"    PMID: {paper.pmid}")
                print(f"    Title: {paper.title[:60]}...")
                print(f"    Authors: {', '.join(paper.authors[:3])}")
                print(f"    Year: {paper.year}")
                print(f"    Journal: {paper.journal}")
                print(f"    Abstract Length: {len(paper.abstract_text)} chars")
                print(f"    DOI: {paper.doi}")
            
            # Serialize and save
            filename = query.replace(" ", "_") + ".json"
            filepath = os.path.join("data/sample_runs", filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump([p.model_dump() for p in papers], f, indent=2)
            print(f"Saved results to {filepath}\n")
            
        except Exception as e:
            print(f"Validation failed for query '{query}': {e}\n")

if __name__ == "__main__":
    asyncio.run(validate())
