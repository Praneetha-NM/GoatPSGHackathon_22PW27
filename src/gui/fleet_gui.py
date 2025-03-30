import logging
import time
import pygame
import random
from src.models.nav_graph import NavigationGraph
from src.controllers.fleet_manager import FleetManager
from src.utils.helpers import find_shortest_path

# Configuration
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
BACKGROUND_COLOR = (220, 220, 220)
VERTEX_COLOR = (50, 50, 50)
VERTEX_RADIUS = 25
LANE_COLOR = (100, 100, 100)
ROBOT_SIZE = 25
ROBOT_BORDER_COLOR = (0, 0, 0)
ROBOT_COLORS = {}
STATUS_COLORS = {
    "idle": (0, 128, 0),
    "moving": (0, 0, 255),
    "waiting": (255, 255, 0),
    "charging": (255, 165, 0),
    "task_complete": (128, 128, 128)
}
ROBOT_SPEED = 2
BUTTON_HEIGHT = 30
BUTTON_WIDTH = 120
BUTTON_COLOR = (150, 150, 150)
BUTTON_TEXT_COLOR = (0, 0, 0)
DASHBOARD_WIDTH = 200
GRAPH_AREA_WIDTH = SCREEN_WIDTH - DASHBOARD_WIDTH
ZOOM_SPEED = 0.1
MIN_ZOOM = 0.5
MAX_ZOOM = 2.0
BATTERY_BAR_HEIGHT = 5
BATTERY_BAR_OFFSET_Y = ROBOT_SIZE // 2 + 5
BATTERY_COLOR_FULL = (0, 255, 0)
BATTERY_COLOR_LOW = (255, 0, 0)
BATTERY_COLOR_MEDIUM = (255, 165, 0)

