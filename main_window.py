"""
Main window module for BX53/BX53M-P Microscope Viewer
Contains the primary application window and UI layout
"""

import sys
import os
import subprocess
import cv2
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QGroupBox, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QHeaderView, QStatusBar, QProgressBar,
    QFrame, QApplication, QComboBox, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QSize, QRect, pyqtSignal
from PyQt6.QtGui import (
    QFont, QPixmap, QImage, QAction, QColor, QPainter, 
    QIcon, QBrush, QPen, QLinearGradient
)

from config import CONFIG, COLORS, SCALE, MINERAL_PROPERTIES, PLACEHOLDER_CLASSIFICATIONS
from style import setup_stylesheet, MAIN_STYLESHEET, get_button_style
from camera_worker import CameraWorker
from stage_control import StageController
from screen_utils import (
    StatusIndicator, GlassPanel, MetalProgressBar, EnhancedPushButton,
    CameraView, create_header_label, create_info_label, create_status_label,
    format_filename, format_timestamp
)


class MainWindow(QMainWindow):
    """Main application window for microscope viewer."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(CONFIG.APP_TITLE)
        self.setMinimumSize(CONFIG.MIN_WIDTH, CONFIG.MIN_HEIGHT)
        self.setStyleSheet(MAIN_STYLESHEET)

        # ═══ State Variables ═══
        self._current_frame = None
        self._gallery_paths = []
        self._show_crosshair = False
        self._show_scale_bar = False
        self._captures_dir = CONFIG.CAPTURES_DIR
        self._light_mode = "PPL"
        
        # ESP32 state
        self._esp_started = False
        self._esp_paused = False
        self._esp_connected = False
        
        # Initialize stage controller
        self.stage_controller = StageController()
        
        # Initialize camera worker
        self.camera_worker = CameraWorker()
        self.camera_worker.frame_ready.connect(self._on_frame_ready)
        self.camera_worker.fps_updated.connect(self._on_fps_updated)
        self.camera_worker.error_occurred.connect(self._on_camera_error)
        self.camera_worker.connected.connect(self._on_camera_connected)
        
        # Build UI
        self._build_menu()
        self._build_ui()
        self._build_statusbar()

        # Focus score timer
        self._focus_timer = QTimer()
        self._focus_timer.timeout.connect(self._update_focus)
        self._focus_timer.start(CONFIG.FOCUS_UPDATE_INTERVAL)
        
        # Start camera worker
        self.camera_worker.start()

    # ═══════════════════════════════════════════════════════════
    #  MENU BAR
    # ═══════════════════════════════════════════════════════════
    def _build_menu(self):
        """Build application menu bar."""
        mb = self.menuBar()
        
        # File Menu
        file_m = mb.addMenu("📁 File")
        file_m.addAction(self._create_action("📷 Capture Image", "Ctrl+S", self._capture))
        file_m.addAction(self._create_action("📂 Open Captures", "Ctrl+O", self._open_captures))
        file_m.addSeparator()
        file_m.addAction(self._create_action("❌ Exit", "Ctrl+Q", self.close))

        # View Menu
        view_m = mb.addMenu("👁 View")
        view_m.addAction(self._create_action("✚ Crosshair", "Ctrl+H", self._toggle_crosshair))
        view_m.addAction(self._create_action("📏 Scale Bar", "Ctrl+B", self._toggle_scalebar))

        # Camera Menu
        cam_m = mb.addMenu("📹 Camera")
        for i in range(4):
            cam_m.addAction(self._create_action(f"Camera {i}", None, lambda checked, idx=i: None))

    def _create_action(self, text, shortcut, slot):
        """Create a menu action."""
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        return a

    # ═══════════════════════════════════════════════════════════
    #  MAIN UI LAYOUT
    # ═══════════════════════════════════════════════════════════
    def _build_ui(self):
        """Build main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(SCALE.padding_normal, SCALE.padding_normal, 
                                 SCALE.padding_normal, SCALE.padding_normal)
        root.setSpacing(SCALE.padding_normal)

        # ═══ ROW 1: LEFT SIDEBAR + VIDEO FEED + RIGHT SIDEBAR ═══
        main_content = QHBoxLayout()
        main_content.setSpacing(SCALE.padding_normal)

        left_sidebar = self._build_left_sidebar()
        main_content.addWidget(left_sidebar, stretch=1)

        video_panel = self._build_video_panel()
        main_content.addWidget(video_panel, stretch=4)

        right_sidebar = self._build_right_sidebar()
        main_content.addWidget(right_sidebar, stretch=1)

        root.addLayout(main_content, stretch=1)

        # ═══ ROW 2: STAGE CONTROL ═══
        stage_panel = self._build_stage_panel()
        root.addWidget(stage_panel, stretch=0)

    # ═══════════════════════════════════════════════════════════
    #  VIDEO PANEL
    # ═══════════════════════════════════════════════════════════
    def _build_video_panel(self):
        """Build the main video feed display."""
        panel = GlassPanel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(SCALE.padding_normal, SCALE.padding_normal, 
                                   SCALE.padding_normal, SCALE.padding_normal)
        layout.setSpacing(10)

        # ── Header ──
        header = QHBoxLayout()
        
        title = create_header_label("🔬 Live Microscope Feed")
        header.addWidget(title)
        header.addStretch()
        
        self.status_indicator = StatusIndicator("disconnected")
        header.addWidget(self.status_indicator)
        self.status_dot = QLabel("Connecting...")
        self.status_dot.setStyleSheet(f"color: {COLORS.accent_orange}; font-weight: bold; background: transparent;")
        header.addWidget(self.status_dot)

        # Mode Toggle
        self.mode_btn = QPushButton("PPL")
        self.mode_btn.setCheckable(True)
        self.mode_btn.setMinimumHeight(SCALE.button_height_normal)
        self.mode_btn.setMaximumWidth(100)
        self.mode_btn.setToolTip("Toggle PPL/XPL mode")
        self.mode_btn.setStyleSheet(get_button_style("primary"))
        self.mode_btn.clicked.connect(self._toggle_light_mode)
        header.addWidget(self.mode_btn)

        # Capture Button
        self.cap_btn = EnhancedPushButton("📷 Capture", "success")
        self.cap_btn.setMinimumHeight(SCALE.button_height_normal)
        self.cap_btn.setMinimumWidth(160)
        self.cap_btn.clicked.connect(self._capture)
        header.addWidget(self.cap_btn)

        layout.addLayout(header)

        # ── Video Display ──
        self.video_label = CameraView()
        layout.addWidget(self.video_label, stretch=1)

        # ── Footer: Info Bar ──
        footer = QHBoxLayout()
        footer.setSpacing(20)

        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(31, 41, 55, 150);
                border: 1px solid {COLORS.border};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        info_layout = QHBoxLayout(info_frame)
        info_layout.setSpacing(20)
        info_layout.setContentsMargins(SCALE.padding_normal, 6, SCALE.padding_normal, 6)

        self.fps_lbl = create_info_label("📊 FPS: --", COLORS.accent_cyan, bold=True)
        info_layout.addWidget(self.fps_lbl)
        
        self.res_lbl = create_info_label("📐 Resolution: --", COLORS.accent_blue, bold=True)
        info_layout.addWidget(self.res_lbl)
        
        self.focus_lbl = create_info_label("🎯 Focus: -- (--)", COLORS.accent_green, bold=True)
        info_layout.addWidget(self.focus_lbl)

        info_layout.addStretch()
        footer.addWidget(info_frame, stretch=1)

        layout.addLayout(footer)

        return panel

    # ═══════════════════════════════════════════════════════════
    #  LEFT SIDEBAR
    # ═══════════════════════════════════════════════════════════
    def _build_left_sidebar(self):
        """Build left sidebar with point counting and history."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {COLORS.bg_primary}; }}")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SCALE.padding_normal)

        # ── Point Counting ──
        count_group = QGroupBox("📊 Point Counting (1000)")
        count_lay = QVBoxLayout(count_group)
        count_lay.setSpacing(8)

        self.progress_bar = MetalProgressBar()
        self.progress_bar.setRange(0, CONFIG.POINT_COUNT_TARGET)
        self.progress_bar.setValue(0)
        count_lay.addWidget(self.progress_bar)

        self.point_table = QTableWidget(0, 3)
        self.point_table.setHorizontalHeaderLabels(["Mineral", "Count", "%"])
        self.point_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.point_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.point_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.point_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.point_table.setMinimumHeight(150)
        self.point_table.setAlternatingRowColors(True)
        count_lay.addWidget(self.point_table)

        layout.addWidget(count_group)

        # ── Detection History ──
        hist_group = QGroupBox("📜 Detection History")
        hist_lay = QVBoxLayout(hist_group)

        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(150)
        hist_lay.addWidget(self.history_list)

        layout.addWidget(hist_group)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ═══════════════════════════════════════════════════════════
    #  RIGHT SIDEBAR
    # ═══════════════════════════════════════════════════════════
    def _build_right_sidebar(self):
        """Build right sidebar with classification and properties."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {COLORS.bg_primary}; }}")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SCALE.padding_normal)

        # ── Live Classification ──
        cls_group = QGroupBox("🔍 Live Classification")
        cls_lay = QVBoxLayout(cls_group)
        cls_lay.setSpacing(8)

        self.cls_waiting = QLabel("Waiting for analysis...")
        self.cls_waiting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cls_waiting.setStyleSheet(f"color: {COLORS.text_muted}; font-style: italic; background: transparent;")
        cls_lay.addWidget(self.cls_waiting)

        self.cls_bars_widget = QWidget()
        self.cls_bars_layout = QVBoxLayout(self.cls_bars_widget)
        self.cls_bars_layout.setContentsMargins(0, 0, 0, 0)
        self.cls_bars_layout.setSpacing(6)
        self.cls_bars_widget.setVisible(False)
        cls_lay.addWidget(self.cls_bars_widget)

        layout.addWidget(cls_group)

        # ── Stage Position ──
        pos_group = QGroupBox("📍 Stage Position")
        pos_lay = QVBoxLayout(pos_group)
        pos_lay.setSpacing(8)

        self.pos_x_lbl = create_info_label("X: -- mm", COLORS.accent_cyan, bold=True)
        self.pos_y_lbl = create_info_label("Y: -- mm", COLORS.accent_cyan, bold=True)
        self.pos_z_lbl = create_info_label("Z: --°", COLORS.accent_cyan, bold=True)

        for lbl in (self.pos_x_lbl, self.pos_y_lbl, self.pos_z_lbl):
            pos_lay.addWidget(lbl)

        layout.addWidget(pos_group)

        # ── Optical Properties ──
        prop_group = QGroupBox("💎 Optical Properties")
        prop_lay = QVBoxLayout(prop_group)
        prop_lay.setSpacing(6)

        self.prop_mineral_lbl = create_info_label("Mineral: --", COLORS.accent_green, bold=True)
        self.prop_mineral_lbl.setStyleSheet(f"color: {COLORS.accent_green}; font-weight: bold; font-size: 13px; background: transparent;")
        prop_lay.addWidget(self.prop_mineral_lbl)

        self.prop_relief_lbl = create_info_label("Relief: --", COLORS.text_primary)
        self.prop_pleo_lbl = create_info_label("Pleochroism: --", COLORS.text_primary)
        self.prop_biref_lbl = create_info_label("Birefringence: --", COLORS.text_primary)
        self.prop_ext_lbl = create_info_label("Extinction: --", COLORS.text_primary)

        for lbl in (self.prop_relief_lbl, self.prop_pleo_lbl, self.prop_biref_lbl, self.prop_ext_lbl):
            prop_lay.addWidget(lbl)

        layout.addWidget(prop_group)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ═══════════════════════════════════════════════════════════
    #  STAGE CONTROL PANEL
    # ═══════════════════════════════════════════════════════════
    def _build_stage_panel(self):
        """Build stage control panel."""
        panel = GlassPanel()
        layout = QHBoxLayout(panel)
        layout.setSpacing(SCALE.padding_normal)

        # ── System Status ──
        status_frame = QFrame()
        status_frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(31, 41, 55, 100);
                border: 1px solid {COLORS.border};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setSpacing(3)
        
        esp_layout = QHBoxLayout()
        self.esp_indicator = StatusIndicator("disconnected")
        self.esp_status = create_info_label("ESP32: Disconnected", COLORS.accent_orange, bold=True)
        esp_layout.addWidget(self.esp_indicator)
        esp_layout.addWidget(self.esp_status)
        status_layout.addLayout(esp_layout)

        cam_layout = QHBoxLayout()
        self.camera_indicator = StatusIndicator("warning")
        self.camera_status = create_info_label("Camera: Initializing", COLORS.accent_orange, bold=True)
        cam_layout.addWidget(self.camera_indicator)
        cam_layout.addWidget(self.camera_status)
        status_layout.addLayout(cam_layout)

        layout.addWidget(status_frame)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.VLine)
        sep0.setStyleSheet(f"border: 1px solid {COLORS.border};")
        layout.addWidget(sep0)

        # ── Workflow Controls ──
        self.btn_home = EnhancedPushButton("⌂ HOME", "default")
        self.btn_home.setToolTip("Return to home position")
        self.btn_home.clicked.connect(lambda: self.statusBar().showMessage("🔄 Homing motor...", 2000))
        layout.addWidget(self.btn_home)

        self.btn_start = EnhancedPushButton("▶ START", "success")
        self.btn_start.clicked.connect(self._on_stage_start)
        layout.addWidget(self.btn_start)

        self.btn_pause = EnhancedPushButton("⏸ PAUSE", "warning")
        self.btn_pause.clicked.connect(self._on_stage_stop)
        layout.addWidget(self.btn_pause)

        self.btn_done = EnhancedPushButton("✓ DONE", "primary")
        self.btn_done.clicked.connect(self._on_stage_done)
        layout.addWidget(self.btn_done)

        sep00 = QFrame()
        sep00.setFrameShape(QFrame.Shape.VLine)
        sep00.setStyleSheet(f"border: 1px solid {COLORS.border};")
        layout.addWidget(sep00)

        # ── Movement (X/Y) ──
        layout.addWidget(create_info_label("XY Movement:", COLORS.text_primary))
        
        btn_left = EnhancedPushButton("◄", "default")
        btn_left.setMaximumWidth(50)
        btn_left.clicked.connect(lambda: self._on_stage_move("X-"))
        layout.addWidget(btn_left)

        btn_right = EnhancedPushButton("►", "default")
        btn_right.setMaximumWidth(50)
        btn_right.clicked.connect(lambda: self._on_stage_move("X+"))
        layout.addWidget(btn_right)

        btn_down = EnhancedPushButton("▼", "default")
        btn_down.setMaximumWidth(50)
        btn_down.clicked.connect(lambda: self._on_stage_move("Y-"))
        layout.addWidget(btn_down)

        btn_up = EnhancedPushButton("▲", "default")
        btn_up.setMaximumWidth(50)
        btn_up.clicked.connect(lambda: self._on_stage_move("Y+"))
        layout.addWidget(btn_up)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"border: 1px solid {COLORS.border};")
        layout.addWidget(sep1)

        layout.addWidget(create_info_label("Z Rotation:", COLORS.text_primary))

        for angle in CONFIG.STAGE_Z_ANGLES:
            btn = EnhancedPushButton(f"{angle}°", "default")
            btn.setMaximumWidth(65)
            btn.clicked.connect(lambda checked, a=angle: self._on_stage_z_move(a))
            layout.addWidget(btn)

        layout.addStretch()
        return panel

    # ═══════════════════════════════════════════════════════════
    #  HELPER METHODS
    # ═══════════════════════════════════════════════════════════
    def _update_classification_display(self, results):
        """Update confidence bars."""
        while self.cls_bars_layout.count():
            item = self.cls_bars_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not results:
            self.cls_waiting.setVisible(True)
            self.cls_bars_widget.setVisible(False)
            return

        self.cls_waiting.setVisible(False)
        self.cls_bars_widget.setVisible(True)

        rank_colors = [
            COLORS.accent_cyan,
            COLORS.accent_blue,
            COLORS.accent_green,
            COLORS.accent_orange,
            COLORS.text_muted,
        ]

        for idx, entry in enumerate(results[:4]):
            name = entry["name"]
            conf = entry["confidence"]
            color = rank_colors[min(idx, len(rank_colors) - 1)]

            row = QWidget()
            row_lay = QVBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(3)

            header = QHBoxLayout()
            name_lbl = create_info_label(name, COLORS.text_primary, bold=(idx == 0))
            pct_lbl = create_info_label(f"{conf:.1f}%", color, bold=True)
            pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

            header.addWidget(name_lbl)
            header.addStretch()
            header.addWidget(pct_lbl)
            row_lay.addLayout(header)

            bar = MetalProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(conf * 10))
            bar.setFixedHeight(SCALE.progress_bar_height)
            row_lay.addWidget(bar)
            self.cls_bars_layout.addWidget(row)

        self.cls_bars_layout.addStretch()

        # Add to history
        top_mineral = results[0]["name"]
        top_conf = results[0]["confidence"]
        ts = datetime.now().strftime("%H:%M:%S")
        self.history_list.insertItem(0, f"[{ts}] {top_mineral} ({top_conf:.1f}%)")

        # Update point counting
        self._mock_update_point_counting(top_mineral)
        
        # Update optical properties
        self._update_optical_properties(top_mineral)

    def _update_optical_properties(self, mineral):
        """Update optical properties display."""
        props = MINERAL_PROPERTIES.get(mineral, MINERAL_PROPERTIES["Unknown"])
        self.prop_mineral_lbl.setText(f"Mineral: {mineral}")
        self.prop_relief_lbl.setText(f"Relief: {props['relief']}")
        self.prop_pleo_lbl.setText(f"Pleochroism: {props['pleochroism']}")
        self.prop_biref_lbl.setText(f"Birefringence: {props['birefringence']}")
        self.prop_ext_lbl.setText(f"Extinction: {props['extinction']}")

    def _mock_update_point_counting(self, mineral):
        """Update point counting table."""
        row = -1
        for i in range(self.point_table.rowCount()):
            if self.point_table.item(i, 0).text() == mineral:
                row = i
                break

        if row == -1:
            row = self.point_table.rowCount()
            self.point_table.insertRow(row)
            self.point_table.setItem(row, 0, QTableWidgetItem(mineral))
            self.point_table.setItem(row, 1, QTableWidgetItem("1"))
            self.point_table.setItem(row, 2, QTableWidgetItem("100%"))
        else:
            count = int(self.point_table.item(row, 1).text()) + 1
            self.point_table.setItem(row, 1, QTableWidgetItem(str(count)))

        # Recompute percentages
        total = sum([int(self.point_table.item(r, 1).text()) for r in range(self.point_table.rowCount())])
        for r in range(self.point_table.rowCount()):
            c = int(self.point_table.item(r, 1).text())
            pct = (c / total) * 100 if total > 0 else 0
            self.point_table.setItem(r, 2, QTableWidgetItem(f"{pct:.1f}%"))

        self.progress_bar.setValue(total)

    def _update_focus(self):
        """Update focus score display."""
        if self._current_frame is not None:
            gray = cv2.cvtColor(self._current_frame, cv2.COLOR_BGR2GRAY)
            score = cv2.Laplacian(gray, cv2.CV_64F).var()
            q = "Sharp" if score > CONFIG.FOCUS_SHARP_THRESHOLD else "Good" if score > CONFIG.FOCUS_GOOD_THRESHOLD else "Soft"
            c = (
                COLORS.accent_green if score > CONFIG.FOCUS_SHARP_THRESHOLD
                else COLORS.accent_orange if score > CONFIG.FOCUS_GOOD_THRESHOLD
                else COLORS.accent_red
            )
            self.focus_lbl.setText(f"🎯 Focus: {score:.0f} ({q})")
            self.focus_lbl.setStyleSheet(f"color: {c}; font-weight: bold; background: transparent;")

    # ═══════════════════════════════════════════════════════════
    #  CAMERA CALLBACKS
    # ═══════════════════════════════════════════════════════════
    def _on_frame_ready(self, q_img):
        """Handle new frame from camera."""
        self.video_label.setPixmap(QPixmap.fromImage(q_img))

    def _on_fps_updated(self, fps):
        """Handle FPS update."""
        self.fps_lbl.setText(f"📊 FPS: {fps:.1f}")

    def _on_camera_error(self, error_msg):
        """Handle camera error."""
        self.statusBar().showMessage(f"❌ Camera Error: {error_msg}", 5000)

    def _on_camera_connected(self, connected):
        """Handle camera connection status."""
        if connected:
            self.camera_indicator.set_status("connected")
            self.camera_status.setText("Camera: Connected")
            self.camera_status.setStyleSheet(f"color: {COLORS.accent_green}; font-weight: bold; background: transparent;")
        else:
            self.camera_indicator.set_status("disconnected")
            self.camera_status.setText("Camera: Disconnected")
            self.camera_status.setStyleSheet(f"color: {COLORS.accent_red}; font-weight: bold; background: transparent;")

    # ═══════════════════════════════════════════════════════════
    #  ACTIONS
    # ═══════════════════════════════════════════════════════════
    def _capture(self):
        """Capture image."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = format_filename("IMG", suffix=self._light_mode)
        self.statusBar().showMessage(f"✅ Saved: {fname}", 3000)
        self._update_classification_display(PLACEHOLDER_CLASSIFICATIONS)

    def _open_captures(self):
        """Open captures folder."""
        try:
            subprocess.Popen(["xdg-open", str(self._captures_dir)])
        except:
            pass

    def _toggle_crosshair(self):
        self._show_crosshair = not self._show_crosshair
        msg = "✓ Crosshair ON" if self._show_crosshair else "✗ Crosshair OFF"
        self.statusBar().showMessage(msg, 2000)

    def _toggle_scalebar(self):
        self._show_scale_bar = not self._show_scale_bar
        msg = "✓ Scale bar ON" if self._show_scale_bar else "✗ Scale bar OFF"
        self.statusBar().showMessage(msg, 2000)

    def _toggle_light_mode(self):
        """Toggle PPL/XPL mode."""
        if self._light_mode == "PPL":
            self._light_mode = "XPL"
            self.mode_btn.setText("XPL")
            self.mode_btn.setChecked(True)
        else:
            self._light_mode = "PPL"
            self.mode_btn.setText("PPL")
            self.mode_btn.setChecked(False)
        self.statusBar().showMessage(f"💡 Light mode: {self._light_mode}", 2000)

    # ═══════════════════════════════════════════════════════════
    #  STAGE CONTROL
    # ═══════════════════════════════════════════════════════════
    def _on_stage_move(self, direction):
        self.statusBar().showMessage(f"↔️ Moving {direction}...", 1000)

    def _on_stage_z_move(self, angle):
        self.pos_z_lbl.setText(f"Z: {angle}°")
        self.statusBar().showMessage(f"🔄 Rotating to Z={angle}°...", 1000)

    def _on_stage_start(self):
        self._esp_started = True
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.statusBar().showMessage("▶️ Point counting started", 2000)

    def _on_stage_stop(self):
        self._esp_paused = not self._esp_paused
        msg = "⏸️ Paused" if self._esp_paused else "▶️ Resumed"
        self.statusBar().showMessage(msg, 2000)

    def _on_stage_done(self):
        self._esp_started = False
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.statusBar().showMessage("✓ Point counting completed", 2000)

    def _build_statusbar(self):
        """Build status bar."""
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("✅ Ready — BX53/BX53M-P Microscope Viewer | KoPa JX200")

    def closeEvent(self, event):
        """Handle window close event."""
        self.camera_worker.stop()
        event.accept()


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    setup_stylesheet(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
