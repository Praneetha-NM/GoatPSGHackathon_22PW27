import time
import uuid
import logging

class Robot:
    """Represents a mobile robot within the fleet."""
    def __init__(self, start_node, battery_capacity=100.0, low_battery_threshold=30.0):
        """
        Initializes a new Robot instance.

        Args:
            start_node (any): The initial location (node ID) of the robot.
            battery_capacity (float): The maximum battery level of the robot.
            low_battery_threshold (float): The battery level below which the robot is considered low.
        """
        self.id = str(uuid.uuid4())[:8]  # Unique identifier for the robot
        self.current_node = start_node  # Current location of the robot
        self.next_node = None  # The next node the robot intends to move to
        self.path = None  # The planned path for the robot's current task
        self.path_index = 0  # The current index in the planned path
        self.status = "idle"  # Current status of the robot: idle, moving, waiting, charging, task_complete
        self.destination_node = None  # The final destination node for the current task
        self.battery_level = battery_capacity  # Current battery level
        self.battery_capacity = battery_capacity  # Maximum battery capacity
        self.low_battery_threshold = low_battery_threshold  # Threshold for low battery
        self.fleet_manager = None # Reference to the FleetManager, set later
        self.charging_start_time = None # Timestamp when charging started
        self.intended_next_node = None # Store the node the robot is trying to move to
        logging.info(f"Robot {self.id} initialized at {start_node} with battery {self.battery_level:.2f}")

    def get_location(self):
        """Returns the current location (node ID) of the robot."""
        return self.current_node

    def get_next_node(self):
        """Returns the next intended node of the robot."""
        return self.next_node

    def get_path(self):
        """Returns the current planned path of the robot."""
        return self.path

    def get_status(self):
        """Returns the current status of the robot."""
        return self.status

    def set_status(self, status):
        """Sets the current status of the robot and logs the change."""
        self.status = status
        logging.info(f"Robot {self.id} status updated to {status}")

    def set_destination(self, destination_node, path):
        """
        Sets the destination node and the planned path for the robot.

        Args:
            destination_node (any): The ID of the final destination node.
            path (list): A list of node IDs representing the planned path.
        """
        self.destination_node = destination_node
        self.path = path
        self.path_index = 1  # Start from the second node in the path (index 0 is current)
        if self.path and len(self.path) > 1:
            self.next_node = self.path[self.path_index]
        elif path and len(path) == 1 and path[0] == self.current_node:
            # Already at the destination
            self.destination_node = destination_node
            self.path = path
            self.path_index = 0
            self.next_node = None
            self.status = "task_complete"
        else:
            # Invalid or empty path
            self.destination_node = None
            self.path = None
            self.path_index = 0
            self.next_node = None
            if self.status in ["moving", "moving_to_charge"]:
                self.status = "idle" # Revert to idle if no valid path

    def get_intended_next_node(self):
        return self.intended_next_node

    def move(self):
        """
        Attempts to move the robot along its planned path.
        Handles battery drain, path progression, and status updates.

        Returns:
            bool: True if the robot reached its next intended point (either intermediate or final), False otherwise.
        """
        if self.status == "waiting":
            logging.info(f"Robot {self.id} is waiting and cannot move.")
            return False # Cannot move if waiting for a lane

        if self.status in ["moving","moving_to_charge"]:
            # Check for battery depletion
            if self.battery_level <= 0:
                self.battery_level = 0
                self.status = "idle"
                self.next_node = None
                logging.error(f"Robot {self.id} ran out of battery at {self.current_node}.")
                return False

            if self.battery_level > 0:
                self.battery_level -= 2 # Simulate battery drain per move (adjust value as needed)
                if self.path and self.path_index < len(self.path):
                    intended_next_node = self.path[self.path_index]
                    next_node = self.path[self.path_index]
                    current_node = self.current_node
                    lane = tuple(sorted((current_node, next_node)))
                    # Check with TrafficManager if the next lane is free
                    if self.fleet_manager.traffic_manager.request_lane(self.id,current_node,intended_next_node):
                            previous_node = self.current_node
                            self.current_node = intended_next_node
                            self.fleet_manager.moved(self, previous_node) # Still need to notify FleetManager
                            self.intended_next_node = None

                            self.path_index += 1

                            if self.path_index < len(self.path):
                                self.next_node = self.path[self.path_index]
                                return False # Not reached the immediate next target yet
                            else:
                                # Reached the final destination of the current sub-task (either task completion or charging station)
                                self.next_node = None
                                if self.status == "moving":
                                    self.status = "task_complete"
                                    return True # Reached task destination
                                elif self.status == "moving_to_charge" and self.current_node in self.fleet_manager.charging_stations:
                                    self.status = "charging"
                                    self.charging_start_time = time.time()
                                    return True # Reached charging station and started charging
                                elif self.status == "moving_to_charge" and self.current_node not in self.fleet_manager.charging_stations:
                                    # ... safety check ...
                                    self.status = "idle"
                                    return False
                    else:
                        # Cannot move to the next node (lane occupied)
                        self.status = "waiting"
                        self.next_node = self.intended_next_node
                        self.next_node = next_node # Still intends to go here
                        return False

        elif self.status == "charging":
            # Simulate charging for a duration
            if self.charging_start_time is not None and time.time() - self.charging_start_time >= 5:
                self.battery_level = min(self.battery_capacity, self.battery_level + 20) # Charge by a fixed amount
                self.charging_start_time = time.time() # Reset the timer for the next charging interval
                if self.battery_level >= self.battery_capacity:
                    # Fully charged
                    self.battery_level = self.battery_capacity
                    self.status = "idle"
                    self.charging_start_time = None
                    logging.info(f"Robot {self.id} fully charged to {self.battery_level:.2f}, now idle.")
                    if self.fleet_manager and self.current_node in self.fleet_manager.charging_stations:
                        self.fleet_manager.unassign_charging_station(self.id, self.current_node)
                return True # Charging occurred

        elif self.status == "waiting":
            # Check if the lane it was waiting for is now free
            if self.next_node:
                current_node = self.current_node
                if self.fleet_manager.traffic_manager.request_lane(current_node, self.next_node, self.id):
                    # Lane is now free, set status to moving to proceed in the next move() call
                    self.status = "moving"
                    logging.info(f"Robot {self.id} at {current_node} resuming move to {self.next_node} as lane is free.")
            return False 
        
        else:
            self.status = "idle"
            self.next_node = None
            return False # Cannot move if not in a moving or charging state

        return False # Default return if no significant state change

    def get_battery_level(self):
        """Returns the current battery level of the robot."""
        return self.battery_level

    def is_battery_low(self):
        """Checks if the robot's battery level is below the low battery threshold."""
        return self.battery_level <= self.low_battery_threshold

    def charge(self, amount):
        """Manually charges the robot by a given amount, not respecting charging stations."""
        self.battery_level = min(self.battery_capacity, self.battery_level + amount)
        if self.battery_level >= self.low_battery_threshold and self.status == "charging":
            self.status = "idle" # Transition back to idle after manual charge

    def set_fleet_manager(self, fleet_manager):
        """Sets the reference to the FleetManager that controls this robot."""
        self.fleet_manager = fleet_manager