class FleetGUI:
    """Manages the graphical user interface for the fleet management system."""
    def __init__(self, nav_graph_path):
        """
        Initializes the FleetGUI.

        Args:
            nav_graph_path (str): The path to the navigation graph file.
        """
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Fleet Management System")
        self.nav_graph = NavigationGraph(nav_graph_path)
        self.fleet_manager = FleetManager(self.nav_graph)
        self.fleet_manager.set_gui(self) # Give FleetManager a reference to the GUI
        self.running = True
        self.selected_robot = None
        self.font = pygame.font.Font(None, 20)
        self.robot_sprites = pygame.sprite.Group()
        self.robot_sprites_map = {}
        self.occupied_vertices = {}
        self.logs = []
        self._load_logs()
        self.small_font = pygame.font.Font(None, 14) # For battery percentage and node IDs
        self.spawn_button_rect = pygame.Rect(20, SCREEN_HEIGHT - BUTTON_HEIGHT - 10, BUTTON_WIDTH, BUTTON_HEIGHT)
        self.navigate_button_rect = pygame.Rect(20 + BUTTON_WIDTH + 10, SCREEN_HEIGHT - BUTTON_HEIGHT - 10, BUTTON_WIDTH, BUTTON_HEIGHT)
        self.mode = None
        self.navigation_start_node = None
        self.raw_vertices_positions = {
            node_id: data['pos'] for node_id, data in self.nav_graph.vertices_data.items()
        }
        self.zoom_level = 1.0
        self.graph_offset = pygame.Vector2(GRAPH_AREA_WIDTH // 2, SCREEN_HEIGHT // 2 - BUTTON_HEIGHT * 2//2)
        self.mouse_drag_origin = None
        self._init_robots_sprites()
        self.battery_check_timer = 0
        self.battery_check_interval = 30 # Check every 30 frames (approx. 1 second at 30 FPS)
        self.log_rect = pygame.Rect(GRAPH_AREA_WIDTH + 20, 100, 260, 300)
        self.notification_rect = pygame.Rect(GRAPH_AREA_WIDTH + 20, self.log_rect.bottom + 20, 260, 160)
        self.notification_duration = 5  # seconds
        self.notification_start_time = {}
        self.notifications = []
        self.notification_font = pygame.font.Font(None, 22)

    def _calculate_center(self):
        """Calculates the center of the navigation graph for initial view."""
        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')
        for data in self.nav_graph.vertices_data.values():
            x, y = data['pos']
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
        return (min_x + max_x) / 2, (min_y + max_y) / 2

    def _init_robots_sprites(self):
        """Initializes the robot sprites based on the fleet manager's robots."""
        scaled_positions = self._calculate_scaled_positions()
        for robot_id, robot in self.fleet_manager.get_all_robots().items():
            if robot.get_location() in scaled_positions:
                x, y = scaled_positions[robot.get_location()]
                color = ROBOT_COLORS.get(robot_id, (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
                ROBOT_COLORS[robot_id] = color
                robot_sprite = RobotSprite(robot.get_location(), (x, y), ROBOT_SIZE, color, robot)
                self.robot_sprites.add(robot_sprite)
                self.robot_sprites_map[robot_id] = robot_sprite
                self.occupied_vertices[robot.get_location()] = robot_id

    def show_notification(self, message):
        """Displays a notification message in the GUI."""
        timestamp = time.time()
        self.notifications.append(message)
        self.notification_start_time[message] = timestamp

    def _draw_notifications(self):
        """Draws the notification area and current notifications."""
        pygame.draw.rect(self.screen, (50, 50, 50), self.notification_rect) # Background
        notification_surface = pygame.Surface(self.notification_rect.size)
        notification_surface.fill((50, 50, 50))
        current_time = time.time()
        notifications_to_display = []
        for notification in self.notifications:
            if current_time - self.notification_start_time.get(notification, 0) < self.notification_duration:
                notifications_to_display.append(notification)

        y_offset = 10
        line_height = self.notification_font.get_linesize()
        padding = 5

        for message in reversed(notifications_to_display):
            text_surface = self.notification_font.render(message, True, (255, 255, 0)) # Yellow text
            notification_surface.blit(text_surface, (padding, y_offset))
            y_offset += line_height + padding

        self.screen.blit(notification_surface, self.notification_rect.topleft)

        # Clean up old notifications
        self.notifications = [
            n for n in self.notifications
            if current_time - self.notification_start_time.get(n, 0) < self.notification_duration
        ]

    def _update_robot_sprites(self):
        """Updates the position and appearance of robot sprites."""
        new_occupied = {}
        scaled_positions = self._calculate_scaled_positions()
        for robot_id, robot in self.fleet_manager.get_all_robots().items():
            sprite = self.robot_sprites_map.get(robot_id)
            if sprite:
                if robot.get_status() == "waiting":
                    sprite.color_override = STATUS_COLORS["waiting"] # Indicate waiting visually
                    sprite.target_pos = None # Stop movement
                elif robot.get_status() in ["moving", "moving_to_charge"]:
                    sprite.color_override = None # Revert to normal color
                    next_node = robot.get_next_node()
                    if next_node is not None and next_node in scaled_positions:
                        sprite.set_target(next_node, scaled_positions[next_node])
                elif robot.get_location() in scaled_positions and sprite.target_node is None:
                    sprite.color_override = None
                    sprite.rect.center = scaled_positions[robot.get_location()]

                sprite.update()
                if robot.get_location() is not None:
                    new_occupied[robot.get_location()] = robot.id
        self.occupied_vertices = new_occupied

    def _load_logs(self):
        """Loads log messages from the fleet logs file."""
        try:
            with open('logs/fleet_logs.txt', 'r') as f:
                self.logs = [line.split(' - ')[-1].strip() for line in f.readlines()]
        except FileNotFoundError:
            self.logs = ["Log file not found."]

    def _update_logs(self):
        """Updates the displayed logs with new entries from the log file."""
        try:
            with open('logs/fleet_logs.txt', 'r') as f:
                new_logs = [line.split(' - ')[-1].strip() for line in f.readlines()]
                if len(new_logs) > len(self.logs):
                    self.logs = new_logs
        except FileNotFoundError:
            self.logs = ["Log file not found."]

    def run(self):
        """Runs the main loop of the FleetGUI."""
        clock = pygame.time.Clock()
        while self.running:
            self._handle_events()
            self._update()
            self._draw()
            pygame.display.flip()
            clock.tick(30)
        pygame.quit()

    def _handle_events(self):
        """Handles Pygame events such as mouse clicks."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                # Handle button clicks
                if self.spawn_button_rect.collidepoint(pos):
                    self.mode = 'spawn' # Set mode to spawn robot on next graph click
                    self.selected_robot = None
                    self.navigation_start_node = None
                elif self.navigate_button_rect.collidepoint(pos):
                    self.mode = 'navigate' # Set mode to select a robot and then a destination
                    self.navigation_start_node = None
                # Handle clicks within the graph area
                elif pos[0] < GRAPH_AREA_WIDTH:
                    clicked_vertex = self._check_vertex_click(pos)
                    clicked_robot = self._check_robot_click(pos)
                    # Spawn mode: if a vertex is clicked, spawn a robot there
                    if self.mode == 'spawn' and clicked_vertex is not None:
                        self._spawn_robot_at(clicked_vertex)
                        self.mode = None # Reset mode after spawning
                    # Navigate mode:
                    elif self.mode == 'navigate':
                        # First click: select a robot
                        if self.selected_robot is None and clicked_robot is not None and self.selected_robot_navigable(clicked_robot.robot):
                            self.selected_robot = clicked_robot.robot
                            # Prevent manual navigation if battery is low
                            if self.selected_robot.get_battery_level() < self.fleet_manager.low_battery_threshold_auto_charge:
                                self.show_notification(f"Robot {self.selected_robot.id[:4]} battery low, cannot navigate manually.")
                                self.selected_robot = None
                            else:
                                self.navigation_start_node = self.selected_robot.get_location() # Remember the starting point for navigation
                        # Second click: set the destination for the selected robot
                        elif self.selected_robot and clicked_vertex is not None and clicked_vertex != self.navigation_start_node:
                            start_node = self.selected_robot.get_location()
                            path = find_shortest_path(self.nav_graph.graph, start_node, clicked_vertex)
                            if path and len(path) > 1:
                                u, v = sorted((path[0], path[1]))
                                # Check for traffic before assigning the task
                                if self.fleet_manager.is_lane_occupied(u, v):
                                    self.show_notification(f"Lane between {path[0]} and {path[1]} is occupied.")
                                elif clicked_vertex in self.occupied_vertices:
                                    self.show_notification(f"Destination vertex {clicked_vertex} is occupied.")
                                else:
                                    success = self.fleet_manager.assign_task(self.selected_robot.id, clicked_vertex)
                                    if not success:
                                        self.show_notification("Task assignment failed (likely battery low or blocked).")
                            elif start_node == clicked_vertex:
                                self.show_notification("Robot is already at the destination.")
                            else:
                                self.show_notification("No path to destination.")
                            self.selected_robot = None # Deselect robot after attempting navigation
                            self.mode = None # Reset mode
                            self.navigation_start_node = None
                        # If a vertex is clicked and it's occupied, show a notification
                        elif clicked_vertex is not None and clicked_vertex in self.occupied_vertices:
                            self.show_notification("Destination vertex is occupied.")
                    # If no mode is active, clicking a robot selects it
                    elif clicked_robot is not None:
                        self.selected_robot = clicked_robot.robot
                    # If clicking in the graph area but not on a vertex or robot, deselect everything
                    else:
                        self.selected_robot = None
                        self.mode = None
                        self.navigation_start_node = None
                # If clicking outside the graph area, deselect everything
                else:
                    self.selected_robot = None
                    self.mode = None
                    self.navigation_start_node = None

    def selected_robot_navigable(self, robot):
        """Checks if the selected robot is in a state where it can be manually navigated."""
        return (robot.get_status() == "idle" or robot.get_status() == "task_complete") and \
               robot.get_battery_level() >= self.fleet_manager.low_battery_threshold_auto_charge

    def _spawn_robot_at(self, start_node):
        """Spawns a robot at the clicked vertex if valid."""
        scaled_positions = self._calculate_scaled_positions()
        if start_node is not None and start_node in self.nav_graph.graph.nodes() and start_node not in self.occupied_vertices and start_node in scaled_positions:
            robot = self.fleet_manager.spawn_robot(start_node)
            if robot:
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                ROBOT_COLORS[robot.id] = color
                initial_pos = scaled_positions[robot.get_location()]
                robot_sprite = RobotSprite(robot.get_location(), initial_pos, ROBOT_SIZE, color, robot)
                self.robot_sprites.add(robot_sprite)
                self.robot_sprites_map[robot.id] = robot_sprite
                self.occupied_vertices[start_node] = robot.id
            else:
                self.show_notification("Cannot spawn at this location.")
        elif start_node is not None and start_node in self.occupied_vertices:
            self.show_notification("Vertex is already occupied.")
        elif start_node is not None:
            pass
        else:
            self.show_notification("Invalid spawn location.")

    def _check_vertex_click(self, pos):
        """Checks if a vertex on the graph was clicked."""
        scaled_positions = self._calculate_scaled_positions()
        for node_id, (x, y) in scaled_positions.items():
            if (x - VERTEX_RADIUS <= pos[0] <= x + VERTEX_RADIUS and
                    y - VERTEX_RADIUS <= pos[1] <= y + VERTEX_RADIUS):
                return node_id
        return None

    def _check_robot_click(self, pos):
        """Checks if a robot sprite was clicked."""
        for sprite in self.robot_sprites:
            if sprite.rect.collidepoint(pos):
                return sprite
        return None

    def _update(self):
        """Updates the state of the GUI and the fleet manager."""
        self._update_robot_sprites()
        self._update_logs()
        if self.battery_check_timer >= self.battery_check_interval:
            self.fleet_manager.check_battery_levels()
            self.battery_check_timer = 0
        self.battery_check_timer += 1 # Increment the timer each frame

    def _draw(self):
            """Draws all elements of the GUI."""
            self.screen.fill(BACKGROUND_COLOR)
            self._draw_graph_area()
            self._draw_ui_buttons()
            self._draw_dashboard()
            self._draw_notifications()
            pygame.display.flip()

    def _calculate_scaled_positions(self):
        """Calculates the scaled positions of the graph vertices based on zoom and offset."""
        scaled_positions = {}
        center = self._calculate_center()
        for node_id, raw_pos in self.raw_vertices_positions.items():
            scaled_x = (raw_pos[0] - center[0]) * 50 * self.zoom_level + self.graph_offset.x
            scaled_y = -(raw_pos[1] - center[1]) * 50 * self.zoom_level + self.graph_offset.y
            scaled_positions[node_id] = (int(scaled_x), int(scaled_y))
        return scaled_positions

    def _draw_graph_area(self):
        """Draws the navigation graph, including edges, vertices, and robot sprites."""
        # Draw the background for the graph area
        pygame.draw.rect(self.screen, BACKGROUND_COLOR, (0, 0, GRAPH_AREA_WIDTH, SCREEN_HEIGHT - BUTTON_HEIGHT - 20))
        # Get the scaled positions of all vertices
        scaled_positions = self._calculate_scaled_positions()
        # Draw the lanes (edges) of the navigation graph
        for u, v, _ in self.nav_graph.get_edges():
            if u in scaled_positions and v in scaled_positions:
                start_pos = scaled_positions[u]
                end_pos = scaled_positions[v]
                pygame.draw.line(self.screen, LANE_COLOR, start_pos, end_pos, 2)

        # Draw the vertices of the navigation graph
        for node_id, data in self.nav_graph.get_vertices():
            if node_id in scaled_positions:
                x, y = scaled_positions[node_id]
                color = VERTEX_COLOR
                # Draw the vertex circle
                pygame.draw.circle(self.screen, color, (int(x), int(y)), VERTEX_RADIUS)
                # Render and draw the node ID
                node_id_surface = self.small_font.render(str(node_id), True, (255, 255, 255))
                node_id_rect = node_id_surface.get_rect(center=(int(x), int(y)))
                # If the vertex is a charging station, draw it in a different color
                if data.get('is_charger'):
                    color = (255, 255, 0)
                    pygame.draw.circle(self.screen, color, (int(x), int(y)), VERTEX_RADIUS)
                    node_id_surface = self.small_font.render(str(node_id), True, (0,0,0))
                    node_id_rect = node_id_surface.get_rect(center=(int(x), int(y)))
                self.screen.blit(node_id_surface, node_id_rect)
                # Render and draw the name of the node (if it exists)
                name = data.get('name', '')
                name_surface = self.small_font.render(name, True, (0, 0, 0))
                name_rect = name_surface.get_rect(center=(int(x), int(y) + VERTEX_RADIUS + 10))
                self.screen.blit(name_surface, name_rect)

        # Draw the robot sprites
        for sprite in self.robot_sprites:
            # Draw the robot body
            pygame.draw.rect(self.screen, ROBOT_COLORS[sprite.robot.id], sprite.rect)
            # Draw a border around the robot
            pygame.draw.rect(self.screen, ROBOT_BORDER_COLOR, sprite.rect, 2)
            # Render and draw the first few characters of the robot ID
            robot_id_text = self.font.render(sprite.robot.id[:4], True, (255, 255, 255))
            text_rect = robot_id_text.get_rect(center=sprite.rect.center)
            self.screen.blit(robot_id_text, text_rect)
            # Get the battery level of the robot
            robot = sprite.robot
            battery_level_percent = robot.get_battery_level() / robot.battery_capacity
            # Calculate the width of the battery bar
            bar_width = int(ROBOT_SIZE * 1.5 * battery_level_percent)
            bar_x = sprite.rect.left
            bar_y = sprite.rect.bottom + BATTERY_BAR_OFFSET_Y

            # Determine the color of the battery bar based on the charge level
            if battery_level_percent > 0.6:
                battery_color = BATTERY_COLOR_FULL
            elif battery_level_percent > 0.3:
                battery_color = BATTERY_COLOR_MEDIUM
            else:
                battery_color = BATTERY_COLOR_LOW

            # Draw the background of the battery bar
            pygame.draw.rect(self.screen, (150, 150, 150), (bar_x - 1, bar_y - 1, int(ROBOT_SIZE * 1.5) + 2, BATTERY_BAR_HEIGHT + 2))
            # Draw the actual battery level bar
            pygame.draw.rect(self.screen, battery_color, (bar_x, bar_y, bar_width, BATTERY_BAR_HEIGHT))

            # Render and draw the battery percentage text
            battery_text_surface = self.small_font.render(f"{int(battery_level_percent * 100)}%", True, (0, 0, 0))
            battery_text_rect = battery_text_surface.get_rect(midbottom=(sprite.rect.centerx, bar_y - 2))
            self.screen.blit(battery_text_surface, battery_text_rect)

        # Display information about the selected robot
        if self.selected_robot:
            text = self.font.render(f"Selected: Robot {self.selected_robot.id[:4]}", True, (0, 0, 0))
            self.screen.blit(text, (10, 10))
        # Display the current mode of interaction
        if self.mode:
            mode_text = self.font.render(f"Mode: {self.mode.capitalize()}", True, (0, 0, 0))
            self.screen.blit(mode_text, (10, 30))

    def _draw_ui_buttons(self):
        """Draws the UI buttons for spawning and navigating robots."""
        pygame.draw.rect(self.screen, BUTTON_COLOR, self.spawn_button_rect)
        spawn_text = self.font.render("Spawn Robot", True, BUTTON_TEXT_COLOR)
        spawn_text_rect = spawn_text.get_rect(center=self.spawn_button_rect.center)
        self.screen.blit(spawn_text, spawn_text_rect)

        pygame.draw.rect(self.screen, BUTTON_COLOR, self.navigate_button_rect)
        navigate_text = self.font.render("Navigate Robot", True, BUTTON_TEXT_COLOR)
        navigate_text_rect = navigate_text.get_rect(center=self.navigate_button_rect.center)
        self.screen.blit(navigate_text, navigate_text_rect)

    def _draw_dashboard(self):
        """Draws the dashboard area displaying robot statuses and logs."""
        pygame.draw.rect(self.screen, (240, 240, 240), (GRAPH_AREA_WIDTH, 0, DASHBOARD_WIDTH, SCREEN_HEIGHT))
        y_offset = 20
        dashboard_title = self.font.render("Robot Status", True, (0, 0, 0))
        self.screen.blit(dashboard_title, (GRAPH_AREA_WIDTH + 10, y_offset))
        y_offset += 30
        for robot_id, robot in self.fleet_manager.get_all_robots().items():
            status_text = self.font.render(f"ID: {robot.id[:4]} - {robot.get_status()}", True, (0, 0, 0))
            self.screen.blit(status_text, (GRAPH_AREA_WIDTH + 10, y_offset))
            y_offset += 20

        y_offset += 30
        logs_title = self.font.render("Logs", True, (0, 0, 0))
        self.screen.blit(logs_title, (GRAPH_AREA_WIDTH + 10, y_offset))
        y_offset += 20
        for log_line in self.logs[-10:]: # Display last 10 log lines
            log_text = self.font.render(log_line.strip(), True, (0, 0, 0))
            self.screen.blit(log_text, (GRAPH_AREA_WIDTH + 10, y_offset))
            y_offset += 15

    def _init_robots_sprites(self):
        """Initializes the visual sprites for each robot in the fleet."""
        scaled_positions = self._calculate_scaled_positions()
        for robot_id, robot in self.fleet_manager.get_all_robots().items():
            if robot.get_location() in scaled_positions:
                initial_pos = scaled_positions[robot.get_location()]
                color = ROBOT_COLORS.get(robot_id, (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
                ROBOT_COLORS[robot_id] = color
                robot_sprite = RobotSprite(robot.get_location(), initial_pos, ROBOT_SIZE, color, robot)
                self.robot_sprites.add(robot_sprite)
                self.robot_sprites_map[robot_id] = robot_sprite
                self.occupied_vertices[robot.get_location()] = robot.id

    def _update_robot_sprites(self):
        """Updates the position and visual state of each robot sprite."""
        new_occupied = {}
        scaled_positions = self._calculate_scaled_positions()
        for robot_id, robot in self.fleet_manager.get_all_robots().items():
            sprite = self.robot_sprites_map.get(robot_id)
            if sprite:
                if robot.get_status() == "waiting":
                    sprite.color_override = STATUS_COLORS["waiting"]
                    sprite.target_pos = None
                elif robot.get_status() in ["moving", "moving_to_charge"]:
                    sprite.color_override = None
                    next_node = robot.get_next_node()
                    if next_node in scaled_positions:
                        sprite.set_target(next_node, scaled_positions[next_node])
                elif robot.get_location() in scaled_positions and sprite.target_node is None:
                    sprite.color_override = None
                    sprite.rect.center = scaled_positions[robot.get_location()]
                sprite.update()
                if robot.get_location() is not None:
                    new_occupied[robot.get_location()] = robot.id
        self.occupied_vertices = new_occupied

class RobotSprite(pygame.sprite.Sprite):
    """Visual representation of a robot in the GUI."""
    def __init__(self, start_node, initial_pos, size, color, robot):
        """
        Initializes the RobotSprite.

        Args:
            start_node: The initial node of the robot.
            initial_pos (tuple): The initial (x, y) position on the screen.
            size (int): The size of the robot sprite.
            color (tuple): The color of the robot sprite.
            robot (Robot): The underlying Robot model.
        """
        super().__init__()
        self.image = pygame.Surface([size, size], pygame.SRCALPHA)
        pygame.draw.circle(self.image, color, (size // 2, size // 2), size // 2)
        self.rect = self.image.get_rect(center=initial_pos)
        self.robot = robot
        self.speed = ROBOT_SPEED
        self.current_node = start_node
        self.target_node = None
        self.target_pos = None
        self.color = color
        self.color_override = None

    def set_target(self, target_node, target_pos):
        """Sets the target node and position for the sprite to move towards."""
        self.target_node = target_node
        self.target_pos = target_pos

    def update(self):
        """Updates the sprite's position, moving it towards the target."""
        current_color = self.color_override if self.color_override else self.color
        self.image = pygame.Surface([self.rect.width, self.rect.height], pygame.SRCALPHA)
        pygame.draw.circle(self.image, current_color, (self.rect.width // 2, self.rect.height // 2), self.rect.width // 2)
        pygame.draw.circle(self.image, (0, 0, 0), (self.rect.width // 2, self.rect.height // 2), self.rect.width // 2, 2) # Border
        if self.target_pos:
            dx = self.target_pos[0] - self.rect.centerx
            dy = self.target_pos[1] - self.rect.centery
            distance = (dx ** 2 + dy ** 2) ** 0.5

            if distance > self.speed:
                angle = pygame.math.Vector2(dx, dy).angle_to((1, 0))
                move_x = self.speed * pygame.math.Vector2(1, 0).rotate(-angle)[0]
                move_y = self.speed * pygame.math.Vector2(1, 0).rotate(-angle)[1]
                self.rect.x += move_x
                self.rect.y += move_y
            else:
                self.rect.center = self.target_pos
                self.target_node = None
                self.target_pos = None
                if self.robot.get_status() in ["moving", "moving_to_charge"]:
                    self.robot.move()
        elif self.robot.get_status() in ["charging"]:
            self.robot.move()