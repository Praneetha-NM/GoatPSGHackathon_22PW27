# fleet_management_system/src/models/nav_graph.py
import json
import networkx as nx
import matplotlib.pyplot as plt

class NavigationGraph:
    def __init__(self, json_path):
        self.json_path = json_path
        self.graph = nx.Graph()
        self.vertices_data = {}
        self._load_graph()

    def _load_graph(self):
        with open(self.json_path, 'r') as f:
            data = json.load(f)
            if 'level1' in data['levels']:
                level_data = data['levels']['level1']
            elif 'l0' in data['levels']:
                level_data = data['levels']['l0']
            elif 'l1' in data['levels']:
                level_data = data['levels']['l1']
            else:
                level_data = None  # Or some default value if none of the keys exist
            vertices = level_data['vertices']
            lanes = level_data['lanes']

            for i, vertex_data in enumerate(vertices):
                x, y, attributes = vertex_data
                self.graph.add_node(i, pos=(x, y), **attributes)
                self.vertices_data[i] = {'pos': (x, y), **attributes}

            for lane in lanes:
                u, v, attributes = lane
                self.graph.add_edge(u, v, **attributes)

    def get_vertices(self):
        return self.graph.nodes(data=True)

    def get_edges(self):
        return self.graph.edges(data=True)

    def get_vertex_by_name(self, name):
        for node, data in self.graph.nodes(data=True):
            if data.get('name') == name:
                return node
        return None

    def get_vertex_data(self, node_id):
        return self.vertices_data.get(node_id)

    def get_shortest_path(self, start_node, end_node):
        try:
            return nx.shortest_path(self.graph, source=start_node, target=end_node)
        except nx.NetworkXNoPath:
            return None

    def visualize(self):
        pos = nx.get_node_attributes(self.graph, 'pos')
        labels = {n: d.get('name', '') for n, d in self.graph.nodes(data=True)}
        nx.draw(self.graph, pos, with_labels=True, labels=labels, node_size=500, node_color='lightblue', font_size=8, font_weight='bold')
        nx.draw_networkx_edge_labels(self.graph, pos, edge_labels=nx.get_edge_attributes(self.graph, 'speed_limit'))
        plt.title("Navigation Graph")
        plt.show()

