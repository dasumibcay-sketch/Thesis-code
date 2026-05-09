"""
Screen utilities and custom widgets for BX53/BX53M-P Microscope Viewer
Provides reusable UI components and helper functions
"""

from PyQt6.QtWidgets import (
    QWidget, QLabel, QProgressBar, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QColor, QPainter, QFont, QCursor

from config import COLORS, SCALE
from style import get_button_style, get_progress_bar_style, get_glass_panel_style


class StatusIndicator(QWidget):
    """
    Custom status indicator with animated pulse effect.
    
    States: 'connected', 'warning', 'disconnected'
    """
    
    def __init__(self, status="disconnected", parent=None):
        super().__init__(parent)
        self.status = status
        self.pulse_opacity = 0.5
        self.setFixedSize(SCALE.status_indicator_size, SCALE.status_indicator_size)
        
        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_pulse)
        self.timer.start(50)
    
    def set_status(self, status):
        """Set indicator status."""
        self.status = status
        self.update()
    
    def _get_color(self):
        """Get color based on status."""
        if self.status == "connected":
            return COLORS.status_connected
        elif self.status == "warning":
            return COLORS.status_warning
        else:
            return COLORS.status_error
    
    def _update_pulse(self):
        """Update pulse animation."""
        self.pulse_opacity += 0.05
        if self.pulse_opacity > 1.0:
            self.pulse_opacity = 0.3
        self.update()
    
    def paintEvent(self, event):
        """Paint the indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Outer pulse ring
        color = QColor(self._get_color())
        color.setAlpha(int(100 * self.pulse_opacity))
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, SCALE.status_indicator_size, SCALE.status_indicator_size)
        
        # Inner solid circle
        inner_color = QColor(self._get_color())
        painter.setBrush(inner_color)
        painter.drawEllipse(3, 3, 10, 10)


class GlassPanel(QFrame):
    """Glass-morphism panel effect."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(get_glass_panel_style())


class MetalProgressBar(QProgressBar):
    """3D metallic progress bar."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(get_progress_bar_style())


class EnhancedPushButton(QPushButton):
    """
    Enhanced button with hover effects and icon support.
    
    style_type: 'default', 'primary', 'success', 'warning', 'danger'
    """
    
    def __init__(self, text="", style_type="default", parent=None):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(SCALE.button_height_normal)
        self.style_type = style_type
        self._setup_style()
    
    def _setup_style(self):
        """Apply button styling."""
        self.setStyleSheet(get_button_style(self.style_type))
    
    def set_style(self, style_type):
        """Change button style."""
        self.style_type = style_type
        self._setup_style()


class CameraView(QLabel):
    """
    Enhanced camera view with overlay information.
    Displays live video feed from camera.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(SCALE.video_min_width, SCALE.video_min_height)
        self.show_info = True
        self.focus_score = 0
        self.fps = 0
        
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS.bg_secondary};
                border: 3px solid {COLORS.border};
                border-radius: {SCALE.radius}px;
            }}
        """)
    
    def set_info(self, fps, focus_score):
        """Update displayed information."""
        self.fps = fps
        self.focus_score = focus_score


class InfoBar(QFrame):
    """Information display bar for status updates."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(31, 41, 55, 150);
                border: 1px solid {COLORS.border};
                border-radius: 6px;
                padding: 8px;
            }}
        """)


class StatisticsPanel(QFrame):
    """Panel for displaying statistics and metrics."""
    
    def __init__(self, title="Statistics", parent=None):
        super().__init__(parent)
        self.title = title
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(31, 41, 55, 100);
                border: 1px solid {COLORS.border};
                border-radius: {SCALE.radius}px;
                padding: 12px;
            }}
        """)
    
    def add_stat(self, label_text, value_text="--"):
        """Add a statistic line (to be implemented in subclasses)."""
        pass


def create_header_label(text, font_size=SCALE.font_header):
    """Create a styled header label."""
    label = QLabel(text)
    label.setFont(QFont("DejaVu Sans", font_size, QFont.Weight.Bold))
    label.setStyleSheet(f"color: {COLORS.accent_cyan}; background: transparent;")
    return label


def create_info_label(text, color=COLORS.text_primary, bold=False):
    """Create a styled info label."""
    label = QLabel(text)
    weight = "bold" if bold else "normal"
    label.setStyleSheet(f"color: {color}; font-weight: {weight}; background: transparent;")
    return label


def create_status_label(status="disconnected"):
    """
    Create a status label with indicator.
    
    Args:
        status: 'connected', 'warning', 'disconnected'
    
    Returns:
        tuple: (StatusIndicator, QLabel)
    """
    indicator = StatusIndicator(status)
    
    status_map = {
        "connected": ("Connected", COLORS.accent_green),
        "warning": ("Connecting...", COLORS.accent_orange),
        "disconnected": ("Disconnected", COLORS.accent_red)
    }
    
    text, color = status_map.get(status, status_map["disconnected"])
    label = QLabel(text)
    label.setStyleSheet(f"color: {color}; font-weight: bold; background: transparent;")
    
    return indicator, label


def apply_hover_effect(widget, normal_color, hover_color):
    """Apply hover effect styling to a widget."""
    stylesheet = f"""
        {widget.__class__.__name__} {{
            background-color: {normal_color};
        }}
        {widget.__class__.__name__}:hover {{
            background-color: {hover_color};
        }}
    """
    widget.setStyleSheet(stylesheet)


def format_timestamp(dt):
    """Format datetime to display string."""
    return dt.strftime("%H:%M:%S")


def format_filename(base_name, timestamp=None, suffix=""):
    """
    Format a filename with timestamp.
    
    Args:
        base_name: Base filename without extension
        timestamp: datetime object or None for current time
        suffix: Optional suffix to add
    
    Returns:
        str: Formatted filename with .png extension
    """
    from datetime import datetime
    
    if timestamp is None:
        timestamp = datetime.now()
    
    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    
    if suffix:
        return f"{base_name}_{ts_str}_{suffix}.png"
    else:
        return f"{base_name}_{ts_str}.png"
