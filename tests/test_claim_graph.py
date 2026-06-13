import pytest
import uuid
import networkx as nx

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.models.paper import Paper
from src.models.contradiction import ContradictionPair, ContradictionType
from src.graph.claim_graph import build_claim_graph, compute_consensus_scores

@pytest.fixture
def sample_data():
    paper_1 = Paper(
        pmid="11111",
        title="Study 1 on Metformin",
        authors=["Author One"],
        year=2020,
        journal="Journal of Diabetes",
        abstract_text="Metformin reduces cancer risk."
    )
    paper_2 = Paper(
        pmid="22222",
        title="Study 2 on Metformin",
        authors=["Author Two"],
        year=2023,
        journal="Cancer Letters",
        abstract_text="Metformin increases cancer risk."
    )
    
    entity_metformin = Entity(text="Metformin", canonical_id="MeSH:D001241", entity_type=EntityType.DRUG)
    entity_cancer = Entity(text="Cancer", canonical_id="MeSH:D009369", entity_type=EntityType.DISEASE)
    
    claim_1 = Claim(
        id=uuid.uuid4(),
        text="Metformin reduces breast cancer risk.",
        paper_id="11111",
        authors=["Author One"],
        year=2020,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.NEGATIVE,
        entities=[entity_metformin, entity_cancer],
        population="humans",
        context="general",
        quote_anchor="reduces risk",
        study_design=StudyDesign.RCT
    )
    
    claim_2 = Claim(
        id=uuid.uuid4(),
        text="Metformin increases breast cancer risk.",
        paper_id="22222",
        authors=["Author Two"],
        year=2023,
        confidence_score=1.0,
        claim_type=ClaimType.CAUSAL,
        polarity=Polarity.POSITIVE,
        entities=[entity_metformin, entity_cancer],
        population="humans",
        context="general",
        quote_anchor="increases risk",
        study_design=StudyDesign.RCT
    )

    contradiction = ContradictionPair(
        claim_a=claim_1,
        claim_b=claim_2,
        contradiction_score=0.95,
        contradiction_type=ContradictionType.DIRECTION_REVERSAL,
        explanation="Claim 1 reduces risk, Claim 2 increases risk.",
        scope_note="",
        is_genuine=True
    )
    
    return [claim_1, claim_2], [contradiction], [paper_1, paper_2]

def test_build_claim_graph(sample_data):
    claims, contradictions, papers = sample_data
    G = build_claim_graph(claims, contradictions, papers)
    
    # Assert nodes and attributes
    assert G.number_of_nodes() == 6 # 2 papers + 2 claims + 2 entities
    
    # Check paper node
    assert G.has_node("11111")
    assert G.nodes["11111"]["type"] == "paper"
    assert G.nodes["11111"]["title"] == "Study 1 on Metformin"
    
    # Check claim node
    claim_1_id = str(claims[0].id)
    assert G.has_node(claim_1_id)
    assert G.nodes[claim_1_id]["type"] == "claim"
    assert G.nodes[claim_1_id]["polarity"] == Polarity.NEGATIVE.value
    
    # Check entity node
    assert G.has_node("MeSH:D001241") # Metformin canonical ID
    assert G.nodes["MeSH:D001241"]["type"] == "entity"
    assert G.nodes["MeSH:D001241"]["entity_type"] == EntityType.DRUG.value

    # Check edges
    # Paper -> Claim (EXTRACTED_FROM)
    assert G.has_edge("11111", claim_1_id)
    assert list(G["11111"][claim_1_id].values())[0]["type"] == "EXTRACTED_FROM"
    
    # Claim -> Entity (MENTIONS)
    assert G.has_edge(claim_1_id, "MeSH:D001241")
    assert list(G[claim_1_id]["MeSH:D001241"].values())[0]["type"] == "MENTIONS"
    
    # Claim <-> Claim (CONTRADICTS / SUPERSEDES)
    claim_2_id = str(claims[1].id)
    assert G.has_edge(claim_1_id, claim_2_id)
    
    # Find edges from claim_1 to claim_2
    edges_1_2 = G[claim_1_id][claim_2_id]
    assert len(edges_1_2) == 1
    edge_1_2_data = list(edges_1_2.values())[0]
    assert edge_1_2_data["type"] == "CONTRADICTS"
    assert edge_1_2_data["score"] == 0.95
    
    # Find edges from claim_2 to claim_1 (should have both CONTRADICTS and SUPERSEDES)
    assert G.has_edge(claim_2_id, claim_1_id)
    edges_2_1 = G[claim_2_id][claim_1_id]
    assert len(edges_2_1) == 2
    
    contradicts_edge = next(e for e in edges_2_1.values() if e["type"] == "CONTRADICTS")
    supersedes_edge = next(e for e in edges_2_1.values() if e["type"] == "SUPERSEDES")
    
    assert contradicts_edge["score"] == 0.95
    
    # Claim 2 (2023) SUPERSEDES Claim 1 (2020) because 2023 > 2020
    assert supersedes_edge["score"] == 0.95
    assert supersedes_edge["explanation"] == "Claim 1 reduces risk, Claim 2 increases risk."
    assert supersedes_edge["scope_note"] == ""
    assert supersedes_edge["is_genuine"] is True

def test_compute_consensus_scores(sample_data):
    claims, contradictions, papers = sample_data
    G = build_claim_graph(claims, contradictions, papers)
    
    scores = compute_consensus_scores(G)
    
    claim_1_id = str(claims[0].id)
    claim_2_id = str(claims[1].id)
    
    # Each claim is contradicted by the other, and there are no supporting claims.
    # S = 0, C = 1 -> Score = 0.0
    assert scores[claim_1_id] == 0.0
    assert scores[claim_2_id] == 0.0
