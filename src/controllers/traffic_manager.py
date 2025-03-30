# fleet_management_system/src/controllers/traffic_manager.py
import logging

logging.basicConfig(filename='logs/fleet_logs.txt', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class TrafficManager:
    def __init__(self, nav_graph, fleet_manager):
        self.nav_graph = nav_graph
        self.fleet_manager = fleet_manager
        self.occupied_lanes = {}  # (u, v): robot_id  (always sorted tuple for key)
        self.robot_intentions = {} # robot_id: {'current': node, 'next': node}
        self.waiting_robots = {}   # robot_id: {'intended_lane': (u, v), 'wait_start_time': timestamp}
        self.intersection_reservations = {} # node_id: robot_id (basic exclusive access)
        self.intersection_wait_queue = {} # node_id: [robot_id]

        logging.info("Traffic Manager initialized.")

    def register_robot_intention(self, robot_id, current_node, next_node):
        """Registers the immediate intention of a robot to move between two nodes."""
        self.robot_intentions[robot_id] = {'current': current_node, 'next': next_node}

    def clear_robot_intention(self, robot_id):
        """Clears the movement intention of a robot."""
        if robot_id in self.robot_intentions:
            del self.robot_intentions[robot_id]

    def is_lane_occupied(self, u, v):
        lane = tuple(sorted((u, v)))
        occupied = lane in self.occupied_lanes
        print(f"TM.is_lane_occupied: Checking lane {lane}. Occupied: {occupied}, Occupied Lanes: {self.occupied_lanes}")
        return occupied

    def occupy_lane(self, u, v, robot_id):
        """Marks a lane as occupied by a robot."""
        lane = tuple(sorted((u, v)))
        if lane in self.occupied_lanes and self.occupied_lanes[lane] != robot_id:
            logging.warning(f"Robot {robot_id} tried to occupy already occupied lane {lane} by {self.occupied_lanes[lane]}.")
            return False
        self.occupied_lanes[lane] = robot_id
        if robot_id in self.waiting_robots and tuple(sorted((u, v))) == self.waiting_robots[robot_id]['intended_lane']:
            del self.waiting_robots[robot_id]
            logging.info(f"Robot {robot_id} entering intended lane {lane}, no longer waiting.")
        return True

    def free_lane(self, u, v, robot_id):
        lane = tuple(sorted((u, v)))
        print(f"TM.free_lane: Robot {robot_id} trying to free lane {lane}. Current occupied lanes: {self.occupied_lanes}")
        if lane in self.occupied_lanes:
            occupied_by = self.occupied_lanes[lane]
            print(f"TM.free_lane: Lane {lane} is occupied by robot {occupied_by}.")
            if occupied_by == robot_id:
                del self.occupied_lanes[lane]
                self._process_waiting_robots(u, v)
                print(f"TM.free_lane: Robot {robot_id} successfully freed lane {lane}. New occupied lanes: {self.occupied_lanes}")
                return True
            else:
                logging.warning(f"Robot {robot_id} tried to free lane {lane} occupied by {occupied_by}.")
                return False
        else:
            print(f"TM.free_lane: Lane {lane} is not currently occupied.")
            return True

    def request_lane(self, robot_id, current_node, next_node):
        """Checks if a robot can move onto the next lane. If occupied, marks the robot as waiting."""
        lane = tuple(sorted((current_node, next_node)))
        if self.is_lane_occupied(current_node, next_node, robot_id):
            if robot_id not in self.waiting_robots:
                self.waiting_robots[robot_id] = {'intended_lane': lane, 'wait_start_time': time.time()}
                logging.info(f"Robot {robot_id} requesting occupied lane {lane}, now waiting at {current_node}.")
            return False
        return True

    def _process_waiting_robots(self, freed_node1, freed_node2):
        """Checks if any waiting robots can now move onto the freed lane."""
        freed_lane = tuple(sorted((freed_node1, freed_node2)))
        for robot_id, wait_info in list(self.waiting_robots.items()):
            if wait_info['intended_lane'] == freed_lane:
                robot = self.fleet_manager.get_robot(robot_id)
                if robot and robot.get_status() == "waiting": # Ensure robot is still intending to move there
                    current = min(wait_info['intended_lane'])
                    next_n = max(wait_info['intended_lane'])
                    if robot.get_location() == current and robot.get_next_node() == next_n:
                        if self.occupy_lane(current, next_n, robot_id):
                            robot.set_status("moving") # Tell the robot it can now move
                            del self.waiting_robots[robot_id]
                            logging.info(f"Robot {robot_id} granted access to lane {freed_lane} after waiting.")
                            return # Allow only one robot to proceed per lane freeing for simplicity

    # --- Basic Intersection Management (First Pass) ---

    def request_intersection(self, robot_id, intersection_node):
        """Requests access to an intersection node."""
        if intersection_node not in self.intersection_reservations:
            self.intersection_reservations[intersection_node] = robot_id
            logging.info(f"Robot {robot_id} reserved intersection {intersection_node}.")
            return True
        elif self.intersection_reservations[intersection_node] == robot_id:
            return True # Already reserved by this robot
        else:
            if intersection_node not in self.intersection_wait_queue:
                self.intersection_wait_queue[intersection_node] = []
            if robot_id not in self.intersection_wait_queue[intersection_node]:
                self.intersection_wait_queue[intersection_node].append(robot_id)
                logging.info(f"Robot {robot_id} waiting for intersection {intersection_node}.")
            return False

    def release_intersection(self, robot_id, intersection_node):
        """Releases access to an intersection node."""
        if intersection_node in self.intersection_reservations and self.intersection_reservations[intersection_node] == robot_id:
            del self.intersection_reservations[intersection_node]
            self._process_intersection_queue(intersection_node)
            logging.info(f"Robot {robot_id} released intersection {intersection_node}.")
            return True
        return False

    def _process_intersection_queue(self, intersection_node):
        """Grants access to the next waiting robot for an intersection."""
        if intersection_node in self.intersection_wait_queue and self.intersection_wait_queue[intersection_node]:
            next_robot_id = self.intersection_wait_queue[intersection_node].pop(0)
            if intersection_node not in self.intersection_reservations:
                self.intersection_reservations[intersection_node] = next_robot_id
                robot = self.fleet_manager.get_robot(next_robot_id)
                if robot:
                    robot.set_status("moving") # If waiting at intersection, allow move
                    logging.info(f"Intersection {intersection_node} granted to robot {next_robot_id} from queue.")

import time # Import time for waiting logic