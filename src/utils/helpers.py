# fleet_management_system/src/utils/helpers.py
import networkx as nx

def find_shortest_path(graph, start_node, end_node):
    """
    Finds the shortest path between two nodes in a NetworkX graph.

    Args:
        graph (nx.Graph): The navigation graph.
        start_node: The starting node.
        end_node: The destination node.

    Returns:
        list: A list of nodes representing the shortest path, or None if no path exists.
    """
    try:
        return nx.shortest_path(graph, source=start_node, target=end_node)
    except nx.NetworkXNoPath:
        return None
