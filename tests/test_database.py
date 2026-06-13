import os
import pytest
import uuid
import tempfile
from src.models.paper import Paper
from src.models.claim import Claim, Entity, ClaimType, Polarity, StudyDesign, EntityType
from src.models.contradiction import ContradictionPair, ContradictionType
from src.storage.database import init_db, save_papers, save_claims, save_contradictions, get_paper, get_claim, get_claims_for_run, get_contradictions_for_run

@pytest.fixture
def temp_db():
    # Create a temporary SQLite database file path
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Initialize the database
    init_db(db_path=path)
    
    yield path
    
    # Cleanup after test
    if os.path.exists(path):
        os.remove(path)

def test_paper_round_trip(temp_db):
    original_paper = Paper(
        pmid="12345",
        title="Impact of Metformin on Cancer Cells",
        authors=["John Smith", "Jane Doe"],
        year=2024,
        journal="Journal of Medicine",
        abstract_text="Metformin reduces breast cancer risk.",
        doi="10.1234/med.2024.1"
    )
    
    save_papers([original_paper], db_path=temp_db)
    
    retrieved_paper = get_paper("12345", db_path=temp_db)
    assert retrieved_paper is not None
    assert retrieved_paper.pmid == original_paper.pmid
    assert retrieved_paper.title == original_paper.title
    assert retrieved_paper.authors == original_paper.authors
    assert retrieved_paper.year == original_paper.year
    assert retrieved_paper.journal == original_paper.journal
    assert retrieved_paper.abstract_text == original_paper.abstract_text
    assert retrieved_paper.doi == original_paper.doi

def test_claim_round_trip(temp_db):
    paper = Paper(
        pmid="98765",
        title="Study on Metformin",
        authors=["Dr. Who"],
        year=2023,
        journal="Journal of Time",
        abstract_text="Metformin does things.",
        doi="10.1000/time.1"
    )
    save_papers([paper], db_path=temp_db)
    
    claim_id = uuid.uuid4()
    claim = Claim(
        id=claim_id,
        text="Metformin reduces cell growth.",
        normalized_text="metformin reduces cell growth",
        paper_id="98765",
        section="Abstract",
        authors=["Dr. Who"],
        year=2023,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        entities=[Entity(text="metformin", entity_type=EntityType.DRUG)],
        population="in vitro HeLa cells",
        context="10mM for 24h",
        quote_anchor="Metformin reduces cell growth",
        study_design=StudyDesign.IN_VITRO,
        is_primary_finding=True
    )
    
    save_claims([claim], db_path=temp_db)
    
    retrieved_claim = get_claim(str(claim_id), db_path=temp_db)
    assert retrieved_claim is not None
    assert retrieved_claim.id == claim.id
    assert retrieved_claim.text == claim.text
    assert retrieved_claim.normalized_text == claim.normalized_text
    assert retrieved_claim.paper_id == claim.paper_id
    assert retrieved_claim.confidence_score == claim.confidence_score
    assert retrieved_claim.claim_type == claim.claim_type
    assert retrieved_claim.polarity == claim.polarity
    assert len(retrieved_claim.entities) == 1
    assert retrieved_claim.entities[0].text == "metformin"
    assert retrieved_claim.entities[0].entity_type == EntityType.DRUG
    
    # Test batch retrieval
    claims = get_claims_for_run(["98765"], db_path=temp_db)
    assert len(claims) == 1
    assert claims[0].id == claim.id

