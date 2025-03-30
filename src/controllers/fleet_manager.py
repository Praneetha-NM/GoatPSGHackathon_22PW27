import logging
from src.models.robot import Robot
from src.models.nav_graph import NavigationGraph
from src.utils.helpers import find_shortest_path  
from src.controllers.traffic_manager import TrafficManager

# Configure logging to write to a file
logging.basicConfig(filename='logs/fleet_logs.txt', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class FleetManager:
    """Manages the fleet of robots, their tasks, and interactions with the environment."""
    def __init__(self, nav_graph):
        """
        Initializes the FleetManager.

        Args:
            nav_graph (NavigationGraph): The graph representing the environment.
        """
        self.nav_graph = nav_graph
        self.robots = {}  
        self.next_robot_id = 1  
        self.charging_stations = self._find_charging_stations()  
        logging.info(f"Charging stations found: {self.charging_stations}")
        self.low_battery_threshold_auto_charge = 30.0  
        self.robots_going_to_charge = {} 
        self.traffic_manager = TrafficManager(self.nav_graph, self)  
        self.gui = None 
        self.occupied_lanes = set()

    def set_gui(self, gui_instance):
        """
        Sets the GUI instance for the FleetManager to enable GUI interactions.

        Args:
            gui_instance: The instance of the FleetGUI.
        """
        self.gui = gui_instance

    def spawn_robot(self, start_node):
        """
        Spawns a new robot at the specified start node.

        Args:
            start_node (any): The node ID where the robot should be created.

        Returns:
            Robot or None: The newly created Robot object, or None if the start node is invalid.
        """
        if start_node in self.nav_graph.graph.nodes():
            robot = Robot(start_node)
            robot.set_fleet_manager(self) # Give the robot a reference to the fleet manager
            self.robots[robot.id] = robot
            logging.info(f"Robot {robot.id} spawned at node {start_node}")
            return robot
        else:
            logging.warning(f"Cannot spawn robot at invalid node {start_node}")
            return None

    def _find_charging_stations(self):
        """
        Identifies all nodes in the navigation graph that are designated as charging stations.

        Returns:
            list: A list of node IDs that are charging stations.
        """
        return [node_id for node_id, data in self.nav_graph.get_vertices() if data.get('is_charger')]

    def assign_task(self, robot_id, destination_node, force=False):
        """
        Assigns a task to a specific robot to move to a destination node.

        Args:
            robot_id (str): The ID of the robot to assign the task to.
            destination_node (any): The node ID of the task destination.
            force (bool, optional): If True, forces the assignment even if battery is low. Defaults to False.

        Returns:
            bool: True if the task was successfully assigned, False otherwise.
        """
        robot = self.robots.get(robot_id)
        if robot:
            # Check if battery is too low for a new manual task (unless forced)
            if robot.get_battery_level() < self.low_battery_threshold_auto_charge and not force:
                robot.set_status("moving_to_charge")
                logging.info(f"Battery Low for Robot {robot_id}. Heading to Battery Station.")
                start_node = robot.get_location()
                charging_station = self._get_nearest_charging_station(start_node, self.robots_going_to_charge.values())
                if charging_station:
                    path = find_shortest_path(self.nav_graph.graph, start_node, charging_station)
                    if path and len(path) > 1:
                        robot.set_destination(charging_station, path)
                        self.robots_going_to_charge[robot_id] = charging_station  # Reserve the charger
                        return True
                    else:
                        logging.error(f"Robot {robot_id} battery low, but no path to charger!")
                        return False
                else:
                    logging.error(f"Robot {robot_id} battery low, but no charging station found!")
                    return False

            start_node = robot.get_location()
            logging.info(f"FleetManager: Finding path from {start_node} to {destination_node}")
            path = find_shortest_path(self.nav_graph.graph, start_node, destination_node)

            if path and len(path) > 1:
                # Check lanes for occupancy
                for i in range(len(path) - 1):
                    u, v = sorted((path[i], path[i + 1]))
                    if self.traffic_manager.is_lane_occupied(u, v):
                        logging.info(f"Lane between {u} and {v} is occupied. Task cannot be assigned.")
                        if self.gui:
                            self.gui.show_notification(f"Task for Robot {robot_id} to {destination_node} blocked: Lane occupied.")
                        return False


                robot.set_destination(destination_node, path)
                if not force and destination_node not in self.charging_stations:
                    robot.set_status("moving")
                elif force and destination_node in self.charging_stations:
                    # Status should already be "moving_to_charge"
                    pass
                elif destination_node in self.charging_stations:
                    robot.set_status("moving_to_charge") # For manual navigation to a charger
                return True
                
        return False

    def get_robot(self, robot_id):
        """
        Retrieves a robot by its ID.

        Args:
            robot_id (str): The ID of the robot to retrieve.

        Returns:
            Robot or None: The Robot object if found, None otherwise.
        """
        return self.robots.get(robot_id)

    def get_all_robots(self):
        """
        Returns a dictionary of all robots in the fleet.

        Returns:
            dict: A dictionary where keys are robot IDs and values are Robot objects.
        """
        return self.robots

    def can_move(self, robot, next_node):
        """
        Checks if a robot is allowed to move to a specific next node based on traffic.

        Args:
            robot (Robot): The robot attempting to move.
            next_node (any): The node the robot wants to move to.

        Returns:
            bool: True if the move is allowed, False otherwise.
        """
        current_node = robot.get_location()
        return self.traffic_manager.is_lane_free(current_node, next_node, robot.id)


    def moved(self, robot, previous_node):
        """
        Notifies the TrafficManager that a robot has moved and freed a lane.

        Args:
            robot (Robot): The robot that has moved.
            previous_node (any): The node the robot was previously at.
        """
        logging.info(f"FM.moved: Robot {robot.id} at {robot.get_location()}, Previous: {previous_node}")
        current_node = robot.get_location()
        if previous_node is not None:
            self.traffic_manager.free_lane(previous_node, current_node, robot.id)
        


    # Methods to directly interact with TrafficManager if needed
    def is_lane_occupied(self, u, v):
        """Checks if the lane between nodes u and v is occupied."""
        return self.traffic_manager.is_lane_occupied(u, v)

    def occupy_lane(self, u, v, robot_id):
        """Marks the lane between nodes u and v as occupied by robot_id."""
        return self.traffic_manager.occupy_lane(u, v, robot_id)

    def free_lane(self, u, v, robot_id):
        """Marks the lane between nodes u and v as free (if occupied by robot_id)."""
        return self.traffic_manager.free_lane(u, v, robot_id)

    def remove_robot(self, robot_id):
        """Removes a robot from the fleet."""
        if robot_id in self.robots:
            del self.robots[robot_id]
            logging.info(f"Robot {robot_id} removed.")
            return True
        return False

    def check_battery_levels(self):
        """Checks the battery levels of all robots and initiates automatic charging if needed."""
        for robot_id, robot in self.robots.items():
            # Check if battery is low and robot is not already charging or going to charge
            if robot.is_battery_low() and robot.get_battery_level() <= self.low_battery_threshold_auto_charge and robot.get_status() not in ["charging", "moving_to_charge"]  and robot_id not in self.robots_going_to_charge:

                # Get a set of currently reserved charging stations
                reserved_chargers = set(self.robots_going_to_charge.values())
                # Find the nearest available charging station
                nearest_charger = self._get_nearest_charging_station(robot.get_location(),reserved_chargers)
                if nearest_charger:
                    # Reserve the charging station for this robot
                    self.robots_going_to_charge[robot_id] = nearest_charger
                    logging.warning(f"Robot {robot_id} battery low ({robot.get_battery_level():.2f}%), automatically heading to charger {nearest_charger}")
                    # Set the robot's destination and status to moving to charge
                    robot.set_destination(nearest_charger, find_shortest_path(self.nav_graph.graph, robot.get_location(), nearest_charger))
                    robot.set_status("moving_to_charge")
                    # Force assign the task to override manual task restrictions
                    self.assign_task(robot_id, nearest_charger, force=True)
                else:
                    logging.error(f"Robot {robot_id} battery low, but no charging station reachable!")
            elif robot.get_status() == "idle" and robot_id in self.robots_going_to_charge:
                # If a robot becomes idle (e.g., due to battery failure) while intending to charge, remove the intention
                del self.robots_going_to_charge[robot_id]
                

    def _get_nearest_charging_station(self, current_node, reserved_chargers=None):
        """
        Finds the nearest available charging station to a given node.

        Args:
            current_node (any): The current node ID.
            reserved_chargers (set, optional): A set of charging station IDs that are currently reserved. Defaults to None.

        Returns:
            any or None: The ID of the nearest available charging station, or None if none is found.
        """
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
        """
        Unassigns a charging station from a robot, making it available for others.

        Args:
            robot_id (str): The ID of the robot that was using the charging station.
            charging_node (any): The ID of the charging station node.
        """
        if robot_id in self.robots_going_to_charge:
            del self.robots_going_to_charge[robot_id]