import pygame
import sys
import math
import threading
import socket
import time
import random  # Import necessário para seleção aleatória
from enum import Enum

# Initialize Pygame
pygame.init()

# Virus
VIRUS_SIMULATION = True  # Set to False to disable virus simulation

# Set up initial parameters
GRID_ROWS = 20    # Number of grid rows
GRID_COLS = 40    # Number of grid columns
CELL_SIZE = 40    # Size of each cell in pixels

# Calculate the size of the window based on grid size
SCREEN_WIDTH = GRID_COLS * CELL_SIZE
SCREEN_HEIGHT = GRID_ROWS * CELL_SIZE

# Set up the display
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption('Drone Simulation Grid')

# Create the grid matrix initialized with zeros
grid = [[0 for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]

# Colors (RGBA)
WHITE = (255, 255, 255, 128)   # Semi-transparent white
GREEN = (0, 255, 0, 128)       # Semi-transparent green
YELLOW = (255, 255, 0, 128)    # Semi-transparent yellow
PURPLE_CELL = (128, 0, 128, 128)  # Semi-transparent purple for virus-affected cells
GRAY = (200, 200, 200, 128)    # Semi-transparent gray
BLACK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)

# Constants for connection
MAX_CONNECTION_DISTANCE = 250  # Maximum distance for connection
WEAK_SIGNAL_THRESHOLD = 0.9 * MAX_CONNECTION_DISTANCE
STRONG_SIGNAL_THRESHOLD = 0.5 * MAX_CONNECTION_DISTANCE

# Load and scale the background image
background_image = pygame.image.load('background.jpg')  # Certifique-se de que a imagem está no diretório correto
background_image = pygame.transform.scale(background_image, (SCREEN_WIDTH, SCREEN_HEIGHT))

# Drone states
class DroneState(Enum):
    IDLE = 0
    MOVING_TO_TARGET = 1
    SCANNING = 2
    RECONNECTING = 3
    RETURNING_TO_BASE = 4
    LOST_CONNECTION = 5

