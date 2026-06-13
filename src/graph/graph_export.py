import os
import json
import networkx as nx

def export_graph_to_cytoscape_json(G: nx.MultiDiGraph, path: str) -> None:
    """Export the NetworkX DiGraph to Cytoscape.js compatible JSON format."""
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    
    # Generate cytoscape-compatible structure
    data = nx.readwrite.json_graph.cytoscape_data(G)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def export_graph_to_gexf(G: nx.MultiDiGraph, path: str) -> None:
    """Export the NetworkX DiGraph to GEXF format (for Gephi, visualization debugging).
    
    Converts list-valued attributes (like authors) to comma-separated strings to avoid
    GEXF writer validation errors.
    """
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    
    # Copy graph to avoid modifying original graph data
    G_export = G.copy()
    
    # Convert list attributes to strings, and None values to empty strings
    for _, attrs in G_export.nodes(data=True):
        for key, val in list(attrs.items()):
            if val is None:
                attrs[key] = ""
            elif isinstance(val, list):
                attrs[key] = ", ".join(map(str, val))
                
    for _, _, attrs in G_export.edges(data=True):
        for key, val in list(attrs.items()):
            if val is None:
                attrs[key] = ""
            elif isinstance(val, list):
                attrs[key] = ", ".join(map(str, val))
                
    nx.write_gexf(G_export, path)
