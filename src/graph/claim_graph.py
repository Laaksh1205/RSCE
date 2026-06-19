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
                "temporal_resolution": pair.temporal_resolution,
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
    
    # 1. Extract all claim nodes and cache their attributes in O(V)
    claims = []
    claim_attrs = {}
    for node, attrs in graph.nodes(data=True):
        if attrs.get("type") == "claim":
            claims.append(node)
            claim_attrs[node] = attrs
            
    # 2. Pre-compute contradicting pairs, claim_to_entities, and entity_to_claims in a single pass O(E)
    contradicting_pairs = set()
    claim_to_entities = {}
    entity_to_claims = {}
    
    for u, v, edge_attrs in graph.edges(data=True):
        e_type = edge_attrs.get("type")
        if e_type in ("CONTRADICTS", "SUPERSEDES"):
            contradicting_pairs.add((u, v))
            contradicting_pairs.add((v, u))
        elif e_type == "MENTIONS":
            # u is claim, v is entity
            if u not in claim_to_entities:
                claim_to_entities[u] = set()
            claim_to_entities[u].add(v)
            
            if v not in entity_to_claims:
                entity_to_claims[v] = set()
            entity_to_claims[v].add(u)
            
    # 3. Compute consensus scores
    for claim_node in claims:
        # Get entities mentioned by this claim
        claim_entities = claim_to_entities.get(claim_node, set())
        
        if not claim_entities:
            # If no entities are linked, score defaults to 1.0
            consensus_scores[claim_node] = 1.0
            continue
            
        # Find all other claims that share at least one entity
        related_claims = set()
        for entity in claim_entities:
            for u_claim in entity_to_claims.get(entity, set()):
                if u_claim != claim_node:
                    related_claims.add(u_claim)
                    
        if not related_claims:
            consensus_scores[claim_node] = 1.0
            continue
            
        s_count = 0
        c_count = 0
        
        curr_attrs = claim_attrs[claim_node]
        claim_polarity = curr_attrs.get("polarity")
        claim_type = curr_attrs.get("claim_type")
        claim_population = curr_attrs.get("population")
        
        for related in related_claims:
            # Fast O(1) set lookup
            if (claim_node, related) in contradicting_pairs:
                c_count += 1
            else:
                rel_attrs = claim_attrs[related]
                related_polarity = rel_attrs.get("polarity")
                if related_polarity == claim_polarity:
                    same_claim_type = rel_attrs.get("claim_type") == claim_type
                    same_population = (
                        bool(claim_population)
                        and bool(rel_attrs.get("population"))
                        and claim_population.strip().lower() == rel_attrs.get("population").strip().lower()
                    )
                    if same_claim_type or same_population:
                        s_count += 1
                    
        total = s_count + c_count
        if total > 0:
            consensus_scores[claim_node] = float(s_count / total)
        else:
            consensus_scores[claim_node] = 1.0
            
    return consensus_scores
