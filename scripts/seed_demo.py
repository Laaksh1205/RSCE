import os
import sys
import json
import sqlite3

# Add P1 to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings
from src.storage.database import init_db, get_connection

def seed_demo_data(db_path: str = None) -> None:
    if db_path is None:
        db_path = settings.db_path
        
    print(f"Initializing database at: {db_path}")
    init_db(db_path)
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    seed_file = os.path.join(base_dir, "data", "demo_seed.json")
    
    if not os.path.exists(seed_file):
        print(f"Error: Seed file not found at {seed_file}")
        sys.exit(1)
        
    print(f"Loading seed data from: {seed_file}")
    with open(seed_file, "r", encoding="utf-8") as f:
        seed_data = json.load(f)
        
    conn = get_connection(db_path)
    
    with conn:
        # Seed papers
        print(f"Seeding {len(seed_data['papers'])} papers...")
        for p in seed_data['papers']:
            conn.execute("""
                INSERT OR REPLACE INTO papers (
                    pmid, title, authors, year, journal, abstract_text, full_text, doi
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p['pmid'], p['title'], p['authors'], p['year'], p['journal'],
                p['abstract_text'], p['full_text'], p['doi']
            ))
            
        # Seed claims
        print(f"Seeding {len(seed_data['claims'])} claims...")
        for c in seed_data['claims']:
            conn.execute("""
                INSERT OR REPLACE INTO claims (
                    id, paper_id, text, normalized_text, polarity, population, context,
                    section, quote_anchor, claim_type, study_design, confidence_score,
                    is_primary_finding, sample_size, entities
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c['id'], c['paper_id'], c['text'], c['normalized_text'], c['polarity'],
                c['population'], c['context'], c['section'], c['quote_anchor'],
                c['claim_type'], c['study_design'], c['confidence_score'],
                c['is_primary_finding'], c['sample_size'], c['entities']
            ))
            
        # Seed contradictions
        print(f"Seeding {len(seed_data['contradictions'])} contradictions...")
        for c in seed_data['contradictions']:
            conn.execute("""
                INSERT OR REPLACE INTO contradictions (
                    id, claim_a_id, claim_b_id, contradiction_score, contradiction_type,
                    explanation, scope_note, temporal_resolution, is_genuine
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c['id'], c['claim_a_id'], c['claim_b_id'], c['contradiction_score'],
                c['contradiction_type'], c['explanation'], c['scope_note'],
                c['temporal_resolution'], c['is_genuine']
            ))
            
        # Seed pipeline runs
        print(f"Seeding {len(seed_data['pipeline_runs'])} pipeline runs...")
        for r in seed_data['pipeline_runs']:
            conn.execute("""
                INSERT OR REPLACE INTO pipeline_runs (
                    id, query, status, papers_fetched, claims_extracted, contradictions_found,
                    started_at, completed_at, error_message, pmids, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['id'], r['query'], r['status'], r['papers_fetched'],
                r['claims_extracted'], r['contradictions_found'],
                r['started_at'], r['completed_at'], r['error_message'],
                r['pmids'], r['report_json']
            ))
            
    conn.close()
    print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_demo_data()
