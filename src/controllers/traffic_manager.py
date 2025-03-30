import logging
import time
logging.basicConfig(filename='logs/fleet_logs.txt', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class TrafficManager:
    """Manages traffic flow to prevent collisions and deadlocks."""
    def __init__(self, nav_graph, fleet_manager):
        """
        Initializes the TrafficManager.

        Args:
            nav_graph (NavigationGraph): The graph representing the environment.
            fleet_manager (FleetManager): A reference to the FleetManager.
        """
        self.nav_graph = nav_graph
        self.fleet_manager = fleet_manager
        self.occupied_lanes = {}  # (sorted_tuple(node_id1, node_id2)): robot_id
        self.robot_intentions = {} # robot_id: {'current': node, 'next': node} (not actively used in this version)
        self.waiting_robots = {}   # robot_id: {'intended_lane': (u, v), 'wait_start_time': timestamp}
        self.intersection_reservations = {} # node_id: robot_id (basic exclusive access)
        self.intersection_wait_queue = {} # node_id: [robot_id]

    def register_robot_intention(self, robot_id, current_node, next_node):
        """Registers the immediate intention of a robot to move between two nodes.
        (Currently not actively used in the core lane occupancy logic).
        """
        self.robot_intentions[robot_id] = {'current': current_node, 'next': next_node}

    def clear_robot_intention(self, robot_id):
        """Clears the movement intention of a robot.
        (Currently not actively used in the core lane occupancy logic).
        """
        if robot_id in self.robot_intentions:
            del self.robot_intentions[robot_id]

    def is_lane_occupied(self, u, v):
        """
        Checks if the lane between two nodes is currently occupied.

        Args:
            u (any): The ID of the first node.
            v (any): The ID of the second node.

        Returns:
            bool: True if the lane is occupied, False otherwise.
        """
        lane = tuple(sorted((u, v)))
        return lane in self.occupied_lanes

    def is_lane_free(self, node1, node2, robot_id):
        node1_str = str(node1)
        node2_str = str(node2)
        lane = tuple(sorted((node1_str, node2_str)))
        return lane not in self.occupied_lanes or self.occupied_lanes[lane] == robot_id

    def occupy_lane(self, u, v, robot_id):
        """
        Marks a lane as occupied by a specific robot.

        Args:
            u (any): The ID of the first node of the lane.
            v (any): The ID of the second node of the lane.
            robot_id (str): The ID of the robot occupying the lane.

        Returns:
            bool: True if the lane was successfully occupied, False if it was already occupied by another robot.
        """
        node1_str = str(u)
        node2_str = str(v)
        lane = tuple(sorted((node1_str, node2_str)))
        if lane in self.occupied_lanes and self.occupied_lanes[lane] != robot_id:
            logging.warning(f"TrafficManager: Lane {lane} already occupied by robot {self.occupied_lanes[lane]}, but robot {robot_id} trying to occupy.")
            return False
        self.occupied_lanes[lane] = robot_id
        logging.info(f"TrafficManager: Robot {robot_id} occupied lane {lane}")
        if lane in self.waiting_robots and self.waiting_robots[lane] == robot_id:
            del self.waiting_robots[lane]
            logging.info(f"TrafficManager: Robot {robot_id} (previously waiting) occupied lane {lane}")
        return True

    def free_lane(self, u, v, robot_id):
        """
        Marks a lane as free, if it was occupied by the specified robot.

        Args:
            u (any): The ID of the first node of the lane.
            v (any): The ID of the second node of the lane.
            robot_id (str): The ID of the robot that was occupying the lane.

        Returns:
            bool: True if the lane was successfully freed, False if it wasn't occupied by the given robot or not occupied at all.
        """
        node1_str = str(u)
        node2_str = str(v)
        lane = tuple(sorted((node1_str, node2_str)))

        if lane in self.occupied_lanes and self.occupied_lanes[lane] == robot_id:
            del self.occupied_lanes[lane]
            logging.info(f"TrafficManager: Robot {robot_id} freed lane {lane}")
            self.check_waiting_robots(v) # Check if any waiting robot can now move from the freed node
            return True
        elif lane in self.occupied_lanes:
            logging.warning(f"TrafficManager: Robot {robot_id} tried to free lane {lane} occupied by {self.occupied_lanes[lane]}.")
            return False
        return True

    def request_lane(self, robot_id, current_node, next_node):
        """
        Checks if a robot can move onto the next lane. If occupied, marks the robot as waiting.

        Args:
            robot_id (str): The ID of the robot requesting the lane.
            current_node (any): The current node of the robot.
            next_node (any): The node the robot wants to move to.

        Returns:
            bool: True if the lane is free, False if the lane is occupied and the robot is now waiting.
        """
        current_node = str(current_node)
        next_node = str(next_node)
        lane = tuple(sorted((current_node, next_node)))
        
        if self.is_lane_free(current_node, next_node, robot_id):
            return True
        else:
            # Mark the robot as waiting
            self.waiting_robots[lane] = robot_id
            robot = self.fleet_manager.get_robot(robot_id)
            if robot:
                robot.set_status("waiting")  # Update robot status to waiting
            logging.info(f"TrafficManager: Robot {robot_id} is waiting for lane {lane}.")
            return False


    def _process_waiting_robots(self, freed_node1, freed_node2):
        """
        Checks if any waiting robots can now move onto the freed lane.

        Args:
            freed_node1 (any): The ID of the first node of the freed lane.
            freed_node2 (any): The ID of the second node of the freed lane.
        """
        freed_lane = tuple(sorted((freed_node1, freed_node2)))
        for robot_id, wait_info in list(self.waiting_robots.items()):
            if wait_info['intended_lane'] == freed_lane:
                robot = self.fleet_manager.get_robot(robot_id)
                if robot and robot.get_status() == "waiting" and robot.get_next_node() == max(wait_info['intended_lane']) and robot.get_location() == min(wait_info['intended_lane']):
                    current = min(wait_info['intended_lane'])
                    next_n = max(wait_info['intended_lane'])
                    if self.occupy_lane(current, next_n, robot_id):
                        robot.set_status("moving") # Tell the robot it can now move
                        del self.waiting_robots[robot_id]
                        return # Allow only one robot to proceed per lane freeing for simplicity

    # --- Basic Intersection Management (First Pass) ---

    def request_intersection(self, robot_id, intersection_node):
        """
        Requests exclusive access to an intersection node for a robot.

        Args:
            robot_id (str): The ID of the robot requesting access.
            intersection_node (any): The ID of the intersection node.

        Returns:
            bool: True if access is granted, False otherwise (occupied or added to wait queue).
        """
        if intersection_node not in self.intersection_reservations:
            self.intersection_reservations[intersection_node] = robot_id
            return True
        elif self.intersection_reservations[intersection_node] == robot_id:
            return True # Already reserved by this robot
        else:
            if intersection_node not in self.intersection_wait_queue:
                self.intersection_wait_queue[intersection_node] = []
            if robot_id not in self.intersection_wait_queue[intersection_node]:
                self.intersection_wait_queue[intersection_node].append(robot_id)
            return False

    def release_intersection(self, robot_id, intersection_node):
        """
        Releases a robot's exclusive access to an intersection node.

        Args:
            robot_id (str): The ID of the robot releasing the intersection.
            intersection_node (any): The ID of the intersection node.

        Returns:
            bool: True if the intersection was successfully released by the robot.
        """
        if intersection_node in self.intersection_reservations and self.intersection_reservations[intersection_node] == robot_id:
            del self.intersection_reservations[intersection_node]
            self._process_intersection_queue(intersection_node) # Grant access to the next waiting robot
            return True
        return False

    def _process_intersection_queue(self, intersection_node):
        """Grants access to the next waiting robot for an intersection."""
        if intersection_node in self.intersection_wait_queue and self.intersection_wait_queue[intersection_node]:
            next_robot_id = self.intersection_wait_queue[intersection_node].pop(0)
            if intersection_node not in self.intersection_reservations:
                self.intersection_reservations[intersection_node] = next_robot_id
                robot = self.fleet_manager.get_robot(next_robot_id)
                if robot and robot.get_status() == "waiting": # If waiting at intersection, allow move
                    robot.set_status("moving")

    def check_waiting_robots(self, freed_node):
        """Checks if any waiting robots can now move from the node where a lane was just freed."""
        for (u, v), robot_id in list(self.waiting_robots.items()):
            if u == freed_node:
                if self.is_lane_free(u, v, robot_id):
                    if self.occupy_lane(u, v, robot_id):
                        # The waiting robot will now proceed in its next move step
                        del self.waiting_robots[(u, v)]
                        logging.info(f"TrafficManager: Allowed waiting robot {robot_id} to occupy lane ({u}, {v}) from freed node {freed_node}.")
                        # You might need to signal the FleetManager or Robot to trigger the move
                    break # Allow only one waiting robot to move at a time from a freed node in this simple implementation
