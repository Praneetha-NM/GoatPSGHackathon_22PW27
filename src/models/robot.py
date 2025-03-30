import time
import uuid
import logging

class Robot:
    def __init__(self, start_node, battery_capacity=100.0, low_battery_threshold=30.0):
        self.id = str(uuid.uuid4())[:8]
        self.current_node = start_node
        self.next_node = None
        self.path = None
        self.path_index = 0
        self.status = "idle"  # idle, moving, waiting, charging, task_complete
        self.destination_node = None
        self.battery_level = battery_capacity
        self.battery_capacity = battery_capacity
        self.low_battery_threshold = low_battery_threshold
        logging.info(f"Robot {self.id} initialized at {start_node} with battery {self.battery_level:.2f}")

    def get_location(self):
        return self.current_node

    def get_next_node(self):
        return self.next_node

    def get_path(self):
        return self.path

    def get_status(self):
        return self.status

    def set_status(self, status):
        self.status = status
        logging.info(f"Robot {self.id} status updated to {status}")

    def set_destination(self, destination_node, path):
        self.destination_node = destination_node
        self.path = path
        self.path_index = 1
        if self.path and len(self.path) > 1:
            self.next_node = self.path[self.path_index]
        elif path and len(path) == 1 and path[0] == self.current_node:
            self.destination_node = destination_node
            self.path = path
            self.path_index = 0
            self.next_node = None
            self.status = "task_complete"
        else:
            self.destination_node = None
            self.path = None
            self.path_index = 0
            self.next_node = None
            if self.status in ["moving", "moving_to_charge"]:
                self.status = "idle" # Revert to idle if no valid path

    def move(self):
        logging.info(f"Robot {self.id}: Current Status: {self.status}, Battery: {self.battery_level:.2f}, Next Node Intent: {self.next_node}") # DEBUG
        if self.status == "waiting":
            print(f"Robot {self.id}: Is in 'waiting' status, returning False.") # DEBUG
            return False
        if self.status == "moving" or self.status == "moving_to_charge":
            if self.battery_level <= 0:
                self.battery_level = 0  # Ensure it doesn't go negative
                self.status = "idle"  # Or "battery_failure"
                self.next_node = None
                logging.error(f"Robot {self.id} ran out of battery at {self.current_node}.")
                
                return False  # Indicate no movement

            if self.battery_level > 0:
                self.battery_level -= 5 # Simulate battery drain (adjust value as needed)
                if self.path and self.path_index < len(self.path):

                    previous_node = self.current_node
                    next_node = self.path[self.path_index]

                    if self.fleet_manager.can_move(self, next_node):
                        # Robot is allowed to move
                        self.current_node = next_node
                        self.fleet_manager.moved(self, previous_node) # Notify lane freed and occupied
                        self.path_index += 1
                        if self.path_index < len(self.path):
                            self.next_node = self.path[self.path_index]
                            return False  # Not reached destination yet
                        else:
                            self.next_node = None
                            if self.status == "moving":
                                self.status = "task_complete"
                                logging.info(f"Robot {self.id} reached destination: {self.destination_node}, status: {self.status}, battery: {self.battery_level:.2f}")
                                return True  # Reached task destination
                            elif self.status == "moving_to_charge":
                                self.status = "charging"
                                self.charging_start_time = time.time()
                                logging.info(f"Robot {self.id} reached charging station {self.destination_node}, status: {self.status}, beginning charging.")
                                return True  # Reached charging station and started charging
                        
                    else:
                        logging.info(f"Robot {self.id}: can_move returned False.") # DEBUG
                        self.status = "waiting"
                        self.next_node = next_node # Still intend to go here
                        logging.info(f"Robot {self.id} waiting to move from {self.current_node} to {self.next_node}.")
                        return False

            elif self.status in ["moving", "moving_to_charge"]:
                self.status = "idle" # Or "battery_failure"
                self.next_node = None
                logging.error(f"Robot {self.id} ran out of battery at {self.current_node}.")
                return True
        elif self.status == "charging":
            if self.charging_start_time is not None and time.time() - self.charging_start_time >= 5:
                self.battery_level =self.battery_level + 20
                logging.info(f"Robot {self.id} charged to {self.battery_level:.2f}.")
                self.charging_start_time = time.time() # Reset the timer for the next 5-second interval
                if self.battery_level >= self.battery_capacity:
                    self.battery_level = self.battery_capacity
                    self.status = "idle"
                    self.charging_start_time = None
                    logging.info(f"Robot {self.id} fully charged to {self.battery_level:.2f}, now idle.")
                    if self.current_node in self.fleet_manager.charging_stations:
                        self.fleet_manager.unassign_charging_station(self.id, self.current_node)
                return True

        else:
            self.status = "idle"
            self.next_node = None
            logging.error(f"Robot {self.id} ran out of battery at {self.current_node}")
            
            return False
        return False
    
    def get_battery_level(self):
        return self.battery_level

    def is_battery_low(self):
        return self.battery_level <= self.low_battery_threshold

    def charge(self, amount):
        self.battery_level = min(self.battery_capacity, self.battery_level + amount)
        if self.battery_level >= self.low_battery_threshold and self.status == "charging":
            self.status = "idle" # Or perhaps "task_complete" if it was on a charging task
    def set_fleet_manager(self, fleet_manager):
        self.fleet_manager = fleet_manager
