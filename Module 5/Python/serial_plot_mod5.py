"""Read the PWM_Serial_Control sketch's serial output, plot temperature,
PWM, direction, setpoint, and error vs. time, and send PWM/direction
commands back to the Arduino - either by hand (Manual mode, identical to
Module 4) or from a proportional-only (P) closed-loop controller.

Incoming lines from the Arduino are expected in the form (same sketch,
unchanged from Module 4):
    Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1, Cutoff: 0

Outgoing commands sent TO the Arduino look like:
    SET PWM 120 DIR HEAT
    SET PWM 45 DIR COOL

The Arduino itself does not change from Module 4: it still averages about
1000 raw thermistor-voltage samples per loop before converting that average
to a temperature, still parses "SET PWM ... DIR ..." commands, still drives
the H-bridge, and still enforces its own independent over-temperature
cutoff no matter what this script asks for.

Two control modes are available from the GUI:
  - Manual: pick a PWM value and direction by hand, exactly like Module 4.
  - P Control: every time a new (already 1000-sample-averaged) temperature
    arrives from the Arduino, this script computes
        e = Tset - T
        u = Kp * e
    turns the sign of u into a direction (u >= 0 -> HEAT, u < 0 -> COOL)
    and |u| (rounded to the nearest integer, clamped to 0-255) into a PWM
    magnitude, and sends that direction/magnitude pair to the Arduino as
    one "SET PWM ... DIR ..." command, same as Manual mode would.

Start Kp small (see DEFAULT_KP below) and increase it gradually - a gain
that's too large will slam the PWM to its clamped extremes and can make
the temperature oscillate or overshoot well past the setpoint.
"""

import csv
from pathlib import Path
import re
import sys

import serial
import serial.tools.list_ports
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERIAL_PORT = "/dev/cu.usbserial-10"  # e.g. "/dev/tty.usbmodem1101"; None = auto-detect
BAUD_RATE = 9600

STRIP_CHART_WINDOW_S = 60.0  # seconds of history visible on the plots
PLOT_UPDATE_INTERVAL_MS = 100  # how often the plots redraw

TEMPERATURE_AXIS_MIN_C = 0.0
TEMPERATURE_AXIS_MAX_C = 50.0
TEMPERATURE_AXIS_MARGIN_C = 1.0
MIN_TEMPERATURE_AXIS_SPAN_C = 6.0

PWM_MIN = 0
PWM_MAX = 255

# P-control defaults. Kp is in PWM counts per degree C of error - e.g. with
# the default Kp below, a 10 C error commands a PWM magnitude of only 10,
# which is small next to Module 4's useful PWM ranges (up to 45 heating, up
# to 115 cooling). That's intentional: start small, watch how the system
# responds, and only raise Kp once you've seen it behave (no sustained
# oscillation, no slamming into 0/255) at the current value.
DEFAULT_SETPOINT_C = 30.0
SETPOINT_MIN_C = TEMPERATURE_AXIS_MIN_C
SETPOINT_MAX_C = TEMPERATURE_AXIS_MAX_C

DEFAULT_KP = 1.0
KP_MIN = 0.0
KP_MAX = 500.0

OUTPUT_CSV_FILENAME = Path(__file__).resolve().parents[1] / "data" / "temperature_log.csv"
# ---------------------------------------------------------------------------

LINE_PATTERN = re.compile(
    r"Temperature \(C\):\s*(?P<temperature>-?\d+\.?\d*),\s*"
    r"Time \(s\):\s*(?P<time>-?\d+\.?\d*),\s*"
    r"PWM:\s*(?P<pwm>\d+),\s*"
    r"Heat/Cool:\s*(?P<heat_cool>[01])"
)

CSV_FIELDNAMES = [
    "time_s",
    "temperature_C",
    "pwm",
    "heat_cool",
    "mode",
    "setpoint_C",
    "kp",
    "error_C",
]

