# fleet_management_system/src/controllers/fleet_manager.py
import logging

from src.models.robot import Robot
from src.models.nav_graph import NavigationGraph
from src.utils.helpers import find_shortest_path  # Assuming this will be in helpers.py
from src.controllers.traffic_manager import TrafficManager

logging.basicConfig(filename='logs/fleet_logs.txt', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class FleetManager:
    def __init__(self, nav_graph):
        self.nav_graph = nav_graph
        self.robots = {}
        self.next_robot_id = 1
        self.charging_stations = self._find_charging_stations()
        logging.info(f"Charging stations found: {self.charging_stations}")
        self.low_battery_threshold_auto_charge = 30.0 # New threshold for automatic charging
        self.robots_going_to_charge = {}  # {robot_id: charging_node_id}
        self.traffic_manager = TrafficManager(self.nav_graph, self) # Initialize Traffic Manager

    def spawn_robot(self, start_node):
        if start_node in self.nav_graph.graph.nodes():
            robot = Robot(start_node)
            self.robots[robot.id] = robot
            logging.info(f"Robot {robot.id} spawned at node {start_node}")
            return robot
        else:
            logging.warning(f"Cannot spawn robot at invalid node {start_node}")
            return None
    def _find_charging_stations(self):
        return [node_id for node_id, data in self.nav_graph.get_vertices() if data.get('is_charger')]

    def assign_task(self, robot_id, destination_node, force=False):
        robot = self.robots.get(robot_id)
        if robot:
            if robot.get_battery_level() < self.low_battery_threshold_auto_charge and not force:
                print(f"Robot {robot_id} battery low ({robot.get_battery_level():.2f}%), cannot assign manual task. Automatically heading to charger.")
                robot.set_status("moving_to_charge")
                logging.info(f"Battery Low for Robot {robot_id}. Heading to Battery Station.")
                start_node = robot.get_location()
                charging_station = self._get_nearest_charging_station(start_node, self.robots_going_to_charge.values())
                if charging_station:
                    path = find_shortest_path(self.nav_graph.graph, start_node, charging_station)
                    if path and len(path) > 1:
                        robot.set_destination(charging_station, path)
                        self.robots_going_to_charge[robot_id] = charging_station # Reserve the charger
                        print(f"Robot {robot_id} automatically set destination to charger: {charging_station}, path: {path}, status: {robot.get_status()}")
                        return True
                    else:
                        logging.error(f"Robot {robot_id} battery low, but no path to charger!")
                        return False
                else:
                    logging.error(f"Robot {robot_id} battery low, but no charging station found!")
                    return False

            start_node = robot.get_location()
            print(f"FleetManager: Finding path from {start_node} to {destination_node}")
            path = find_shortest_path(self.nav_graph.graph, start_node, destination_node)
            print(f"FleetManager: Path found: {path}")
            if path and len(path) > 1:
                u, v = sorted((path[0], path[1]))
                if self.traffic_manager.is_lane_occupied(u, v):
                    print(f"Lane between {path[0]} and {path[1]} is occupied. Task cannot be assigned.")
                    return False
                elif destination_node in self.traffic_manager.occupied_lanes.values(): # Basic check if destination is on an occupied lane
                    print(f"Destination node {destination_node} seems to be on an occupied lane. Task cannot be assigned.")
                    return False
                else:
                    robot.set_destination(destination_node, path)
                    if not force:
                        robot.set_status("moving")
                    logging.info(f"Task assigned to Robot {robot_id}: {start_node} to {destination_node}, path: {path}")
                    print(f"Robot {robot_id} path: {path}, status: {robot.get_status()}")
                    return True
            elif start_node == destination_node:
                print("Robot is already at the destination.")
                return False
            else:
                print("No path to destination.")
                return False
        return False

    def get_robot(self, robot_id):
        return self.robots.get(robot_id)

    def get_all_robots(self):
        return self.robots

    def can_move(self, robot, next_node):
        current_node = robot.get_location()
        occupied = self.traffic_manager.is_lane_occupied(current_node, next_node)
        print(f"FM.can_move: Robot {robot.id} from {current_node} to {next_node}. Lane occupied: {occupied}")
        return not occupied

    def moved(self, robot, previous_node):
        """Notifies the TrafficManager that a robot has moved and freed a lane."""
        logging.info(f"FM.moved: Robot {robot.id} at {robot.get_location()}, Previous: {previous_node}")
        current_node = robot.get_location()
        if previous_node is not None:
            self.traffic_manager.free_lane(previous_node, current_node, robot.id)
        next_node = robot.get_next_node()
        if next_node:
            self.traffic_manager.occupy_lane(current_node, next_node, robot.id)


    # Methods to directly interact with TrafficManager if needed
    def is_lane_occupied(self, u, v):
        return self.traffic_manager.is_lane_occupied(u, v)

    def occupy_lane(self, u, v, robot_id):
        return self.traffic_manager.occupy_lane(u, v, robot_id)

    def free_lane(self, u, v, robot_id):
        return self.traffic_manager.free_lane(u, v, robot_id)

    def remove_robot(self, robot_id):
        if robot_id in self.robots:
            del self.robots[robot_id]
            logging.info(f"Robot {robot_id} removed.")
            return True
        return False
    def check_battery_levels(self):
        for robot_id, robot in self.robots.items():
            if robot.is_battery_low() and robot.get_battery_level() <= self.low_battery_threshold_auto_charge and robot.get_status() not in ["charging", "moving_to_charge"]  and robot_id not in self.robots_going_to_charge:
                
                reserved_chargers = set(self.robots_going_to_charge.values())
                nearest_charger = self._get_nearest_charging_station(robot.get_location(),reserved_chargers)
                if nearest_charger:
                    self.robots_going_to_charge[robot_id] = nearest_charger
                    logging.warning(f"Robot {robot_id} battery low ({robot.get_battery_level():.2f}%), automatically heading to charger {nearest_charger}")
                    print(f"Robot {robot_id} battery low, automatically heading to charger {nearest_charger}")
                    robot.set_destination(nearest_charger, find_shortest_path(self.nav_graph.graph, robot.get_location(), nearest_charger))
                    robot.set_status("moving_to_charge")
                    self.assign_task(robot_id, nearest_charger, force=True) # Use force=True to bypass manual task restrictions
                else:
                    logging.error(f"Robot {robot_id} battery low, but no charging station reachable!")
            elif robot.get_status() == "idle" and robot_id in self.robots_going_to_charge:
                # If a robot in 'battery_failure' was going to charge, remove the intention
                del self.robots_going_to_charge[robot_id]
                print(f"FleetManager: Removed charging intention for robot {robot_id} due to battery failure.")


    def _get_nearest_charging_station(self, current_node, reserved_chargers=None):
        if not self.charging_stations:
            return None
        shortest_distance = float('inf')
        nearest_charger = None
        available_chargers = []
        if reserved_chargers is None:
            reserved_chargers = set()
        else:
            reserved_chargers = set(reserved_chargers)

        # Filter out occupied and reserved charging stations
        for charger in self.charging_stations:
            is_occupied = False
            for robot_id, robot in self.robots.items():
                if robot.get_location() == charger and robot.get_status() not in ["moving_to_charge", "charging"]:
                    is_occupied = True
                    break
            if not is_occupied and charger not in reserved_chargers:
                available_chargers.append(charger)

        if not available_chargers:
            return None

        for charger in available_chargers:
            path = find_shortest_path(self.nav_graph.graph, current_node, charger)
            if path:
                distance = len(path)
                if distance < shortest_distance:
                    shortest_distance = distance
                    nearest_charger = charger

        return nearest_charger

    def unassign_charging_station(self, robot_id, charging_node):
        logging.info(f"Robot {robot_id} finished charging at {charging_node}, station is now free.")
        print(f"FM: unassign_charging_station called for robot {robot_id} at {charging_node}") # DEBUG
        if robot_id in self.robots_going_to_charge:
            del self.robots_going_to_charge[robot_id]
            print(f"FM: Robot {robot_id} removed from robots_going_to_charge.") # DEBUG
        
