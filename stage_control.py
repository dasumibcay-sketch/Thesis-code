"""
Stage control module for BX53/BX53M-P Microscope Viewer
Handles motorized stage movement and Z-rotation
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable

from config import CONFIG

logger = logging.getLogger(__name__)


class StageDirection(Enum):
    """Enumeration for stage movement directions."""
    X_POSITIVE = "X+"
    X_NEGATIVE = "X-"
    Y_POSITIVE = "Y+"
    Y_NEGATIVE = "Y-"
    Z_CLOCKWISE = "Z_CW"
    Z_COUNTERCLOCKWISE = "Z_CCW"


@dataclass
class StagePosition:
    """Data class for stage position."""
    x: float = 0.0  # mm
    y: float = 0.0  # mm
    z: float = 0.0  # degrees


class StageController:
    """
    Controller for motorized microscope stage.
    
    Manages movement in X, Y axes and rotation in Z axis.
    Communicates with ESP32 microcontroller via serial connection.
    """
    
    def __init__(self, port=CONFIG.ESP32_PORT, baudrate=CONFIG.ESP32_BAUDRATE):
        """
        Initialize stage controller.
        
        Args:
            port: Serial port for ESP32 communication
            baudrate: Serial communication baudrate
        """
        self.port = port
        self.baudrate = baudrate
        self.is_connected = False
        self.current_position = StagePosition()
        self.is_moving = False
        
        # Status callback
        self._status_callback: Optional[Callable] = None
        
        # Movement limits
        self.x_min = -100.0  # mm
        self.x_max = 100.0   # mm
        self.y_min = -100.0  # mm
        self.y_max = 100.0   # mm
        self.z_angles = [0, 45, 60, 90]  # Available Z angles
        
        # Serial connection (lazy loaded)
        self.serial_conn = None
    
    def connect(self) -> bool:
        """
        Establish connection to ESP32 microcontroller.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import serial
            self.serial_conn = serial.Serial(
                self.port,
                self.baudrate,
                timeout=CONFIG.ESP32_TIMEOUT
            )
            self.is_connected = True
            logger.info(f"Connected to ESP32 on {self.port}")
            self._emit_status("ESP32", "connected")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ESP32: {str(e)}")
            self._emit_status("ESP32", "error")
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from ESP32 microcontroller.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.serial_conn:
                self.serial_conn.close()
            self.is_connected = False
            logger.info("Disconnected from ESP32")
            self._emit_status("ESP32", "disconnected")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from ESP32: {str(e)}")
            return False
    
    def home(self) -> bool:
        """
        Move stage to home position (0, 0, 0).
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._send_command("HOME")
            self.current_position = StagePosition(0.0, 0.0, 0.0)
            logger.info("Stage moved to home position")
            return True
        except Exception as e:
            logger.error(f"Home command failed: {str(e)}")
            return False
    
    def move_x(self, distance: float) -> bool:
        """
        Move stage in X direction.
        
        Args:
            distance: Distance in mm (positive = right, negative = left)
        
        Returns:
            bool: True if successful, False otherwise
        """
        return self._move(StageDirection.X_POSITIVE if distance > 0 else StageDirection.X_NEGATIVE, abs(distance))
    
    def move_y(self, distance: float) -> bool:
        """
        Move stage in Y direction.
        
        Args:
            distance: Distance in mm (positive = up, negative = down)
        
        Returns:
            bool: True if successful, False otherwise
        """
        return self._move(StageDirection.Y_POSITIVE if distance > 0 else StageDirection.Y_NEGATIVE, abs(distance))
    
    def rotate_z(self, angle: float) -> bool:
        """
        Rotate stage to specific Z angle.
        
        Args:
            angle: Target angle in degrees
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if angle not in self.z_angles:
                logger.warning(f"Angle {angle} not in available angles {self.z_angles}")
                return False
            
            self._send_command(f"Z_{int(angle)}")
            self.current_position.z = angle
            logger.info(f"Stage rotated to Z={angle}°")
            return True
        except Exception as e:
            logger.error(f"Z rotation failed: {str(e)}")
            return False
    
    def _move(self, direction: StageDirection, distance: float) -> bool:
        """
        Internal method to move stage.
        
        Args:
            direction: Direction to move
            distance: Distance to move
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate distance
            if distance > CONFIG.STAGE_X_STEP * 100:  # Sanity check
                logger.warning(f"Movement distance {distance} exceeds safe limit")
                return False
            
            self.is_moving = True
            command = f"MOVE_{direction.value}_{distance:.2f}"
            self._send_command(command)
            
            # Update position
            if "X+" in direction.value:
                self.current_position.x += distance
            elif "X-" in direction.value:
                self.current_position.x -= distance
            elif "Y+" in direction.value:
                self.current_position.y += distance
            elif "Y-" in direction.value:
                self.current_position.y -= distance
            
            # Clamp to limits
            self.current_position.x = max(self.x_min, min(self.x_max, self.current_position.x))
            self.current_position.y = max(self.y_min, min(self.y_max, self.current_position.y))
            
            logger.debug(f"Stage position: X={self.current_position.x:.2f}, Y={self.current_position.y:.2f}")
            self.is_moving = False
            return True
        except Exception as e:
            logger.error(f"Movement failed: {str(e)}")
            self.is_moving = False
            return False
    
    def _send_command(self, command: str) -> bool:
        """
        Send command to ESP32.
        
        Args:
            command: Command string to send
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.is_connected or not self.serial_conn:
                logger.error("Not connected to ESP32")
                return False
            
            self.serial_conn.write((command + "\n").encode())
            response = self.serial_conn.readline().decode().strip()
            
            if response == "OK":
                logger.debug(f"Command sent: {command}")
                return True
            else:
                logger.warning(f"Unexpected response: {response}")
                return False
        except Exception as e:
            logger.error(f"Failed to send command: {str(e)}")
            return False
    
    def get_position(self) -> StagePosition:
        """
        Get current stage position.
        
        Returns:
            StagePosition: Current position
        """
        return self.current_position
    
    def set_position_callback(self, callback: Callable[[StagePosition], None]):
        """
        Set callback function for position updates.
        
        Args:
            callback: Function to call with StagePosition
        """
        self.position_callback = callback
    
    def set_status_callback(self, callback: Callable[[str, str], None]):
        """
        Set callback function for status updates.
        
        Args:
            callback: Function to call with (component, status)
        """
        self._status_callback = callback
    
    def _emit_status(self, component: str, status: str):
        """Emit status update to callback."""
        if self._status_callback:
            self._status_callback(component, status)


