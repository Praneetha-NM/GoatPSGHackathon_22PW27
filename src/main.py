import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from src.gui.fleet_gui import FleetGUI

if __name__ == '__main__':
    nav_graph_path = os.path.join(ROOT_DIR, 'data', 'nav_graph_1.json') #Can Change to nav_graph_2.json or nav_graph_3.json 
    gui = FleetGUI(nav_graph_path)
    gui.run()