def test_contradiction_saving(temp_db):
    paper = Paper(
        pmid="55555",
        title="Double Study",
        authors=["Author A"],
        year=2022,
        journal="Double Journal",
        abstract_text="Abstract content.",
        doi="10.1000/double"
    )
    save_papers([paper], db_path=temp_db)
    
    claim_a = Claim(
        id=uuid.uuid4(),
        text="Drug A is good.",
        normalized_text="drug a is good",
        paper_id="55555",
        year=2022,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        population="humans",
        context="none",
        quote_anchor="Drug A is good.",
        study_design=StudyDesign.RCT,
    )
    claim_b = Claim(
        id=uuid.uuid4(),
        text="Drug A is bad.",
        normalized_text="drug a is bad",
        paper_id="55555",
        year=2022,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        population="humans",
        context="none",
        quote_anchor="Drug A is bad.",
        study_design=StudyDesign.RCT,
    )
    save_claims([claim_a, claim_b], db_path=temp_db)
    
    pair = ContradictionPair(
        claim_a=claim_a,
        claim_b=claim_b,
        contradiction_score=0.9,
        contradiction_type=ContradictionType.DIRECT_NEGATION,
        explanation="Opposite efficacy statements",
        scope_note="Same population",
        is_genuine=True
    )
    
    assigned_ids = save_contradictions([pair], db_path=temp_db)
    assert len(assigned_ids) == 1
    assert isinstance(assigned_ids[0], str)
    
    # Test retrieving contradictions
    retrieved_pairs = get_contradictions_for_run(["55555"], db_path=temp_db)
    assert len(retrieved_pairs) == 1
    assert retrieved_pairs[0].contradiction_score == 0.9
    assert retrieved_pairs[0].claim_a.id == claim_a.id
    assert retrieved_pairs[0].claim_b.id == claim_b.id


def test_package_exports():
    import src.storage as storage
    import src.storage.database as db
    
    assert storage.get_connection is db.get_connection
    assert storage.init_db is db.init_db
    assert storage.save_papers is db.save_papers
    assert storage.save_claims is db.save_claims
    assert storage.save_contradictions is db.save_contradictions
    assert storage.save_pipeline_run is db.save_pipeline_run
    assert storage.get_pipeline_run is db.get_pipeline_run
    assert storage.get_paper is db.get_paper
    assert storage.get_claim is db.get_claim
    assert storage.get_contradictions_for_run is db.get_contradictions_for_run
    assert storage.get_claims_for_run is db.get_claims_for_run
    assert storage.get_papers_for_run is db.get_papers_for_run


def test_save_pipeline_run_preserves_started_at(temp_db):
    from src.storage.database import save_pipeline_run, get_pipeline_run
    
    run_id = "test_run_123"
    query = "metformin cancer"
    started_at = "2026-06-12T12:00:00Z"
    
    # 1. Start the run
    save_pipeline_run(
        run_id=run_id,
        query=query,
        status="RUNNING",
        started_at=started_at,
        db_path=temp_db
    )
    
    run = get_pipeline_run(run_id, db_path=temp_db)
    assert run is not None
    assert run["status"] == "RUNNING"
    assert run["started_at"] == started_at
    
    # 2. Update the run (e.g. intermediate save without started_at)
    save_pipeline_run(
        run_id=run_id,
        query=query,
        status="COMPLETED",
        completed_at="2026-06-12T12:05:00Z",
        db_path=temp_db
    )
    
    run = get_pipeline_run(run_id, db_path=temp_db)
    assert run is not None
    assert run["status"] == "COMPLETED"
    assert run["started_at"] == started_at  # Should be preserved!
    assert run["completed_at"] == "2026-06-12T12:05:00Z"


def test_seed_demo_script(temp_db):
    from scripts.seed_demo import seed_demo_data
    from src.storage.database import get_pipeline_run
    
    # Run the seeding script targeting our temp database
    seed_demo_data(db_path=temp_db)
    
    # Verify the demo runs exist in the database
    run_metformin = get_pipeline_run("demo_metformin", db_path=temp_db)
    assert run_metformin is not None
    assert run_metformin["status"] == "COMPLETED"
    assert run_metformin["query"] == "Does metformin reduce cancer risk?"
    
    run_fasting = get_pipeline_run("demo_fasting", db_path=temp_db)
    assert run_fasting is not None
    
    run_ssri = get_pipeline_run("demo_ssri", db_path=temp_db)
    assert run_ssri is not None