class AutoStageController(StageController):
    """Extended stage controller with automatic scanning capabilities."""
    
    def __init__(self, port=CONFIG.ESP32_PORT, baudrate=CONFIG.ESP32_BAUDRATE):
        super().__init__(port, baudrate)
        self.is_scanning = False
        self.scan_grid = []
        self.current_scan_index = 0
    
    def start_grid_scan(self, x_range: tuple, y_range: tuple, step: float) -> bool:
        """
        Start automatic grid scanning.
        
        Args:
            x_range: (x_min, x_max) tuple
            y_range: (y_min, y_max) tuple
            step: Step size in mm
        
        Returns:
            bool: True if successful
        """
        try:
            self.scan_grid = []
            for x in range(int(x_range[0]), int(x_range[1]) + 1, int(step)):
                for y in range(int(y_range[0]), int(y_range[1]) + 1, int(step)):
                    self.scan_grid.append((x, y))
            
            self.is_scanning = True
            self.current_scan_index = 0
            logger.info(f"Starting grid scan with {len(self.scan_grid)} points")
            return True
        except Exception as e:
            logger.error(f"Grid scan setup failed: {str(e)}")
            return False
    
    def next_scan_point(self) -> bool:
        """Move to next scanning point."""
        if not self.is_scanning or self.current_scan_index >= len(self.scan_grid):
            self.is_scanning = False
            return False
        
        x, y = self.scan_grid[self.current_scan_index]
        self.current_scan_index += 1
        
        # Move to point (simplified)
        logger.info(f"Moving to scan point {self.current_scan_index}/{len(self.scan_grid)}: ({x}, {y})")
        return True
    
    def stop_scan(self) -> bool:
        """Stop automatic scanning."""
        self.is_scanning = False
        logger.info("Scan stopped")
        return True
