import os
import json
import uuid
import tempfile
import pytest
import networkx as nx

from src.models.claim import Claim, ClaimType, Polarity, StudyDesign, Entity, EntityType
from src.models.paper import Paper
from src.models.contradiction import ContradictionPair, ContradictionType
from src.graph.claim_graph import build_claim_graph
from src.graph.graph_export import export_graph_to_cytoscape_json, export_graph_to_gexf


@pytest.fixture
def sample_data():
    paper_1 = Paper(
        pmid="11111",
        title="Study 1 on Metformin",
        authors=["Author One", "Co-Author One"],
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
        authors=["Author One", "Co-Author One"],
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


def test_export_graph_to_cytoscape_json(sample_data):
    claims, contradictions, papers = sample_data
    G = build_claim_graph(claims, contradictions, papers)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "graph.json")
        export_graph_to_cytoscape_json(G, json_path)
        
        assert os.path.exists(json_path)
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Cytoscape format should contain 'elements'
        assert "elements" in data
        elements = data["elements"]
        assert "nodes" in elements
        assert "edges" in elements
        
        # Verify node counts (2 papers + 2 claims + 2 entities = 6 nodes)
        nodes = elements["nodes"]
        assert len(nodes) == 6
        
        # Verify node properties
        node_ids = {n["data"]["id"] for n in nodes}
        assert "11111" in node_ids
        
        paper_node = next(n for n in nodes if n["data"]["id"] == "11111")
        assert paper_node["data"]["type"] == "paper"
        assert paper_node["data"]["title"] == "Study 1 on Metformin"
        assert paper_node["data"]["authors"] == ["Author One", "Co-Author One"]
        
        claim_node = next(n for n in nodes if n["data"]["id"] == str(claims[0].id))
        assert claim_node["data"]["type"] == "claim"
        assert claim_node["data"]["polarity"] == Polarity.NEGATIVE.value


def test_export_graph_to_gexf(sample_data):
    claims, contradictions, papers = sample_data
    G = build_claim_graph(claims, contradictions, papers)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        gexf_path = os.path.join(tmpdir, "graph.gexf")
        export_graph_to_gexf(G, gexf_path)
        
        assert os.path.exists(gexf_path)
        
        # Check that the file parses correctly back using networkx GEXF reader
        G_imported = nx.read_gexf(gexf_path)
        
        assert G_imported.number_of_nodes() == 6
        
        # Check that the paper's authors (originally a list) have been converted to a comma-separated string
        paper_data = G_imported.nodes["11111"]
        assert paper_data["type"] == "paper"
        assert paper_data["authors"] == "Author One, Co-Author One"