# The Arduino reports direction as an integer (1 = heating, 0 = cooling).
# This dictionary just turns that number into a readable word for the GUI.
DIRECTION_LABELS = {1: "HEAT", 0: "COOL"}


def clamp_pwm(value):
    """Force a PWM value to stay inside the valid 0-255 range.

    Anything below PWM_MIN becomes PWM_MIN, anything above PWM_MAX becomes
    PWM_MAX, and anything already in range is returned unchanged.
    """
    return max(PWM_MIN, min(PWM_MAX, value))


def find_default_port():
    ports = list(serial.tools.list_ports.comports())
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        sys.exit("No serial ports found. Connect the Arduino or set SERIAL_PORT.")
    port_list = "\n".join(f"  {p.device} ({p.description})" for p in ports)
    sys.exit(f"Multiple serial ports found, set SERIAL_PORT to one of:\n{port_list}")


class SerialReader(QtCore.QThread):
    """Runs in a background thread so reading serial data never freezes the GUI.

    It both reads incoming measurement lines from the Arduino AND writes
    outgoing "SET PWM ... DIR ..." command lines back to it, using the same
    open serial connection.
    """

    measurement = QtCore.Signal(float, float, int, int)
    connected = QtCore.Signal()
    error = QtCore.Signal(str)

    def __init__(self, port, baud_rate, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud_rate = baud_rate
        self._running = True
        self.connection = None  # set once the serial port is actually open

    def run(self):
        try:
            with serial.Serial(self._port, self._baud_rate, timeout=1) as connection:
                self.connection = connection
                self.connected.emit()
                while self._running:
                    raw_line = connection.readline().decode("utf-8", errors="ignore").strip()
                    if not raw_line:
                        continue
                    match = LINE_PATTERN.search(raw_line)
                    if not match:
                        continue
                    time_s = float(match.group("time"))
                    temperature_c = float(match.group("temperature"))
                    pwm = int(match.group("pwm"))
                    heat_cool = int(match.group("heat_cool"))
                    self.measurement.emit(time_s, temperature_c, pwm, heat_cool)
        except serial.SerialException as error:
            self.error.emit(str(error))
        finally:
            self.connection = None

    def send_command(self, command_text):
        """Write one line of text to the Arduino, e.g. "SET PWM 120 DIR HEAT".

        Serial commands are plain text lines ending in a newline character,
        which is what Serial.readStringUntil('\\n') (or similar) expects on
        the Arduino side. If the port isn't open yet, this just does nothing
        instead of crashing.
        """
        if self.connection is None or not self.connection.is_open:
            return
        line_with_ending = command_text + "\n"
        self.connection.write(line_with_ending.encode("utf-8"))

    def stop(self):
        self._running = False
        self.wait()


class TemperaturePlotWindow(QtWidgets.QMainWindow):
    def __init__(self, port, baud_rate):
        super().__init__()
        self.setWindowTitle(f"TEC Temperature & P Controller - {port}")

        # Current control-panel state (what we intend to send to the
        # Arduino). In Manual mode these come straight from the direction
        # radios / PWM slider; in P mode compute_p_control() overwrites them
        # every time a new measurement arrives.
        self.current_pwm = 0
        self.current_direction = "COOL"
        self.control_mode = "MANUAL"  # or "P"

        # History lists used to draw the strip charts. Every new measurement
        # appends one entry to each of these, and old entries are dropped
        # once they scroll off the left edge of the window.
        self.times = []
        self.temperatures = []
        self.pwms = []
        self.directions = []  # "HEAT" or "COOL" for each sample, same length as above
        self.setpoints = []
        self.errors = []

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        main_layout.addWidget(self._build_live_readings_box())
        main_layout.addWidget(self._build_mode_box())
        main_layout.addWidget(self._build_manual_control_box())
        main_layout.addWidget(self._build_p_control_box())
        main_layout.addWidget(self._build_temperature_plot())
        main_layout.addWidget(self._build_pwm_plot())
        main_layout.addWidget(self._build_error_plot())

        # Controls are disabled until the serial port actually opens, so we
        # can't try to write to a port that isn't ready yet.
        self.manual_control_box.setEnabled(False)

        self.csv_file = open(OUTPUT_CSV_FILENAME, "w", newline="")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=CSV_FIELDNAMES)
        self.csv_writer.writeheader()

        self.redraw_timer = QtCore.QTimer(self)
        self.redraw_timer.timeout.connect(self.redraw_plots)
        self.redraw_timer.start(PLOT_UPDATE_INTERVAL_MS)

        self.reader = SerialReader(port, baud_rate)
        self.reader.measurement.connect(self.on_measurement)
        self.reader.connected.connect(self.on_serial_connected)
        self.reader.error.connect(self.on_error)
        self.reader.start()

    # -----------------------------------------------------------------
    # GUI widget construction
    # -----------------------------------------------------------------
    def _build_live_readings_box(self):
        """Build the row of read-only labels showing the latest values
        reported back by the Arduino (not just what we asked it to do), plus
        the setpoint/error this script is currently working from.
        """
        box = QtWidgets.QGroupBox("Live Readings")
        layout = QtWidgets.QHBoxLayout(box)

        # QLabel is just a piece of text on screen. We keep a reference to
        # each one (self.temperature_label, etc.) so we can update its text
        # later whenever a new measurement arrives.
        self.temperature_label = QtWidgets.QLabel("Temperature: -- C")
        self.pwm_label = QtWidgets.QLabel("PWM: --")
        self.direction_label = QtWidgets.QLabel("Direction: --")
        self.setpoint_label = QtWidgets.QLabel("Setpoint: -- C")
        self.error_label = QtWidgets.QLabel("Error: -- C")
        self.time_label = QtWidgets.QLabel("Time: -- s")

        labels = (
            self.temperature_label,
            self.pwm_label,
            self.direction_label,
            self.setpoint_label,
            self.error_label,
            self.time_label,
        )
        for label in labels:
            label.setStyleSheet("font-size: 14pt;")
            layout.addWidget(label)

        return box

    def _build_mode_box(self):
        """Build the Manual/P Control switch. Only one mode drives the
        Arduino at a time - the other mode's widgets stay visible (and, for
        the P-control setpoint/Kp, editable) but don't send anything.
        """
        box = QtWidgets.QGroupBox("Control Mode")
        layout = QtWidgets.QHBoxLayout(box)

        self.manual_mode_radio = QtWidgets.QRadioButton("Manual")
        self.p_mode_radio = QtWidgets.QRadioButton("P Control")
        self.manual_mode_radio.setChecked(True)  # start open-loop, same as Module 4
        self.mode_button_group = QtWidgets.QButtonGroup(self)
        self.mode_button_group.addButton(self.manual_mode_radio)
        self.mode_button_group.addButton(self.p_mode_radio)
        layout.addWidget(self.manual_mode_radio)
        layout.addWidget(self.p_mode_radio)
        self.p_mode_radio.toggled.connect(self.on_mode_changed)

        return box

    def _build_manual_control_box(self):
        """Build the heat/cool switch and the synchronized PWM slider + text
        box. Only takes effect while Control Mode is Manual.
        """
        self.manual_control_box = QtWidgets.QGroupBox("Manual Control")
        layout = QtWidgets.QHBoxLayout(self.manual_control_box)

        # --- Heat/Cool switch -------------------------------------------------
        # Two radio buttons in the same QButtonGroup act like a switch: only
        # one of them can be selected ("checked") at a time.
        direction_group_box = QtWidgets.QGroupBox("Direction")
        direction_layout = QtWidgets.QHBoxLayout(direction_group_box)
        self.heat_radio = QtWidgets.QRadioButton("Heat")
        self.cool_radio = QtWidgets.QRadioButton("Cool")
        self.cool_radio.setChecked(True)  # matches the Arduino sketch's default state
        self.direction_button_group = QtWidgets.QButtonGroup(self)
        self.direction_button_group.addButton(self.heat_radio)
        self.direction_button_group.addButton(self.cool_radio)
        direction_layout.addWidget(self.heat_radio)
        direction_layout.addWidget(self.cool_radio)
        # toggled() fires for both the button that got checked and the one
        # that got unchecked, so we only react when a button becomes checked.
        self.heat_radio.toggled.connect(self.on_direction_changed)
        layout.addWidget(direction_group_box)

        # --- PWM slider ---------------------------------------------------
        self.pwm_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pwm_slider.setMinimum(PWM_MIN)
        self.pwm_slider.setMaximum(PWM_MAX)
        self.pwm_slider.setValue(self.current_pwm)
        self.pwm_slider.valueChanged.connect(self.on_slider_moved)

        # --- PWM editable text box -----------------------------------------
        self.pwm_edit = QtWidgets.QLineEdit(str(self.current_pwm))
        self.pwm_edit.setFixedWidth(50)
        # QIntValidator gives basic protection while typing (letters won't
        # even appear), but we still clamp the value ourselves below because
        # a validator alone won't stop something like a pasted "999".
        self.pwm_edit.setValidator(QtGui.QIntValidator(PWM_MIN, PWM_MAX, self))
        # editingFinished fires when the user presses Enter or clicks away,
        # not on every keystroke, so we're not fighting the user while they type.
        self.pwm_edit.editingFinished.connect(self.on_pwm_edit_finished)

        pwm_layout = QtWidgets.QHBoxLayout()
        pwm_layout.addWidget(QtWidgets.QLabel("PWM (0-255):"))
        pwm_layout.addWidget(self.pwm_slider)
        pwm_layout.addWidget(self.pwm_edit)
        layout.addLayout(pwm_layout)

        return self.manual_control_box

    def _build_p_control_box(self):
        """Build the setpoint and Kp inputs for P-only control. Editable
        regardless of the current mode, but only actually drives the
        Arduino while Control Mode is P Control.
        """
        self.p_control_box = QtWidgets.QGroupBox("P Control")
        layout = QtWidgets.QHBoxLayout(self.p_control_box)

        self.setpoint_spinbox = QtWidgets.QDoubleSpinBox()
        self.setpoint_spinbox.setRange(SETPOINT_MIN_C, SETPOINT_MAX_C)
        self.setpoint_spinbox.setDecimals(1)
        self.setpoint_spinbox.setSingleStep(0.5)
        self.setpoint_spinbox.setValue(DEFAULT_SETPOINT_C)
        self.setpoint_spinbox.setSuffix(" C")

        self.kp_spinbox = QtWidgets.QDoubleSpinBox()
        self.kp_spinbox.setRange(KP_MIN, KP_MAX)
        self.kp_spinbox.setDecimals(2)
        self.kp_spinbox.setSingleStep(0.1)
        self.kp_spinbox.setValue(DEFAULT_KP)

        layout.addWidget(QtWidgets.QLabel("Setpoint (Tset):"))
        layout.addWidget(self.setpoint_spinbox)
        layout.addWidget(QtWidgets.QLabel("Kp:"))
        layout.addWidget(self.kp_spinbox)
        layout.addWidget(QtWidgets.QLabel("u = Kp * (Tset - T); sign(u) -> direction, |u| -> PWM"))

        return self.p_control_box

    def _build_temperature_plot(self):
        self.temperature_plot = pg.PlotWidget()
        self.temperature_plot.setBackground("w")
        self.temperature_plot.setLabel("left", "Temperature", units="C")
        self.temperature_plot.setLabel("bottom", "Time", units="s")
        self.temperature_plot.showGrid(x=True, y=True)
        self.temperature_curve = self.temperature_plot.plot(pen=pg.mkPen(color="r", width=2))
        self.setpoint_curve = self.temperature_plot.plot(
            pen=pg.mkPen(color="g", width=2, style=QtCore.Qt.DashLine)
        )
        return self.temperature_plot

    def _build_pwm_plot(self):
        """Build the PWM strip chart, drawn as two curves so the line color
        reflects the direction that was active at each point in time:
        solid red while heating, solid blue while cooling.
        """
        self.pwm_plot = pg.PlotWidget()
        self.pwm_plot.setLabel("left", "PWM", units="")
        self.pwm_plot.setLabel("bottom", "Time", units="s")
        self.pwm_plot.showGrid(x=True, y=True)
        self.pwm_plot.setYRange(PWM_MIN, PWM_MAX, padding=0)
        self.pwm_heat_curve = self.pwm_plot.plot(pen=pg.mkPen(color="r", width=2))
        self.pwm_cool_curve = self.pwm_plot.plot(pen=pg.mkPen(color="b", width=2))
        return self.pwm_plot

    def _build_error_plot(self):
        """Build the error (Tset - T) strip chart, with a dashed zero line
        so it's obvious at a glance which side of the setpoint we're on.
        """
        self.error_plot = pg.PlotWidget()
        self.error_plot.setLabel("left", "Error (Tset - T)", units="C")
        self.error_plot.setLabel("bottom", "Time", units="s")
        self.error_plot.showGrid(x=True, y=True)
        zero_line = pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.DashLine)
        )
        self.error_plot.addItem(zero_line)
        self.error_curve = self.error_plot.plot(pen=pg.mkPen(color="orange", width=2))
        return self.error_plot

    # -----------------------------------------------------------------
    # Serial command sending
    # -----------------------------------------------------------------
    def send_current_settings(self):
        """Send the currently selected PWM value and direction to the
        Arduino as one command line, e.g. "SET PWM 120 DIR HEAT". The PWM
        value and direction always travel together in a single command so
        the Arduino never receives one without the other.
        """
        command = f"SET PWM {self.current_pwm} DIR {self.current_direction}"
        self.reader.send_command(command)
        # Printing here is our "terminal output": run this script from a
        # terminal and you'll see every command as it's sent.
        print(f"Sent: {command}")

    def apply_pwm(self, value):
        """Clamp a requested PWM value, then keep the slider, the text box,
        and self.current_pwm all in agreement before sending it out. Only
        called from the Manual-mode widgets, which are disabled while P
        Control is active.
        """
        value = clamp_pwm(int(value))
        self._sync_manual_widgets(value, self.current_direction)
        self.current_pwm = value
        self.send_current_settings()

    def _sync_manual_widgets(self, pwm, direction):
        """Update the direction radios and PWM slider/text box to reflect
        (pwm, direction) without re-triggering their own signal handlers -
        used both when the user changes them directly (Manual mode) and
        when compute_p_control() wants the GUI to show what it just
        commanded (P mode), so the panel always shows the truth.
        """
        # blockSignals stops these widgets from firing their own
        # "value changed" signals while we set them programmatically, which
        # would otherwise cause an infinite slider <-> text box update loop
        # (or re-entrant sends in P mode).
        self.pwm_slider.blockSignals(True)
        self.pwm_slider.setValue(pwm)
        self.pwm_slider.blockSignals(False)

        self.pwm_edit.blockSignals(True)
        self.pwm_edit.setText(str(pwm))
        self.pwm_edit.blockSignals(False)

        self.heat_radio.blockSignals(True)
        self.cool_radio.blockSignals(True)
        if direction == "HEAT":
            self.heat_radio.setChecked(True)
        else:
            self.cool_radio.setChecked(True)
        self.heat_radio.blockSignals(False)
        self.cool_radio.blockSignals(False)

    @QtCore.Slot(int)
    def on_slider_moved(self, value):
        self.apply_pwm(value)

    @QtCore.Slot()
    def on_pwm_edit_finished(self):
        text = self.pwm_edit.text()
        try:
            value = int(text)
        except ValueError:
            value = self.current_pwm  # box was left empty/invalid; keep the old value
        self.apply_pwm(value)

    @QtCore.Slot(bool)
    def on_direction_changed(self, heat_is_checked):
        self.current_direction = "HEAT" if heat_is_checked else "COOL"
        self.send_current_settings()

    @QtCore.Slot(bool)
    def on_mode_changed(self, p_is_checked):
        self.control_mode = "P" if p_is_checked else "MANUAL"
        # Manual widgets are disabled in P mode so the two controllers can
        # never fight over the same serial link.
        self.manual_control_box.setEnabled(not p_is_checked and self.reader.connection is not None)
        if not p_is_checked:
            # Switching back to Manual: resume from whatever the slider/
            # radio buttons are currently showing, rather than leaving the
            # Arduino running on the last PWM computed by the P controller.
            self.current_pwm = self.pwm_slider.value()
            self.current_direction = "HEAT" if self.heat_radio.isChecked() else "COOL"
            self.send_current_settings()

    @QtCore.Slot()
    def on_serial_connected(self):
        # Now that the port is open it's safe to write to it, so unlock the
        # manual controls (if that's the active mode) and tell the Arduino
        # our starting PWM/direction.
        self.manual_control_box.setEnabled(self.control_mode == "MANUAL")
        self.send_current_settings()

    # -----------------------------------------------------------------
    # P-only control
    # -----------------------------------------------------------------
    def compute_p_control(self, temperature_c):
        """Proportional-only control law, run once per incoming (already
        1000-sample-averaged) temperature measurement while Control Mode is
        P Control:

            e = Tset - T
            u = Kp * e

        The sign of u becomes the direction (u >= 0 -> HEAT, since a
        positive error means we're colder than the setpoint; u < 0 -> COOL),
        and |u| becomes the PWM magnitude, rounded to the nearest integer
        and clamped to 0-255 before being sent to the Arduino.

        Returns (setpoint, error) so the caller can log/plot them even
        though the send itself already happened here.
        """
        setpoint = self.setpoint_spinbox.value()
        kp = self.kp_spinbox.value()
        error = setpoint - temperature_c
        u = kp * error

        direction = "HEAT" if u >= 0 else "COOL"
        pwm_magnitude = clamp_pwm(int(round(abs(u))))

        self.current_pwm = pwm_magnitude
        self.current_direction = direction
        self._sync_manual_widgets(pwm_magnitude, direction)
        self.send_current_settings()

        return setpoint, error

    # -----------------------------------------------------------------
    # Incoming measurements + plot updates
    # -----------------------------------------------------------------
    @QtCore.Slot(float, float, int, int)
    def on_measurement(self, time_s, temperature_c, pwm, heat_cool):
        if self.control_mode == "P":
            setpoint, error = self.compute_p_control(temperature_c)
        else:
            # Manual mode still drives nothing off temperature, but we keep
            # computing/showing setpoint and error against the current
            # spinbox values so they're ready to read the moment you switch
            # to P Control.
            setpoint = self.setpoint_spinbox.value()
            error = setpoint - temperature_c

        direction = DIRECTION_LABELS[heat_cool]

        self.times.append(time_s)
        self.temperatures.append(temperature_c)
        self.pwms.append(pwm)
        self.directions.append(direction)
        self.setpoints.append(setpoint)
        self.errors.append(error)

        # Update the live readout labels with what the Arduino just reported
        # (temperature/PWM/direction/time) plus this script's own setpoint/error.
        self.temperature_label.setText(f"Temperature: {temperature_c:.2f} C")
        self.pwm_label.setText(f"PWM: {pwm}")
        self.direction_label.setText(f"Direction: {direction}")
        self.setpoint_label.setText(f"Setpoint: {setpoint:.2f} C")
        self.error_label.setText(f"Error: {error:+.2f} C")
        self.time_label.setText(f"Time: {time_s:.2f} s")

        self.csv_writer.writerow({
            "time_s": time_s,
            "temperature_C": temperature_c,
            "pwm": pwm,
            "heat_cool": heat_cool,
            "mode": self.control_mode,
            "setpoint_C": setpoint,
            "kp": self.kp_spinbox.value(),
            "error_C": error,
        })
        self.csv_file.flush()

    def redraw_plots(self):
        """Runs on a timer (see PLOT_UPDATE_INTERVAL_MS) to redraw all three
        strip charts and drop any data older than STRIP_CHART_WINDOW_S.
        """
        if not self.times:
            return

        latest_time = self.times[-1]
        window_start = latest_time - STRIP_CHART_WINDOW_S

        # Drop old samples that have scrolled off the left edge of the chart.
        while self.times and self.times[0] < window_start:
            self.times.pop(0)
            self.temperatures.pop(0)
            self.pwms.pop(0)
            self.directions.pop(0)
            self.setpoints.pop(0)
            self.errors.pop(0)

        self.temperature_curve.setData(self.times, self.temperatures)
        self.setpoint_curve.setData(self.times, self.setpoints)

        # Split the PWM data into a "heat" series and a "cool" series so each
        # can be drawn in its own color. Where a sample doesn't belong to a
        # series we put float("nan") instead of a number - pyqtgraph leaves
        # a gap wherever it sees NaN, so the two colors never blend together.
        heat_pwms = [
            pwm if direction == "HEAT" else float("nan")
            for pwm, direction in zip(self.pwms, self.directions)
        ]
        cool_pwms = [
            pwm if direction == "COOL" else float("nan")
            for pwm, direction in zip(self.pwms, self.directions)
        ]
        self.pwm_heat_curve.setData(self.times, heat_pwms)
        self.pwm_cool_curve.setData(self.times, cool_pwms)

        self.error_curve.setData(self.times, self.errors)

        # The temperature axis follows only the samples still visible in the
        # rolling window. This makes small temperature changes easier to see.
        lowest_temperature = min(self.temperatures)
        highest_temperature = max(self.temperatures)
        measured_span = highest_temperature - lowest_temperature

        if measured_span < MIN_TEMPERATURE_AXIS_SPAN_C:
            # If the data are nearly flat, use a six-degree window centered
            # on the measured temperatures so noise is not over-magnified.
            center_temperature = (lowest_temperature + highest_temperature) / 2
            temperature_axis_min = center_temperature - MIN_TEMPERATURE_AXIS_SPAN_C / 2
            temperature_axis_max = center_temperature + MIN_TEMPERATURE_AXIS_SPAN_C / 2
        else:
            # For a wider range, leave exactly one degree on each side.
            temperature_axis_min = lowest_temperature - TEMPERATURE_AXIS_MARGIN_C
            temperature_axis_max = highest_temperature + TEMPERATURE_AXIS_MARGIN_C

        self.temperature_plot.setYRange(
            temperature_axis_min, temperature_axis_max, padding=0
        )
        self.temperature_plot.setXRange(window_start, latest_time, padding=0)
        self.pwm_plot.setXRange(window_start, latest_time, padding=0)
        self.error_plot.setXRange(window_start, latest_time, padding=0)

    @QtCore.Slot(str)
    def on_error(self, message):
        QtWidgets.QMessageBox.critical(self, "Serial error", message)
        self.close()

    def closeEvent(self, event):
        self.reader.stop()
        self.csv_file.close()
        super().closeEvent(event)


def main():
    port = SERIAL_PORT or find_default_port()

    app = QtWidgets.QApplication(sys.argv)
    window = TemperaturePlotWindow(port, BAUD_RATE)
    window.resize(950, 900)
    window.show()
    sys.exit(app.exec())


# Run with:
#   cd "/Users/joshbub/Documents/PHYS39A_Repo/PHY39A_repo/Module 5" && venv/bin/python Python/serial_plot_mod5.py
if __name__ == "__main__":
    main()
