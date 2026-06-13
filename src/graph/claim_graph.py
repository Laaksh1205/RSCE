import networkx as nx
from src.models.claim import Claim
from src.models.paper import Paper
from src.models.contradiction import ContradictionPair

def build_claim_graph(
    claims: list[Claim],
    contradictions: list[ContradictionPair],
    papers: list[Paper],
) -> nx.MultiDiGraph:
    """Build a directed claim-evidence graph using NetworkX.
    
    Nodes:
      - Paper: Represented by paper_id (PMID), attributes: title, authors, year, journal, type="paper"
      - Claim: Represented by claim_id (UUID string), attributes: text, polarity, confidence_score, type="claim"
      - Entity: Represented by entity_id (canonical_id or text), attributes: text, entity_type, type="entity"
      
    Edges:
      - EXTRACTED_FROM: paper -> claim
      - CONTRADICTS: claim <-> claim (added bidirectionally)
      - MENTIONS: claim -> entity
      - SUPERSEDES: newer claim -> older claim (based on year of contradiction pairs)
    """
    G = nx.MultiDiGraph()
    
    # 1. Add Paper Nodes
    for paper in papers:
        G.add_node(
            paper.pmid,
            type="paper",
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            journal=paper.journal or "",
            doi=paper.doi or ""
        )
        
    # 2. Add Claim Nodes and EXTRACTED_FROM edges
    for claim in claims:
        claim_id_str = str(claim.id)
        G.add_node(
            claim_id_str,
            type="claim",
            text=claim.text,
            polarity=claim.polarity.value,
            confidence_score=claim.confidence_score,
            claim_type=claim.claim_type.value,
            study_design=claim.study_design.value,
            population=claim.population,
            context=claim.context
        )
        
        # Link Paper -> Claim if Paper exists in graph
        if claim.paper_id in G:
            G.add_edge(claim.paper_id, claim_id_str, type="EXTRACTED_FROM")
            
        # Add Entity nodes and MENTIONS edges
        for entity in claim.entities:
            entity_id = entity.canonical_id if entity.canonical_id else entity.text
            if not G.has_node(entity_id):
                G.add_node(
                    entity_id,
                    type="entity",
                    text=entity.text,
                    canonical_id=entity.canonical_id,
                    entity_type=entity.entity_type.value
                )
            G.add_edge(claim_id_str, entity_id, type="MENTIONS")

    # 3. Add CONTRADICTS and SUPERSEDES edges from contradiction pairs
    for pair in contradictions:
        claim_a_id = str(pair.claim_a.id)
        claim_b_id = str(pair.claim_b.id)
        
        # Ensure claim nodes exist in the graph before linking
        if claim_a_id in G and claim_b_id in G:
            # Add bidirectional CONTRADICTS edges
            edge_attrs = {
                "type": "CONTRADICTS",
                "score": pair.contradiction_score,
                "explanation": pair.explanation,
                "scope_note": pair.scope_note,
                "is_genuine": pair.is_genuine
            }
            G.add_edge(claim_a_id, claim_b_id, **edge_attrs)
            G.add_edge(claim_b_id, claim_a_id, **edge_attrs)
            
            # Add SUPERSEDES edge from newer claim to older claim if years differ
            if pair.claim_a.year > pair.claim_b.year:
                supersedes_attrs = {**edge_attrs, "type": "SUPERSEDES"}
                G.add_edge(claim_a_id, claim_b_id, **supersedes_attrs)
            elif pair.claim_b.year > pair.claim_a.year:
                supersedes_attrs = {**edge_attrs, "type": "SUPERSEDES"}
                G.add_edge(claim_b_id, claim_a_id, **supersedes_attrs)
                
    return G

def compute_consensus_scores(graph: nx.MultiDiGraph) -> dict[str, float]:
    """Compute consensus score for each claim in the graph.
    
    Score = S / (S + C) where:
      - S = number of claims sharing at least one entity and having the same polarity (supporting)
      - C = number of claims connected via CONTRADICTS edges (contradicting)
      
    Returns: dict mapping claim_id (string) to consensus score (float between 0.0 and 1.0)
    """
    consensus_scores = {}
    
    # Extract all claim nodes
    claims = [node for node, attrs in graph.nodes(data=True) if attrs.get("type") == "claim"]
    
    # Pre-compute all contradicting and superseding claim pairs in O(E_graph)
    contradicting_pairs = set()
    for u, v, edge_attrs in graph.edges(data=True):
        if edge_attrs.get("type") in ("CONTRADICTS", "SUPERSEDES"):
            contradicting_pairs.add((u, v))
            contradicting_pairs.add((v, u))
            
    for claim_node in claims:
        # Get entities mentioned by this claim
        claim_entities = {
            target for _, target, edge_attrs in graph.out_edges(claim_node, data=True)
            if edge_attrs.get("type") == "MENTIONS"
        }
        
        if not claim_entities:
            # If no entities are linked, score defaults to 1.0
            consensus_scores[claim_node] = 1.0
            continue
            
        # Find all other claims that share at least one entity
        related_claims = set()
        for entity in claim_entities:
            # Predecessors of an entity node via MENTIONS edges are claims
            for predecessor in graph.predecessors(entity):
                if predecessor != claim_node and graph.nodes[predecessor].get("type") == "claim":
                    related_claims.add(predecessor)
                    
        if not related_claims:
            consensus_scores[claim_node] = 1.0
            continue
            
        # Calculate Supporting (S) and Contradicting (C) claims
        s_count = 0
        c_count = 0
        
        claim_polarity = graph.nodes[claim_node].get("polarity")
        
        for related in related_claims:
            # Fast O(1) set lookup instead of O(E_uv) multi-edge scan
            if (claim_node, related) in contradicting_pairs:
                c_count += 1
            else:
                # If they have the same polarity, count as supporting
                related_polarity = graph.nodes[related].get("polarity")
                if related_polarity == claim_polarity:
                    s_count += 1
                    
        total = s_count + c_count
        if total > 0:
            consensus_scores[claim_node] = float(s_count / total)
        else:
            consensus_scores[claim_node] = 1.0
            
    return consensus_scores
