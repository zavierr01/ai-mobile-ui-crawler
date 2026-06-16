"""Settings panel widget for mobile-crawler GUI."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from mobile_crawler.infrastructure.user_config_store import UserConfigStore


class SettingsPanel(QWidget):
    """Widget for configuring crawler settings.

    Provides inputs for API keys, system prompt, crawl limits,
    and test credentials. Saves to user_config.db.
    """

    # Signal emitted when settings are saved
    settings_saved = Signal()  # type: ignore

    def __init__(self, config_store: "UserConfigStore", parent=None):
        """Initialize settings panel widget.

        Args:
            config_store: UserConfigStore instance for saving/loading settings
            parent: Parent widget
        """
        super().__init__(parent)
        self._config_store = config_store
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Set up user interface."""
        main_layout = QVBoxLayout(self)

        # Main Tab Widget
        self.tab_widget = QTabWidget()

        # 1. General Tab (Limits, Screen Config)
        self.tab_widget.addTab(self._setup_general_tab(), "General")

        # 2. AI & Agent Tab (Provider keys, DroidRun, parser, prompts, test credentials)
        self.tab_widget.addTab(self._setup_ai_tab(), "AI & Agent")

        # 3. Integrations Tab (Traffic, Video, MobSF)
        self.tab_widget.addTab(self._setup_integrations_tab(), "Integrations")

        main_layout.addWidget(self.tab_widget, 1)

        # Save button in bottom area (stays visible regardless of tab)
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self.save_button = QPushButton("Save Settings")
        self.save_button.setMinimumHeight(40)
        self.save_button.setStyleSheet("font-weight: bold;")
        self.save_button.clicked.connect(self._on_save_clicked)
        save_layout.addWidget(self.save_button)
        main_layout.addLayout(save_layout)

    def _setup_general_tab(self) -> QWidget:
        """Create the General settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # ── Crawl Limits ──────────────────────────────────────────────
        limits_group = QGroupBox("Crawl Limits")
        limits_layout = QVBoxLayout()
        self.limit_button_group = QButtonGroup(self)

        max_steps_layout = QHBoxLayout()
        self.steps_radio = QRadioButton()
        self.steps_radio.setChecked(True)
        self.limit_button_group.addButton(self.steps_radio, 0)
        max_steps_layout.addWidget(self.steps_radio)
        max_steps_layout.addWidget(QLabel("Max Steps:"))
        self.max_steps_input = QSpinBox()
        self.max_steps_input.setRange(1, 10000)
        self.max_steps_input.setValue(100)
        self.max_steps_input.setSingleStep(10)
        max_steps_layout.addWidget(self.max_steps_input)
        max_steps_layout.addStretch()
        limits_layout.addLayout(max_steps_layout)

        max_duration_layout = QHBoxLayout()
        self.duration_radio = QRadioButton()
        self.limit_button_group.addButton(self.duration_radio, 1)
        max_duration_layout.addWidget(self.duration_radio)
        max_duration_layout.addWidget(QLabel("Max Duration (seconds):"))
        self.max_duration_input = QSpinBox()
        self.max_duration_input.setRange(10, 3600)
        self.max_duration_input.setValue(300)
        self.max_duration_input.setSingleStep(30)
        self.max_duration_input.setEnabled(False)
        max_duration_layout.addWidget(self.max_duration_input)
        max_duration_layout.addStretch()
        limits_layout.addLayout(max_duration_layout)

        self.steps_radio.toggled.connect(self._on_limit_type_changed)
        limits_group.setLayout(limits_layout)
        layout.addWidget(limits_group)

        # ── Mode Selector ─────────────────────────────────────────────
        mode_group = QGroupBox("Crawl Mode")
        mode_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        mode_layout = QVBoxLayout()

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self.crawl_mode_combo = QComboBox()
        self.crawl_mode_combo.addItem("🤖  DroidRun AI Agent", "droidrun")
        self.crawl_mode_combo.addItem("🔍  OmniParser Sweep", "omni_sweep")
        self.crawl_mode_combo.setMinimumHeight(32)
        mode_row.addWidget(self.crawl_mode_combo)
        mode_row.addStretch()
        mode_layout.addLayout(mode_row)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # ── DroidRun Settings (visible only when DroidRun selected) ───
        self.droidrun_settings_group = QGroupBox("DroidRun AI Agent Settings")
        self.droidrun_settings_group.setStyleSheet(
            "QGroupBox { border: 1px solid #3a6ea5; border-radius: 4px; margin-top: 6px; }"
            "QGroupBox::title { color: #5b9bd5; }"
        )
        dr_layout = QVBoxLayout()
        dr_layout.setSpacing(8)

        self.enable_droidrun_checkbox = QCheckBox("Enable DroidRun AI Agent")
        self.enable_droidrun_checkbox.setToolTip(
            "Use DroidRun's advanced multi-step planning agent instead of single-shot AI responses"
        )
        dr_layout.addWidget(self.enable_droidrun_checkbox)

        self.droidrun_reasoning_checkbox = QCheckBox("Use Reasoning Mode")
        self.droidrun_reasoning_checkbox.setToolTip(
            "Enable complex planning with ManagerAgent → ExecutorAgent cycles"
        )
        self.droidrun_reasoning_checkbox.setChecked(True)
        dr_layout.addWidget(self.droidrun_reasoning_checkbox)

        dr_cycles_row = QHBoxLayout()
        dr_cycles_row.addWidget(QLabel("Max Planning Cycles:"))
        self.droidrun_max_cycles_input = QSpinBox()
        self.droidrun_max_cycles_input.setRange(1, 20)
        self.droidrun_max_cycles_input.setValue(5)
        dr_cycles_row.addWidget(self.droidrun_max_cycles_input)
        dr_cycles_row.addStretch()
        dr_layout.addLayout(dr_cycles_row)

        self.droidrun_streaming_checkbox = QCheckBox("Enable Streaming Output")
        dr_layout.addWidget(self.droidrun_streaming_checkbox)

        dr_retry_row = QHBoxLayout()
        dr_retry_row.addWidget(QLabel("Agent Retry Count:"))
        self.droidrun_retry_count_input = QSpinBox()
        self.droidrun_retry_count_input.setRange(0, 10)
        self.droidrun_retry_count_input.setValue(2)
        dr_retry_row.addWidget(self.droidrun_retry_count_input)
        dr_retry_row.addStretch()
        dr_layout.addLayout(dr_retry_row)

        parser_mode_row = QHBoxLayout()
        parser_mode_row.addWidget(QLabel("UI Parser Mode:"))
        self.ui_parser_mode_combo = QComboBox()
        self.ui_parser_mode_combo.addItems(["boost", "omniparser", "accessibility"])
        self.ui_parser_mode_combo.setCurrentText("boost")
        self.ui_parser_mode_combo.setToolTip(
            "'boost': accessibility tree first, OmniParser fallback\n"
            "'omniparser': vision-only\n"
            "'accessibility': a11y-only"
        )
        parser_mode_row.addWidget(self.ui_parser_mode_combo)
        parser_mode_row.addStretch()
        dr_layout.addLayout(parser_mode_row)

        objective_label = QLabel("Exploration Objective:")
        objective_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        dr_layout.addWidget(objective_label)
        self.exploration_objective_input = QTextEdit()
        self.exploration_objective_input.setMaximumHeight(90)
        self.exploration_objective_input.setPlaceholderText(
            "Explore the app systematically. Navigate through different screens, "
            "interact with UI elements, and discover the app's functionality."
        )
        dr_layout.addWidget(self.exploration_objective_input)

        self.enable_droidrun_checkbox.toggled.connect(self._on_droidrun_enabled_changed)
        self._on_droidrun_enabled_changed(self.enable_droidrun_checkbox.isChecked())
        self.droidrun_settings_group.setLayout(dr_layout)
        layout.addWidget(self.droidrun_settings_group)

        # ── OmniParser Sweep Settings (visible only when Sweep selected) ──
        self.sweep_settings_group = QGroupBox("OmniParser Sweep Settings")
        self.sweep_settings_group.setStyleSheet(
            "QGroupBox { border: 1px solid #2e7d32; border-radius: 4px; margin-top: 6px; }"
            "QGroupBox::title { color: #66bb6a; }"
        )
        sw_layout = QVBoxLayout()
        sw_layout.setSpacing(8)

        nav_row = QHBoxLayout()
        nav_row.addWidget(QLabel("Navigation Strategy:"))
        self.omni_sweep_mode_combo = QComboBox()
        self.omni_sweep_mode_combo.addItem("Breadth — tap all elements, return each time", "breadth")
        self.omni_sweep_mode_combo.addItem("Depth — follow navigations recursively", "depth")
        nav_row.addWidget(self.omni_sweep_mode_combo)
        nav_row.addStretch()
        sw_layout.addLayout(nav_row)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Box Detection Threshold:"))
        self.omni_threshold_input = QDoubleSpinBox()
        self.omni_threshold_input.setRange(0.01, 0.5)
        self.omni_threshold_input.setSingleStep(0.01)
        self.omni_threshold_input.setDecimals(2)
        self.omni_threshold_input.setValue(0.02)
        self.omni_threshold_input.setToolTip(
            "Lower = more boxes detected (higher recall). Default 0.02."
        )
        threshold_row.addWidget(self.omni_threshold_input)
        threshold_row.addStretch()
        sw_layout.addLayout(threshold_row)

        omni_hint = QLabel(
            "All detected boxes are tapped. Boxes that navigate to the same destination are merged "
            "afterwards. No LLM calls — purely deterministic."
        )
        omni_hint.setWordWrap(True)
        omni_hint.setStyleSheet("color: #888; font-size: 11px;")
        sw_layout.addWidget(omni_hint)

        local_url_row = QHBoxLayout()
        local_url_row.addWidget(QLabel("Local OmniParser URL:"))
        self.omni_local_url_input = QLineEdit()
        self.omni_local_url_input.setPlaceholderText("http://localhost:8000")
        self.omni_local_url_input.setToolTip("URL of the locally running OmniParser server.")
        local_url_row.addWidget(self.omni_local_url_input)
        sw_layout.addLayout(local_url_row)

        self.sweep_settings_group.setLayout(sw_layout)
        layout.addWidget(self.sweep_settings_group)

        # ── Screen Configuration ───────────────────────────────────────
        screen_group = QGroupBox("Screen Configuration")
        screen_layout = QVBoxLayout()
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(QLabel("Exclude Top Bar (pixels):"))
        self.top_bar_height_input = QSpinBox()
        self.top_bar_height_input.setRange(0, 500)
        self.top_bar_height_input.setValue(0)
        self.top_bar_height_input.setToolTip("Exclude the Android status bar. Typically 80-120px.")
        top_bar_layout.addWidget(self.top_bar_height_input)
        top_bar_layout.addStretch()
        screen_layout.addLayout(top_bar_layout)
        screen_group.setLayout(screen_layout)
        layout.addWidget(screen_group)

        self.crawl_mode_combo.currentIndexChanged.connect(self._on_crawl_mode_changed)
        self._on_crawl_mode_changed(self.crawl_mode_combo.currentIndex())

        layout.addStretch()
        return self._wrap_in_scroll_area(tab)

    def _setup_ai_tab(self) -> QWidget:
        """Create the AI / API Keys settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # ── AI Provider Keys ───────────────────────────────────────────
        api_keys_group = QGroupBox("AI Provider API Keys")
        api_keys_group.setToolTip("Used by DroidRun AI Agent mode only.")
        api_layout = QVBoxLayout()
        api_layout.setSpacing(8)

        def _key_row(label_text, placeholder, attr_name):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(160)
            row.addWidget(lbl)
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setPlaceholderText(placeholder)
            row.addWidget(edit)
            setattr(self, attr_name, edit)
            api_layout.addLayout(row)

        _key_row("Gemini API Key:", "AIza…", "gemini_api_key_input")
        _key_row("OpenRouter API Key:", "sk-or-…", "openrouter_api_key_input")
        _key_row("Anthropic API Key:", "sk-ant-…", "anthropic_api_key_input")

        api_note = QLabel("ℹ  API keys are only needed for DroidRun AI Agent mode.")
        api_note.setStyleSheet("color: #888; font-size: 11px; margin-top: 4px;")
        api_layout.addWidget(api_note)
        api_keys_group.setLayout(api_layout)
        layout.addWidget(api_keys_group)

        # ── Test Credentials ───────────────────────────────────────────
        credentials_group = QGroupBox("App Test Credentials")
        cred_layout = QVBoxLayout()
        cred_layout.setSpacing(8)

        def _cred_row(label_text, placeholder, attr_name, is_password=False):
            col = QVBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold;")
            col.addWidget(lbl)
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setMinimumHeight(28)
            if is_password:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            col.addWidget(edit)
            setattr(self, attr_name, edit)
            cred_layout.addLayout(col)

        _cred_row("Test Username:", "username / email", "test_username_input")
        _cred_row("Test Password:", "password", "test_password_input", is_password=True)

        credentials_group.setLayout(cred_layout)
        layout.addWidget(credentials_group)

        # ── Replicate key (OmniParser cloud backend) ───────────────────
        replicate_group = QGroupBox("OmniParser Cloud Backend (optional)")
        rep_layout = QHBoxLayout()
        rep_layout.addWidget(QLabel("Replicate API Key:"))
        self.replicate_api_key_input = QLineEdit()
        self.replicate_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.replicate_api_key_input.setPlaceholderText("Leave blank to use local server")
        rep_layout.addWidget(self.replicate_api_key_input)
        replicate_group.setLayout(rep_layout)
        layout.addWidget(replicate_group)

        layout.addStretch()
        return self._wrap_in_scroll_area(tab)

    def _setup_integrations_tab(self) -> QWidget:
        """Create the Integrations tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Traffic Capture
        traffic_capture_group = QGroupBox("Traffic Capture (PCAPdroid)")
        traffic_capture_layout = QVBoxLayout()
        self.enable_traffic_capture_checkbox = QCheckBox("Enable Traffic Capture")
        traffic_capture_layout.addWidget(self.enable_traffic_capture_checkbox)

        pcap_key_layout = QHBoxLayout()
        pcap_key_label = QLabel("API Key:")
        pcap_key_layout.addWidget(pcap_key_label)
        self.pcapdroid_api_key_input = QLineEdit()
        self.pcapdroid_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pcapdroid_api_key_input.setEnabled(False)
        pcap_key_layout.addWidget(self.pcapdroid_api_key_input)
        traffic_capture_layout.addLayout(pcap_key_layout)

        self.enable_traffic_capture_checkbox.toggled.connect(self._on_traffic_capture_toggled)
        traffic_capture_group.setLayout(traffic_capture_layout)
        layout.addWidget(traffic_capture_group)

        # Video Recording
        video_group = QGroupBox("Video Recording")
        video_layout = QVBoxLayout()
        self.enable_video_recording_checkbox = QCheckBox("Enable Video Recording")
        video_layout.addWidget(self.enable_video_recording_checkbox)
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # MobSF Analysis
        mobsf_group = QGroupBox("MobSF Static Analysis")
        mobsf_layout = QVBoxLayout()
        self.enable_mobsf_analysis_checkbox = QCheckBox("Enable MobSF Analysis")
        mobsf_layout.addWidget(self.enable_mobsf_analysis_checkbox)

        mobsf_url_layout = QHBoxLayout()
        mobsf_url_layout.addWidget(QLabel("API URL:"))
        self.mobsf_api_url_input = QLineEdit()
        self.mobsf_api_url_input.setPlaceholderText("http://localhost:8000")
        self.mobsf_api_url_input.setEnabled(False)
        mobsf_url_layout.addWidget(self.mobsf_api_url_input)
        mobsf_layout.addLayout(mobsf_url_layout)

        self.enable_mobsf_analysis_checkbox.toggled.connect(self._on_mobsf_toggled)
        mobsf_group.setLayout(mobsf_layout)
        layout.addWidget(mobsf_group)

        layout.addStretch()
        return self._wrap_in_scroll_area(tab)

    def _wrap_in_scroll_area(self, widget: QWidget) -> QWidget:
        """Wrap a widget in a QScrollArea for handling small screens."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        return scroll

    def _on_crawl_mode_changed(self, index: int) -> None:
        """Show/hide mode-specific settings groups based on selected crawl mode."""
        is_omni_sweep = self.crawl_mode_combo.itemData(index) == "omni_sweep"
        self.droidrun_settings_group.setVisible(not is_omni_sweep)
        self.sweep_settings_group.setVisible(is_omni_sweep)

    def _on_droidrun_enabled_changed(self, enabled: bool) -> None:
        """Enable/disable DroidRun sub-controls."""
        self.droidrun_reasoning_checkbox.setEnabled(enabled)
        self.droidrun_max_cycles_input.setEnabled(enabled)
        self.droidrun_streaming_checkbox.setEnabled(enabled)
        self.droidrun_retry_count_input.setEnabled(enabled)

    def _on_limit_type_changed(self, checked: bool):
        """Handle limit type radio button toggle.

        Args:
            checked: Whether steps radio is checked
        """
        if checked:
            # Steps is selected
            self.max_steps_input.setEnabled(True)
            self.max_duration_input.setEnabled(False)
        else:
            # Duration is selected
            self.max_steps_input.setEnabled(False)
            self.max_duration_input.setEnabled(True)

    def _on_traffic_capture_toggled(self, checked: bool):
        """Handle traffic capture checkbox toggle.

        Args:
            checked: Whether traffic capture is enabled
        """
        self.pcapdroid_api_key_input.setEnabled(checked)

    def _on_mobsf_toggled(self, checked: bool):
        """Handle MobSF analysis checkbox toggle.

        Args:
            checked: Whether MobSF analysis is enabled
        """
        self.mobsf_api_url_input.setEnabled(checked)

    def _load_settings(self):
        """Load settings from user_config.db."""
        # Load API keys (None if not found or decryption fails)
        gemini_key = self._config_store.get_secret_plaintext("gemini_api_key")
        if gemini_key:
            self.gemini_api_key_input.setText(gemini_key)
        else:
            self.gemini_api_key_input.setText("")  # Clear field if no valid key

        openrouter_key = self._config_store.get_secret_plaintext("openrouter_api_key")
        if openrouter_key:
            self.openrouter_api_key_input.setText(openrouter_key)
        else:
            self.openrouter_api_key_input.setText("")  # Clear field if no valid key

        anthropic_key = self._config_store.get_secret_plaintext("anthropic_api_key")
        if anthropic_key:
            self.anthropic_api_key_input.setText(anthropic_key)
        else:
            self.anthropic_api_key_input.setText("")  # Clear field if no valid key

        # Load crawl limits
        max_steps = self._config_store.get_setting("max_steps", default=100)
        self.max_steps_input.setValue(max_steps)

        max_duration = self._config_store.get_setting("max_duration_seconds", default=300)
        self.max_duration_input.setValue(max_duration)

        # Load crawl mode
        crawl_mode = self._config_store.get_setting("crawl_mode", default="droidrun")
        crawl_mode_index = self.crawl_mode_combo.findData(crawl_mode)
        if crawl_mode_index >= 0:
            self.crawl_mode_combo.setCurrentIndex(crawl_mode_index)
        self._on_crawl_mode_changed(self.crawl_mode_combo.currentIndex())

        omni_sweep_mode = self._config_store.get_setting("omni_sweep_mode", default="breadth")
        omni_sweep_mode_index = self.omni_sweep_mode_combo.findData(omni_sweep_mode)
        if omni_sweep_mode_index >= 0:
            self.omni_sweep_mode_combo.setCurrentIndex(omni_sweep_mode_index)

        omni_threshold = self._config_store.get_setting("omniparser_box_threshold", default=0.02)
        self.omni_threshold_input.setValue(float(omni_threshold))

        omni_local_url = self._config_store.get_setting("omniparser_local_url", default="http://localhost:8000")
        self.omni_local_url_input.setText(omni_local_url)

        # Load screen configuration
        top_bar_height = self._config_store.get_setting("top_bar_height", default=0)
        self.top_bar_height_input.setValue(top_bar_height)

        # Load limit type preference (default to steps)
        limit_type = self._config_store.get_setting("limit_type", default="steps")
        if limit_type == "duration":
            self.duration_radio.setChecked(True)
        else:
            self.steps_radio.setChecked(True)

        # Load test credentials
        test_username = self._config_store.get_setting("test_username", default="")
        self.test_username_input.setText(test_username)

        test_password = self._config_store.get_secret_plaintext("test_password")
        if test_password:
            self.test_password_input.setText(test_password)

        # Load traffic capture settings
        enable_traffic_capture = self._config_store.get_setting("enable_traffic_capture", default=False)
        self.enable_traffic_capture_checkbox.setChecked(enable_traffic_capture)
        self._on_traffic_capture_toggled(enable_traffic_capture)

        pcapdroid_api_key = self._config_store.get_secret_plaintext("pcapdroid_api_key")
        if pcapdroid_api_key:
            self.pcapdroid_api_key_input.setText(pcapdroid_api_key)

        # Load video recording settings
        enable_video_recording = self._config_store.get_setting("enable_video_recording", default=False)
        self.enable_video_recording_checkbox.setChecked(enable_video_recording)

        # Load MobSF settings
        enable_mobsf_analysis = self._config_store.get_setting("enable_mobsf_analysis", default=False)
        self.enable_mobsf_analysis_checkbox.setChecked(enable_mobsf_analysis)
        self._on_mobsf_toggled(enable_mobsf_analysis)

        mobsf_api_url = self._config_store.get_setting("mobsf_api_url", default="http://localhost:8000")
        self.mobsf_api_url_input.setText(mobsf_api_url)

        # Load DroidRun Agent settings
        enable_droidrun = self._config_store.get_setting("use_droidrun_agent", default=True)
        self.enable_droidrun_checkbox.setChecked(enable_droidrun)

        droidrun_reasoning = self._config_store.get_setting("droidrun_reasoning_mode", default=True)
        self.droidrun_reasoning_checkbox.setChecked(droidrun_reasoning)

        droidrun_max_cycles = self._config_store.get_setting("droidrun_max_cycles", default=5)
        self.droidrun_max_cycles_input.setValue(droidrun_max_cycles)

        droidrun_streaming = self._config_store.get_setting("droidrun_streaming", default=False)
        self.droidrun_streaming_checkbox.setChecked(droidrun_streaming)

        droidrun_retry_count = self._config_store.get_setting("droidrun_retry_count", default=2)
        self.droidrun_retry_count_input.setValue(droidrun_retry_count)

        # Load UI parser mode and Replicate API key
        ui_parser_mode = self._config_store.get_setting("ui_parser_mode", default="boost")
        self.ui_parser_mode_combo.setCurrentText(ui_parser_mode)

        replicate_key = self._config_store.get_setting("replicate_api_key", default="")
        if replicate_key:
            self.replicate_api_key_input.setText(replicate_key)

        # Load exploration objective (pre-fill with default if not customized)
        exploration_objective = self._config_store.get_setting("exploration_objective", default="")
        if exploration_objective:
            self.exploration_objective_input.setPlainText(exploration_objective)
        else:
            self.exploration_objective_input.setPlainText(
                "Explore the app systematically. Navigate through different screens, "
                "interact with UI elements, and discover the app's functionality. "
                "Focus on user flows like registration, login, main features, and settings."
            )

    def _on_save_clicked(self):
        """Handle save button click."""
        try:
            # Validate API keys before saving
            gemini_key = self.gemini_api_key_input.text().strip()
            if gemini_key and not self._validate_api_key(gemini_key, "Gemini"):
                return

            openrouter_key = self.openrouter_api_key_input.text().strip()
            if openrouter_key and not self._validate_api_key(openrouter_key, "OpenRouter"):
                return

            anthropic_key = self.anthropic_api_key_input.text().strip()
            if anthropic_key and not self._validate_api_key(anthropic_key, "Anthropic"):
                return

            # Validate MobSF API URL if MobSF is enabled
            if self.enable_mobsf_analysis_checkbox.isChecked():
                mobsf_url = self.mobsf_api_url_input.text().strip()
                if mobsf_url and not self._validate_mobsf_url(mobsf_url):
                    return

            # Save API keys (encrypted)
            if gemini_key:
                self._config_store.set_secret_plaintext("gemini_api_key", gemini_key)
            else:
                self._config_store.delete_secret("gemini_api_key")

            if openrouter_key:
                self._config_store.set_secret_plaintext("openrouter_api_key", openrouter_key)
            else:
                self._config_store.delete_secret("openrouter_api_key")

            if anthropic_key:
                self._config_store.set_secret_plaintext("anthropic_api_key", anthropic_key)
            else:
                self._config_store.delete_secret("anthropic_api_key")

            # Save crawl limits
            self._config_store.set_setting("max_steps", self.max_steps_input.value(), "int")
            self._config_store.set_setting("max_duration_seconds", self.max_duration_input.value(), "int")

            # Save crawl mode
            self._config_store.set_setting("crawl_mode", self.crawl_mode_combo.currentData(), "string")
            self._config_store.set_setting("omni_sweep_mode", self.omni_sweep_mode_combo.currentData(), "string")
            self._config_store.set_setting("omniparser_box_threshold", self.omni_threshold_input.value(), "float")
            omni_local_url = self.omni_local_url_input.text().strip() or "http://localhost:8000"
            self._config_store.set_setting("omniparser_local_url", omni_local_url, "string")

            # Save limit type preference
            limit_type = "steps" if self.steps_radio.isChecked() else "duration"
            self._config_store.set_setting("limit_type", limit_type, "string")

            # Save screen configuration
            self._config_store.set_setting("top_bar_height", self.top_bar_height_input.value(), "int")

            # Save test credentials
            test_username = self.test_username_input.text().strip()
            if test_username:
                self._config_store.set_setting("test_username", test_username, "string")
            else:
                self._config_store.delete_setting("test_username")

            test_password = self.test_password_input.text().strip()
            if test_password:
                self._config_store.set_secret_plaintext("test_password", test_password)
            else:
                self._config_store.delete_secret("test_password")

            # Cleanup old config keys
            self._config_store.delete_setting("test_gmail_account")

            # Save traffic capture settings
            enable_traffic_capture = self.enable_traffic_capture_checkbox.isChecked()
            self._config_store.set_setting("enable_traffic_capture", enable_traffic_capture, "bool")

            pcapdroid_api_key = self.pcapdroid_api_key_input.text().strip()
            if pcapdroid_api_key:
                self._config_store.set_secret_plaintext("pcapdroid_api_key", pcapdroid_api_key)
            else:
                self._config_store.delete_secret("pcapdroid_api_key")

            # Save video recording settings
            enable_video_recording = self.enable_video_recording_checkbox.isChecked()
            self._config_store.set_setting("enable_video_recording", enable_video_recording, "bool")

            # Save MobSF settings
            enable_mobsf_analysis = self.enable_mobsf_analysis_checkbox.isChecked()
            self._config_store.set_setting("enable_mobsf_analysis", enable_mobsf_analysis, "bool")

            mobsf_api_url = self.mobsf_api_url_input.text().strip()
            if mobsf_api_url:
                self._config_store.set_setting("mobsf_api_url", mobsf_api_url, "string")
            else:
                self._config_store.set_setting("mobsf_api_url", "http://localhost:8000", "string")

            # Save DroidRun Agent settings
            enable_droidrun = self.enable_droidrun_checkbox.isChecked()
            self._config_store.set_setting("use_droidrun_agent", enable_droidrun, "bool")

            droidrun_reasoning = self.droidrun_reasoning_checkbox.isChecked()
            self._config_store.set_setting("droidrun_reasoning_mode", droidrun_reasoning, "bool")

            droidrun_max_cycles = self.droidrun_max_cycles_input.value()
            self._config_store.set_setting("droidrun_max_cycles", droidrun_max_cycles, "int")

            droidrun_streaming = self.droidrun_streaming_checkbox.isChecked()
            self._config_store.set_setting("droidrun_streaming", droidrun_streaming, "bool")

            droidrun_retry_count = self.droidrun_retry_count_input.value()
            self._config_store.set_setting("droidrun_retry_count", droidrun_retry_count, "int")

            # Save UI parser mode
            ui_parser_mode = self.ui_parser_mode_combo.currentText()
            self._config_store.set_setting("ui_parser_mode", ui_parser_mode, "string")

            # Save Replicate API key (as regular setting, not secret - for easier debugging)
            replicate_key = self.replicate_api_key_input.text().strip()
            if replicate_key:
                self._config_store.set_setting("replicate_api_key", replicate_key, "string")
            else:
                self._config_store.delete_setting("replicate_api_key")

            # Save exploration objective
            exploration_objective = self.exploration_objective_input.toPlainText().strip()
            if exploration_objective:
                self._config_store.set_setting("exploration_objective", exploration_objective, "string")
            else:
                self._config_store.delete_setting("exploration_objective")

            # Emit signal
            self.settings_saved.emit()

            # Show success message
            QMessageBox.information(self, "Settings Saved", "All settings have been saved successfully.")

        except Exception as e:
            # Show error message
            QMessageBox.critical(self, "Error Saving Settings", f"Failed to save settings: {e}")

    def get_gemini_api_key(self) -> str:
        """Get the current Gemini API key value.

        Returns:
            Current Gemini API key
        """
        return self.gemini_api_key_input.text()

    def get_openrouter_api_key(self) -> str:
        """Get the current OpenRouter API key value.

        Returns:
            Current OpenRouter API key
        """
        return self.openrouter_api_key_input.text()

    def get_anthropic_api_key(self) -> str:
        """Get the current Anthropic API key value.

        Returns:
            Current Anthropic API key
        """
        return self.anthropic_api_key_input.text()

    def get_max_steps(self) -> int:
        """Get the current max steps value.

        Returns:
            Current max steps
        """
        return self.max_steps_input.value()

    def get_max_duration(self) -> int:
        """Get the current max duration value.

        Returns:
            Current max duration in seconds
        """
        return self.max_duration_input.value()

    def get_limit_mode(self) -> str:
        """Get the current limit mode (steps or duration).

        Returns:
            'steps' or 'duration'
        """
        return "steps" if self.steps_radio.isChecked() else "duration"

    def get_top_bar_height(self) -> int:
        """Get the current top bar height value.

        Returns:
            Current top bar height in pixels
        """
        return self.top_bar_height_input.value()

    def get_test_username(self) -> str:
        """Get the current test username value.

        Returns:
            Current test username
        """
        return self.test_username_input.text()

    def get_test_password(self) -> str:
        """Get the current test password value."""
        return self.test_password_input.text()

    def get_enable_traffic_capture(self) -> bool:
        """Get the current traffic capture enabled state.

        Returns:
            True if traffic capture is enabled
        """
        return self.enable_traffic_capture_checkbox.isChecked()

    def get_enable_video_recording(self) -> bool:
        """Get the current video recording enabled state.

        Returns:
            True if video recording is enabled
        """
        return self.enable_video_recording_checkbox.isChecked()

    def get_enable_mobsf_analysis(self) -> bool:
        """Get the current MobSF analysis enabled state.

        Returns:
            True if MobSF analysis is enabled
        """
        return self.enable_mobsf_analysis_checkbox.isChecked()

    def get_enable_droidrun_agent(self) -> bool:
        """Get the current DroidRun agent enabled state.

        Returns:
            True if DroidRun agent is enabled
        """
        return self.enable_droidrun_checkbox.isChecked()

    def get_exploration_objective(self) -> str:
        """Get the current exploration objective / prompt for DroidRun.

        Returns:
            Current exploration objective text (empty string if not set)
        """
        return self.exploration_objective_input.toPlainText().strip()

    def get_ui_parser_mode(self) -> str:
        """Get the current UI parser mode.

        Returns:
            UI parser mode: "boost", "omniparser", or "accessibility"
        """
        return self.ui_parser_mode_combo.currentText()

    def get_replicate_api_key(self) -> str:
        """Get the current Replicate API key.

        Returns:
            Replicate API key
        """
        return self.replicate_api_key_input.text().strip()

    def get_pcapdroid_api_key(self) -> str:
        """Get the current PCAPdroid API key.

        Returns:
            PCAPdroid API key
        """
        return self.pcapdroid_api_key_input.text().strip()

    def get_mobsf_api_url(self) -> str:
        """Get the current MobSF API URL.

        Returns:
            MobSF API URL
        """
        return self.mobsf_api_url_input.text().strip()

    def reset(self):
        """Reset all settings to default values."""
        self.gemini_api_key_input.clear()
        self.openrouter_api_key_input.clear()
        self.anthropic_api_key_input.clear()
        self.replicate_api_key_input.clear()
        self.max_steps_input.setValue(100)
        self.max_duration_input.setValue(300)
        self.crawl_mode_combo.setCurrentIndex(self.crawl_mode_combo.findData("droidrun"))
        self.omni_sweep_mode_combo.setCurrentIndex(self.omni_sweep_mode_combo.findData("breadth"))
        self.test_username_input.clear()
        self.test_password_input.clear()
        self.ui_parser_mode_combo.setCurrentText("boost")

    def _validate_api_key(self, api_key: str, provider_name: str) -> bool:
        """Validate API key format and optionally test connectivity.

        Args:
            api_key: The API key to validate
            provider_name: Name of the provider for error messages

        Returns:
            True if valid, False otherwise
        """
        # Basic format validation
        if len(api_key) < 20:
            QMessageBox.warning(
                self,
                f"Invalid {provider_name} API Key",
                f"The {provider_name} API key appears to be too short.\n\n"
                f"Please check that you have entered a valid API key.",
            )
            return False

        if not api_key.startswith(("sk-", "AIza", "pk-")) and provider_name != "OpenRouter":
            # Allow more flexible validation for OpenRouter
            if len(api_key) < 30:
                QMessageBox.warning(
                    self,
                    f"Invalid {provider_name} API Key",
                    f"The {provider_name} API key format appears invalid.\n\n"
                    f"Please check that you have entered a valid API key.",
                )
                return False

        # For more thorough validation, we could make a test API call here
        # But for now, basic format validation is sufficient

        return True

    def _validate_mobsf_url(self, url: str) -> bool:
        """Validate MobSF API URL format.

        Args:
            url: The URL to validate

        Returns:
            True if valid, False otherwise
        """
        if not url:
            QMessageBox.warning(
                self, "Invalid MobSF API URL", "MobSF API URL cannot be empty when MobSF analysis is enabled."
            )
            return False

        # Basic URL format validation
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(
                self,
                "Invalid MobSF API URL",
                "MobSF API URL must start with http:// or https://\n\nExample: http://localhost:8000",
            )
            return False

        # Check for basic URL structure
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if not parsed.netloc:
                QMessageBox.warning(
                    self,
                    "Invalid MobSF API URL",
                    "MobSF API URL appears to be malformed.\n\nExample: http://localhost:8000",
                )
                return False
        except Exception:
            QMessageBox.warning(
                self,
                "Invalid MobSF API URL",
                "MobSF API URL appears to be malformed.\n\nExample: http://localhost:8000",
            )
            return False

        return True
