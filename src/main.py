# fleet_management_system/src/main.py
import os
import sys

# Add the project root to the Python path if running directly
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from src.gui.fleet_gui import FleetGUI

if __name__ == '__main__':
    nav_graph_path = os.path.join(ROOT_DIR, 'data', 'nav_graph_1.json')
    gui = FleetGUI(nav_graph_path)
    gui.run()