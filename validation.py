from typing import List, Dict, Optional, Tuple
from data_models import DesignState, DesignNode, SingleProposal
import uuid

def validate_dsg(dsg: DesignState) -> Tuple[bool, str]:
    """
    Validates a DesignState Graph for structural integrity.
    Returns (is_valid, error_message)
    """
    # Check if nodes exist
    if not dsg.nodes:
        return False, "DSG has no nodes"
    
    # Check if edges are properly formatted
    for edge in dsg.edges:
        if not isinstance(edge, list) or len(edge) != 2:
            return False, f"Invalid edge format: {edge}. Edges must be [source_id, target_id]"
        
        source_id, target_id = edge
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            return False, f"Edge IDs must be strings: {edge}"
            
        if source_id not in dsg.nodes:
            return False, f"Edge source node {source_id} not found in nodes"
        if target_id not in dsg.nodes:
            return False, f"Edge target node {target_id} not found in nodes"
    
    # Check for orphaned nodes (nodes with no edges)
    node_ids = set(dsg.nodes.keys())
    connected_nodes = set()
    for edge in dsg.edges:
        connected_nodes.add(edge[0])
        connected_nodes.add(edge[1])
    
    orphaned = node_ids - connected_nodes
    if orphaned:
        return False, f"Found orphaned nodes: {orphaned}"
    
    # Check for duplicate edges
    edge_set = set(tuple(edge) for edge in dsg.edges)
    if len(edge_set) != len(dsg.edges):
        return False, "Found duplicate edges in the graph"
    
    # Check for self-loops
    for edge in dsg.edges:
        if edge[0] == edge[1]:
            return False, f"Found self-loop at node {edge[0]}"
    
    return True, ""

def sanitize_dsg(dsg: DesignState) -> Optional[DesignState]:
    """
    Attempts to fix common issues in a DSG.
    Returns None if the DSG cannot be salvaged.
    """
    try:
        # Create a new DSG to store sanitized data
        sanitized = DesignState(nodes={}, edges=[])
        
        # 1. Fix node IDs and ensure they're unique
        node_id_map = {}  # old_id -> new_id
        for old_id, node in dsg.nodes.items():
            if not isinstance(node, DesignNode):
                continue
            if not node.node_id or not isinstance(node.node_id, str):
                node.node_id = str(uuid.uuid4())
            node_id_map[old_id] = node.node_id
            sanitized.nodes[node.node_id] = node
        
        # 2. Fix edges - remove duplicates and invalid edges
        seen_edges = set()  # Track unique edges
        for edge in dsg.edges:
            if not isinstance(edge, list) or len(edge) != 2:
                continue
                
            source_id, target_id = edge
            if source_id in node_id_map and target_id in node_id_map:
                new_source = node_id_map[source_id]
                new_target = node_id_map[target_id]
                
                # Skip self-loops
                if new_source == new_target:
                    continue
                    
                # Skip duplicate edges
                edge_tuple = (new_source, new_target)
                if edge_tuple in seen_edges:
                    continue
                    
                seen_edges.add(edge_tuple)
                sanitized.edges.append([new_source, new_target])
        
        # 3. Validate the sanitized DSG
        is_valid, error_msg = validate_dsg(sanitized)
        if not is_valid:
            print(f"Sanitization produced invalid DSG: {error_msg}")
            return None
            
        return sanitized
        
    except Exception as e:
        print(f"Error sanitizing DSG: {e}")
        return None

def filter_valid_proposals(proposals: List[SingleProposal]) -> List[SingleProposal]:
    """
    Filters out invalid proposals and attempts to fix salvageable ones.
    Returns only valid proposals.
    """
    valid_proposals = []
    
    for prop in proposals:
        # Try to sanitize first
        sanitized_dsg = sanitize_dsg(prop.content)
        if sanitized_dsg:
            prop.content = sanitized_dsg
            valid_proposals.append(prop)
            continue
            
        # If sanitization failed, try to validate original
        is_valid, error_msg = validate_dsg(prop.content)
        if is_valid:
            valid_proposals.append(prop)
        else:
            print(f"Rejected invalid proposal '{prop.title}': {error_msg}")
    
    return valid_proposals 