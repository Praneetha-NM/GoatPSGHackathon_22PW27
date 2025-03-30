import json
import networkx as nx
import matplotlib.pyplot as plt

class NavigationGraph:
    """
    Represents the navigation environment as a graph.
    Nodes represent locations (vertices), and edges represent paths (lanes) between them.
    """
    def __init__(self, json_path):
        """
        Initializes the NavigationGraph by loading data from a JSON file.

        Args:
            json_path (str): The path to the JSON file containing the graph data.
        """
        self.json_path = json_path
        self.graph = nx.Graph()  # Use NetworkX graph for underlying structure
        self.vertices_data = {}  # Store additional data for each vertex, keyed by node ID
        self._load_graph()

    def _load_graph(self):
        """
        Loads the graph data from the JSON file.
        The JSON file should contain 'levels' with at least one level defined (e.g., 'level1', 'l0', or 'l1').
        Each level should have 'vertices' (a list of [x, y, {attributes}]) and 'lanes' (a list of [u, v, {attributes}]).
        """
        try:
            with open(self.json_path, 'r') as f:
                data = json.load(f)
                level_data = None
                # Prioritize loading from 'level1', then 'l0', then 'l1'
                if 'level1' in data['levels']:
                    level_data = data['levels']['level1']
                elif 'l0' in data['levels']:
                    level_data = data['levels']['l0']
                elif 'l1' in data['levels']:
                    level_data = data['levels']['l1']
                else:
                    raise ValueError("No valid level data ('level1', 'l0', or 'l1') found in the JSON file.")

                vertices = level_data['vertices']
                lanes = level_data['lanes']

                # Add vertices to the graph
                for i, vertex_data in enumerate(vertices):
                    x, y, attributes = vertex_data
                    self.graph.add_node(i, pos=(x, y), **attributes)  # Store position and other attributes in the node
                    self.vertices_data[i] = {'pos': (x, y), **attributes} # Store vertex data in a separate dictionary

                # Add edges (lanes) to the graph
                for lane in lanes:
                    u, v, attributes = lane
                    self.graph.add_edge(u, v, **attributes)  # Store attributes (e.g., speed limit) in the edge

        except FileNotFoundError:
            raise FileNotFoundError(f"Error: Navigation graph JSON file not found at {self.json_path}")
        except json.JSONDecodeError:
            raise json.JSONDecodeError(f"Error: Could not decode JSON from {self.json_path}")
        except KeyError as e:
            raise KeyError(f"Error: Missing key in the JSON file: {e}")
        except ValueError as e:
            raise ValueError(f"Error loading graph: {e}")

    def get_vertices(self):
        """
        Returns an iterator over the vertices (nodes) of the graph, along with their attributes.

        Returns:
            networkx.classes.reportviews.NodeDataView: An iterator of (node_id, attribute_dict).
        """
        return self.graph.nodes(data=True)

    def get_edges(self):
        """
        Returns an iterator over the edges of the graph, along with their attributes.

        Returns:
            networkx.classes.reportviews.EdgeDataView: An iterator of (node_u, node_v, attribute_dict).
        """
        return self.graph.edges(data=True)

    def get_vertex_by_name(self, name):
        """
        Finds and returns the ID of a vertex based on its 'name' attribute.

        Args:
            name (str): The name of the vertex to find.

        Returns:
            any or None: The ID of the vertex if found, otherwise None.
        """
        for node, data in self.graph.nodes(data=True):
            if data.get('name') == name:
                return node
        return None

    def get_vertex_data(self, node_id):
        """
        Retrieves the data associated with a specific vertex ID.

        Args:
            node_id (any): The ID of the vertex.

        Returns:
            dict or None: A dictionary containing the vertex data (including position and other attributes),
                           or None if the node ID is not found.
        """
        return self.vertices_data.get(node_id)

    def get_shortest_path(self, start_node, end_node):
        """
        Calculates the shortest path between two nodes in the graph using Dijkstra's algorithm.

        Args:
            start_node (any): The ID of the starting node.
            end_node (any): The ID of the destination node.

        Returns:
            list or None: A list of node IDs representing the shortest path from start to end,
                           or None if no path exists.
        """
        try:
            return nx.shortest_path(self.graph, source=start_node, target=end_node)
        except nx.NetworkXNoPath:
            return None
        except nx.NetworkXError as e:
            print(f"NetworkX Error: {e}")
            return None

    def visualize(self):
        """
        Visualizes the navigation graph using Matplotlib.
        Nodes are labeled with their names (if available), and edges might be labeled with speed limits.
        """
        pos = nx.get_node_attributes(self.graph, 'pos')  # Get node positions for layout
        labels = {n: d.get('name', '') for n, d in self.graph.nodes(data=True)} # Get node names for labels
        nx.draw(self.graph, pos, with_labels=True, labels=labels, node_size=500, node_color='lightblue', font_size=8, font_weight='bold')
        # Draw edge labels (e.g., speed limits) if the attribute exists
        edge_labels = {(u, v): d.get('speed_limit', '') for u, v, d in self.graph.edges(data=True)}
        nx.draw_networkx_edge_labels(self.graph, pos, edge_labels=edge_labels)
        plt.title("Navigation Graph")
        plt.show()