# Drone class
class Drone:
    MAX_SPEED = 1  # Constant speed when moving
    BASE_PORT = 5000  # Base port number for UDP communication

    def __init__(self, x, y, id):
        self.id = id  # Unique identifier for the drone
        self.x = x  # X-coordinate
        self.y = y  # Y-coordinate
        self.initial_x = x  # Store initial position
        self.initial_y = y
        self.speed_x = 0
        self.speed_y = 0
        self.radius = CELL_SIZE // 6
        self.state = DroneState.IDLE  # Initial state
        self.mission_target = None
        self.wait_frames = 0
        self.connection_status = "connected"
        self.nearby_drones = []  # List of drones within range (drone, distance)
        self.connected_drones = []  # Drones from which we have received pings
        self.last_ping_time = {}  # Last time we received a ping from each drone
        self.ping_interval = 1.0  # Interval between pings in seconds
        self.ping_timeout = 30.0  # Time to wait before considering a connection lost
        self.lock = threading.Lock()  # Lock for thread-safe operations

        # UDP Communication
        self.udp_port = self.BASE_PORT + self.id  # Unique port for each drone
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('localhost', self.udp_port))
        self.udp_socket.settimeout(0.5)  # Non-blocking with timeout

        # Start UDP server thread
        self.running = True
        self.udp_thread = threading.Thread(target=self.listen_for_pings)
        self.udp_thread.daemon = True
        self.udp_thread.start()

        # Timer for sending pings
        self.last_ping_sent = time.time()

    def listen_for_pings(self):
        """Thread function to listen for incoming pings."""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                sender_id = int(data.decode('utf-8'))
                with self.lock:
                    self.last_ping_time[sender_id] = time.time()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Drone {self.id} encountered an error in UDP server: {e}")

    def send_pings(self):
        """Send pings to nearby drones."""
        current_time = time.time()
        if current_time - self.last_ping_sent >= self.ping_interval:
            for drone, distance in self.nearby_drones:
                # Send ping to drone
                message = str(self.id).encode('utf-8')
                try:
                    self.udp_socket.sendto(message, ('localhost', Drone.BASE_PORT + drone.id))
                except Exception as e:
                    print(f"Drone {self.id} failed to send ping to Drone {drone.id}: {e}")
            self.last_ping_sent = current_time

    def check_received_pings(self):
        """Check if pings have been received from nearby drones."""
        current_time = time.time()
        with self.lock:
            # Update connected drones based on received pings
            self.connected_drones = []
            for drone, distance in self.nearby_drones:
                last_time = self.last_ping_time.get(drone.id, None)
                if last_time is not None and current_time - last_time <= self.ping_timeout:
                    self.connected_drones.append((drone, distance))
            # Update connection status
            if self.connected_drones:
                if self.connection_status != "connected":
                    print(f"Drone {self.id} reconectado via ping.")
                self.connection_status = "connected"
            else:
                if self.connection_status != "disconnected":
                    print(f"Drone {self.id} perdeu conexão com todos os drones.")
                self.connection_status = "disconnected"

    def stop(self):
        """Stop the UDP server thread."""
        self.running = False
        self.udp_socket.close()

    def set_mission(self, grid_x, grid_y, grid):
        """Set a new mission for the drone using grid coordinates."""
        if self.connection_status != "connected" or self.state != DroneState.IDLE:
            return  # Do not accept new missions if not connected or not idle

        # Convert grid coordinates to real screen coordinates
        target_x = grid_x * CELL_SIZE + CELL_SIZE // 2
        target_y = grid_y * CELL_SIZE + CELL_SIZE // 2
        self.mission_target = (target_x, target_y)
        self.state = DroneState.MOVING_TO_TARGET
        self.wait_frames = 0

        # Update the grid cell to value 2
        grid[grid_y][grid_x] = 2

    def reset_mission_grid_cell(self, grid):
        """Reset the grid cell to 0 if the drone aborts the mission."""
        if self.mission_target is not None:
            target_x, target_y = self.mission_target
            grid_col = int(target_x // CELL_SIZE)
            grid_row = int(target_y // CELL_SIZE)
            if 0 <= grid_row < GRID_ROWS and 0 <= grid_col < GRID_COLS:
                if grid[grid_row][grid_col] == 2:
                    grid[grid_row][grid_col] = 0

    def find_nearby_drones(self, drones):
        """Find all drones within the connection radius and sort them by distance."""
        nearby_drones = []
        for drone in drones:
            if drone.id == self.id:
                continue  # Skip self
            distance = math.hypot(drone.x - self.x, drone.y - self.y)
            if distance <= MAX_CONNECTION_DISTANCE:
                nearby_drones.append((drone, distance))
        # Sort nearby drones by distance (closest first)
        nearby_drones.sort(key=lambda x: x[1])
        self.nearby_drones = nearby_drones

    def check_connection(self, grid):
        """Check the connection status based on received pings."""
        self.check_received_pings()
        if self.connection_status == "disconnected":
            if self.state != DroneState.RECONNECTING:
                self.reset_mission_grid_cell(grid)
            self.state = DroneState.RECONNECTING  # Try to reconnect
            self.mission_target = None
            self.wait_frames = 0

    def update_mission(self, grid, drones, no_more_missions):
        """Update the drone's movement based on the current state."""
        if self.state == DroneState.IDLE:
            # No mission, maintain connectivity
            # Implement logic to follow drones with missions
            drones_with_missions = [d for d in drones if d.state in [DroneState.MOVING_TO_TARGET, DroneState.SCANNING]]
            if drones_with_missions:
                # Follow the closest drone with a mission
                closest_drone = min(drones_with_missions, key=lambda d: math.hypot(d.x - self.x, d.y - self.y))
                target_x, target_y = closest_drone.x, closest_drone.y
            elif no_more_missions:
                # No more missions, return to initial position
                self.state = DroneState.RETURNING_TO_BASE
                target_x, target_y = self.initial_x, self.initial_y
            else:
                # Stay in place
                self.speed_x, self.speed_y = 0, 0
                return

            distance = math.hypot(target_x - self.x, target_y - self.y)
            if distance < 5:
                # Close enough, stop moving
                self.speed_x, self.speed_y = 0, 0
            else:
                # Move towards the target
                direction_x = (target_x - self.x) / distance
                direction_y = (target_y - self.y) / distance
                self.speed_x = direction_x * self.MAX_SPEED
                self.speed_y = direction_y * self.MAX_SPEED
            return

        elif self.state == DroneState.MOVING_TO_TARGET:
            if self.mission_target is None:
                self.state = DroneState.IDLE
                return
            target_x, target_y = self.mission_target
            distance = math.hypot(target_x - self.x, target_y - self.y)

            if distance < 5:
                # Reached target, start scanning
                self.speed_x, self.speed_y = 0, 0
                self.wait_frames = 60  # Duration of scan
                self.state = DroneState.SCANNING
                return

            # Calculate direction and set speed
            direction_x = (target_x - self.x) / distance
            direction_y = (target_y - self.y) / distance
            self.speed_x = direction_x * self.MAX_SPEED
            self.speed_y = direction_y * self.MAX_SPEED

        elif self.state == DroneState.SCANNING:
            # Stay at position for scanning
            self.speed_x, self.speed_y = 0, 0
            self.wait_frames -= 1
            if self.wait_frames <= 0:
                # Finish scanning, update grid from 2 to 1
                grid_row = int(self.y // CELL_SIZE)
                grid_col = int(self.x // CELL_SIZE)
                if grid[grid_row][grid_col] == 2:
                    grid[grid_row][grid_col] = 1
                self.mission_target = None
                self.state = DroneState.IDLE
            return

        elif self.state == DroneState.RECONNECTING:
            # Move towards the Center of Mass (CM) of all drones excluding self
            cm_x, cm_y = calculate_cm_of_drones_excluding_self(drones, self)
            target_x, target_y = cm_x, cm_y
            distance = math.hypot(target_x - self.x, target_y - self.y)

            if distance < STRONG_SIGNAL_THRESHOLD:
                # Reconnected
                self.connection_status = "connected"
                self.state = DroneState.IDLE
                print(f"Drone {self.id} reconectado.")
                return

            # Move towards CM
            direction_x = (target_x - self.x) / distance
            direction_y = (target_y - self.y) / distance
            self.speed_x = direction_x * self.MAX_SPEED
            self.speed_y = direction_y * self.MAX_SPEED

        elif self.state == DroneState.RETURNING_TO_BASE:
            # Move towards initial position
            target_x, target_y = self.initial_x, self.initial_y
            distance = math.hypot(target_x - self.x, target_y - self.y)
            if distance < 5:
                # Arrived at base
                self.speed_x, self.speed_y = 0, 0
                # Stay in place
            else:
                # Move towards base
                direction_x = (target_x - self.x) / distance
                direction_y = (target_y - self.y) / distance
                self.speed_x = direction_x * self.MAX_SPEED
                self.speed_y = direction_y * self.MAX_SPEED

        elif self.state == DroneState.LOST_CONNECTION:
            # Return to base immediately
            target_x, target_y = self.initial_x, self.initial_y
            distance = math.hypot(target_x - self.x, target_y - self.y)
            if distance < 5:
                self.speed_x, self.speed_y = 0, 0
            else:
                direction_x = (target_x - self.x) / distance
                direction_y = (target_y - self.y) / distance
                self.speed_x = direction_x * self.MAX_SPEED * 1.5  # Faster return
                self.speed_y = direction_y * self.MAX_SPEED * 1.5

    def move(self):
        """Update the drone's position based on its current speed."""
        self.x += self.speed_x
        self.y += self.speed_y

    def render(self, surface):
        """Render the drone on the given surface."""
        # Color based on state
        if self.state == DroneState.RECONNECTING:
            color = BLUE
        elif self.state == DroneState.IDLE:
            color = BLACK
        elif self.state == DroneState.RETURNING_TO_BASE:
            color = WHITE  # Purple for returning to base
        elif self.state == DroneState.LOST_CONNECTION:
            color = RED  # Red for lost connection
        else:
            color = BLACK
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), self.radius)

        # Render connection radius
        pygame.draw.circle(surface, RED, (int(self.x), int(self.y)), int(MAX_CONNECTION_DISTANCE), 1)

    def check_and_send_ping(self):
        """Check for messages and send pings if necessary."""
        self.send_pings()

# Function to calculate the Center of Mass (CM) of drones
def calculate_cm_of_drones(drones):
    total_x = sum(drone.x for drone in drones)
    total_y = sum(drone.y for drone in drones)
    count = len(drones)
    if count == 0:
        return None
    return total_x / count, total_y / count

# Function to calculate the CM of drones excluding a specific drone
def calculate_cm_of_drones_excluding_self(drones, self_drone):
    total_x = sum(drone.x for drone in drones if drone.id != self_drone.id)
    total_y = sum(drone.y for drone in drones if drone.id != self_drone.id)
    count = len(drones) - 1  # Exclude self
    if count == 0:
        # No other drones, return self position
        return self_drone.x, self_drone.y
    return total_x / count, total_y / count

# Function to calculate the CM of grid cells with value 2
def calculate_cm_of_grid_cells_with_value_2(grid):
    positions = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            if grid[row][col] == 2:
                cell_x = col * CELL_SIZE + CELL_SIZE // 2
                cell_y = row * CELL_SIZE + CELL_SIZE // 2
                positions.append((cell_x, cell_y))
    count = len(positions)
    if count == 0:
        return None
    total_x = sum(pos[0] for pos in positions)
    total_y = sum(pos[1] for pos in positions)
    return total_x / count, total_y / count

# Function to check if there are any grid cells with value 0
def no_more_grid_cells_to_visit(grid):
    for row in grid:
        if 0 in row:
            return False
    return True

# Function to simulate the virus
def simulate_virus(grid, last_virus_time):
    current_time = time.time()
    if current_time - last_virus_time >= 5.0:  # Every 5 seconds
        # Choose a random number of cells to infect
        num_cells_to_infect = random.randint(1, 5)  # Infect between 1 and 5 cells
        empty_cells = [(row, col) for row in range(GRID_ROWS) for col in range(GRID_COLS) if grid[row][col] == 0]
        if empty_cells:
            cells_to_infect = random.sample(empty_cells, min(num_cells_to_infect, len(empty_cells)))
            for row, col in cells_to_infect:
                grid[row][col] = 10  # Mark as infected
        last_virus_time = current_time
    return last_virus_time

# Create a list of drones with initial positions
drones = [
    Drone(223, 350, id=1),
    Drone(223, 354, id=2),
    Drone(223, 358, id=3),
    Drone(223, 362, id=4),
    Drone(223, 366, id=5),
    Drone(223, 370, id=6),
    Drone(223, 374, id=7),
    Drone(223, 378, id=8),
    Drone(223, 382, id=9),
    Drone(223, 386, id=10),
]

# Initialize last virus activation time
last_virus_time = time.time()

# Main game loop
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Simulate virus
    if VIRUS_SIMULATION:
        last_virus_time = simulate_virus(grid, last_virus_time)

    # Check if there are no more grid cells to visit
    no_more_missions = no_more_grid_cells_to_visit(grid)

    # Update each drone
    for drone in drones:
        drone.find_nearby_drones(drones)
        drone.check_and_send_ping()  # Send pings and check for responses
        drone.check_connection(grid)  # Update connection status based on pings
        drone.update_mission(grid, drones, no_more_missions)
        drone.move()

    # Calculate CM of drones
    cm_drones = calculate_cm_of_drones(drones)

    # Calculate CM of grid cells with value 2
    cm_grid_2 = calculate_cm_of_grid_cells_with_value_2(grid)

    # Assign missions to drones in IDLE state if there are cells to visit
    if not no_more_missions:
        for drone in drones:
            if drone.state == DroneState.IDLE and drone.connection_status == "connected":
                # Points and weights for weighted average calculation
                points = []
                weights = []

                # Drone's position
                points.append((drone.x, drone.y))
                weights.append(1)  # Weight for drone's position

                # CM of drones
                if cm_drones is not None:
                    points.append(cm_drones)
                    weights.append(1)  # Weight for CM of drones

                # CM of grid cells with value 2
                if cm_grid_2 is not None:
                    points.append(cm_grid_2)
                    weights.append(2)  # Higher weight for CM of cells with value 2

                # Weighted average calculation
                total_weight = sum(weights)
                avg_x = sum(p[0] * w for p, w in zip(points, weights)) / total_weight
                avg_y = sum(p[1] * w for p, w in zip(points, weights)) / total_weight

                # Find the nearest grid cell with value 0 to the calculated point
                target_cell = None
                min_distance = float('inf')
                target_row, target_col = None, None

                for row in range(GRID_ROWS):
                    for col in range(GRID_COLS):
                        if grid[row][col] == 0:
                            cell_x = col * CELL_SIZE + CELL_SIZE // 2
                            cell_y = row * CELL_SIZE + CELL_SIZE // 2
                            distance = math.hypot(avg_x - cell_x, avg_y - cell_y)
                            if distance < min_distance:
                                min_distance = distance
                                target_cell = (cell_x, cell_y)
                                target_row, target_col = row, col

                if target_cell is not None:
                    # Assign mission to the drone
                    drone.set_mission(target_col, target_row, grid)  # Note that we use (col, row)

    # Draw the background image
    screen.blit(background_image, (0, 0))

    # Draw the grid with semi-transparent cells
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell_value = grid[row][col]
            if cell_value != 0:
                # Create a semi-transparent surface for the cell
                cell_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                if cell_value == 1:
                    color = GREEN  # Visited cells
                elif cell_value == 2:
                    color = YELLOW  # Cells assigned to a mission
                elif cell_value == 10:
                    color = PURPLE_CELL  # Virus-affected cells
                else:
                    color = WHITE  # Should not happen
                cell_surface.fill(color)
                screen.blit(cell_surface, (col * CELL_SIZE, row * CELL_SIZE))
            # Draw grid lines
            pygame.draw.rect(screen, GRAY, (col * CELL_SIZE, row * CELL_SIZE, CELL_SIZE, CELL_SIZE), 1)

    # Render drones
    for drone in drones:
        drone.render(screen)

    pygame.display.flip()

# Stop all drone servers
for drone in drones:
    drone.stop()

# Quit Pygame
pygame.quit()
sys.exit()
