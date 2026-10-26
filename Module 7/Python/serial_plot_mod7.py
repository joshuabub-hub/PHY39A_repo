"""Read the PWM_Serial_Control sketch's serial output, plot the TEC and
rod 1-5 temperatures, PWM, direction, setpoint, and error vs. Arduino time,
log every accepted record to a new timestamped CSV, and send PWM/direction
commands back to the Arduino - either by hand (Manual mode, identical to
Module 4) or from a proportional-integral (PI) closed-loop controller.

The Module 7 sketch reads six thermistors (A0 = TEC base, A1-A5 = rod
thermistors 1-5) and sends one measurement record per acquisition cycle,
after a header line printed once at startup:
    DATA,time_s,tec_C,rod1_C,rod2_C,rod3_C,rod4_C,rod5_C,pwm,heat_cool,setpoint_C,safety
    DATA,12.50,23.41,23.38,23.36,23.34,23.31,23.29,120,1,nan,OK
Only lines starting with DATA whose fields all parse are used; the header
and any other text are ignored. A faulted channel reads nan. The Arduino's
setpoint_C is always nan - the setpoint lives here and is logged here.
safety is OK, CUTOFF (over-temperature) or SENSOR_FAULT (TEC sensor).

Outgoing commands sent TO the Arduino look like:
    SET PWM 120 DIR HEAT
    SET PWM 45 DIR COOL

The Arduino still averages about 1000 raw thermistor-voltage samples per
channel before converting to a temperature, still parses "SET PWM ... DIR
..." commands, still drives the H-bridge, and still enforces its own
independent over-temperature cutoff (and now a TEC sensor-fault cutoff) no
matter what this script asks for. Only tec_C is used for PI feedback; the
rod temperatures are plotted and logged. No calibration is applied.

Two control modes are available from the GUI:
  - Manual: pick a PWM value and direction by hand, exactly like Module 4.
  - PI Control: every time a new (already 1000-sample-averaged) TEC-base
    temperature arrives from the Arduino, this script computes
        e_n     = Tset - T_n
        q_n+1   = q_n + e_n * dt_n
        u_n     = Kp * e_n + Ki * q_n+1
    where dt_n is the Arduino-reported time between this measurement and
    the previous accepted one. The sign of u (the requested command) becomes
    the direction (u >= 0 -> HEAT, u < 0 -> COOL) and |u|, rounded to the
    nearest integer and clamped to 0-255, becomes the PWM magnitude (the
    applied command). That pair is sent as one "SET PWM ... DIR ..." command,
    same as Manual mode would.

Anti-windup is conditional integration: if the command requested with the
old integral (Kp * e_n + Ki * q_n) is already beyond the PWM limit and e_n
has the same sign as that command (so integrating would push it farther
into saturation), q is held for that step. The output clamp and the
Arduino's own over-temperature cutoff stay active regardless.

With Ki = 0 this is the Module 5 P-only controller. Start gains small (see
DEFAULT_KP / DEFAULT_KI below) and increase them gradually.
"""

import csv
from collections import deque
from datetime import datetime
import math
from pathlib import Path
import sys
import threading

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

SERIAL_READ_TIMEOUT_S = 0.05  # bounds how long a queued command waits when the Arduino is quiet
SERIAL_WRITE_TIMEOUT_S = 1.0  # a write blocked this long means the device stopped reading
MANUAL_SEND_INTERVAL_MS = 150  # slider drags send at most this often (Arduino checks commands every ~110 ms)

TEMPERATURE_AXIS_MIN_C = 0.0
TEMPERATURE_AXIS_MAX_C = 50.0
TEMPERATURE_AXIS_MARGIN_C = 1.0
MIN_TEMPERATURE_AXIS_SPAN_C = 6.0

PWM_MIN = 0
PWM_MAX = 255

# Legends sit in each plot's top-left corner (a positive offset anchors to
# the top-left) on an opaque light-gray box with a dark border and dark text.
LEGEND_OPTIONS = dict(
    offset=(10, 10),
    labelTextSize="11pt",
    labelTextColor=(20, 20, 20),
    brush=pg.mkBrush(235, 235, 235, 240),
    pen=pg.mkPen(color=(90, 90, 90), width=1),
)

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

# Ki is in PWM counts per (degree C * second) of accumulated error, so
# Ki * q has the same PWM units as Kp * e. The slider moves in steps of
# 1 / KI_SLIDER_SCALE; the text box accepts the same resolution.
DEFAULT_KI = 0.0
KI_MIN = 0.0
KI_MAX = 10.0
KI_DECIMALS = 3
KI_SLIDER_SCALE = 10 ** KI_DECIMALS

# Every run writes two NEW files in Module 7/data, named with the time the
# GUI started, e.g. raw_mod7_20261026_143005.csv. Existing files are never
# opened for writing, so an old run can't be overwritten or appended to.
#   raw_...    every accepted Arduino DATA record, exactly as received
#   pi_log_... what this script computed for that same record (setpoint,
#              gains, PI terms); join the two files on time_s
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW_CSV_PREFIX = "raw_mod7"
PI_LOG_CSV_PREFIX = "pi_log_mod7"

# Fixed label, color and line width for every temperature trace. The same
# colors are used for the live readouts above the plot, so a number and its
# trace always match. TEC is thicker because it is the feedback channel.
TEC_TRACE_WIDTH = 3
ROD_TRACE_WIDTH = 1.5
TEMPERATURE_TRACES = [
    # (record field, label,  color (R, G, B))
    ("tec_C",  "TEC",   (0, 0, 0)),
    ("rod1_C", "Rod 1", (31, 119, 180)),   # blue
    ("rod2_C", "Rod 2", (255, 127, 14)),   # orange
    ("rod3_C", "Rod 3", (148, 103, 189)),  # purple
    ("rod4_C", "Rod 4", (140, 86, 75)),    # brown
    ("rod5_C", "Rod 5", (23, 190, 207)),   # teal
]
# ---------------------------------------------------------------------------

ROD_FIELDNAMES = ["rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C"]
TEMPERATURE_FIELDNAMES = ["tec_C", *ROD_FIELDNAMES]

# The 11 fields of an Arduino DATA record, in the order they are sent after
# the leading "DATA" tag. The raw CSV uses exactly these column names.
RAW_CSV_FIELDNAMES = [
    "time_s",
    *TEMPERATURE_FIELDNAMES,
    "pwm",
    "heat_cool",
    "setpoint_C",
    "safety",
]
SAFETY_STATES = {"OK", "CUTOFF", "SENSOR_FAULT"}

# The PI log has one row per accepted record (same time_s as the raw file).
# tec_C is repeated here because error_C was computed from it.
PI_LOG_CSV_FIELDNAMES = [
    "time_s",
    "tec_C",
    "mode",
    "setpoint_C",
    "kp",
    "error_C",
    # PI columns, blank in Manual mode. p_term = Kp * e, i_term = Ki * q_n+1,
    # integral_C_s = q_n+1, u_requested = p_term + i_term (unclamped),
    # u_applied = signed PWM actually sent (+ HEAT, - COOL) after the clamp.
    "ki",
    "dt_s",
    "p_term",
    "i_term",
    "integral_C_s",
    "integral_held",
    "u_requested",
    "u_applied",
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


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def parse_data_record(line):
    """Check one complete line of Arduino text and return it as a record
    (a dict), or return None if the line should be ignored.

    A line is accepted only if ALL of these are true:
      1. it starts with the tag "DATA" and has exactly 11 more
         comma-separated fields (time_s ... safety);
      2. time_s is a real number, and every temperature is a number or "nan"
         (the Arduino sends nan for a faulted thermistor);
      3. pwm is a whole number from 0 to 255, heat_cool is 0 or 1, and safety
         is one of OK / CUTOFF / SENSOR_FAULT.
    Anything else - the "DATA,time_s,tec_C,..." header, diagnostic text, or a
    line garbled by noise or cut off part-way - returns None. Nothing in here
    can raise an error, so a bad line can never crash the GUI.

    The returned dict holds two versions of every field:
      record["raw"]    the 11 field strings exactly as the Arduino sent them
                       (this is what goes into the raw CSV, unchanged)
      record["tec_C"], record["pwm"], ...   the same values as numbers, for
                       plotting and the PI controller
    """
    parts = line.split(",")

    # Check 1: the tag and the number of fields.
    if parts[0] != "DATA" or len(parts) != 1 + len(RAW_CSV_FIELDNAMES):
        return None
    raw = dict(zip(RAW_CSV_FIELDNAMES, parts[1:]))

    # Check 2 and 3: every field converts to the right kind of value.
    # float("time_s") / int("pwm") raise ValueError, which is how the header
    # line gets rejected here.
    try:
        record = {"raw": raw, "time_s": float(raw["time_s"])}
        for name in TEMPERATURE_FIELDNAMES:
            record[name] = float(raw[name])
        record["pwm"] = int(raw["pwm"])
        record["heat_cool"] = int(raw["heat_cool"])
    except ValueError:
        return None
    record["safety"] = raw["safety"]

    if not math.isfinite(record["time_s"]):
        return None
    if not PWM_MIN <= record["pwm"] <= PWM_MAX:
        return None
    if record["heat_cool"] not in DIRECTION_LABELS:
        return None
    if record["safety"] not in SAFETY_STATES:
        return None
    # "inf" would pass float() but is never a real reading.
    if any(math.isinf(record[name]) for name in TEMPERATURE_FIELDNAMES):
        return None
    return record


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------
def create_new_csv(prefix, fieldnames, started_at):
    """Create a brand-new CSV file in DATA_DIR, write its header row, and
    return (file, writer, path).

    The name is <prefix>_<YYYYMMDD_HHMMSS>.csv using the GUI's start time.
    Mode "x" means "create, and fail if the file already exists", so an
    existing file can never be overwritten; if the name is taken (two
    starts in the same second) a _2, _3, ... suffix is added instead.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"{prefix}_{stamp}.csv"
    n = 2
    while True:
        try:
            csv_file = open(path, "x", newline="")
            break
        except FileExistsError:
            path = DATA_DIR / f"{prefix}_{stamp}_{n}.csv"
            n += 1
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    csv_file.flush()
    return csv_file, writer, path


def find_default_port():
    ports = list(serial.tools.list_ports.comports())
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        sys.exit("No serial ports found. Connect the Arduino or set SERIAL_PORT.")
    port_list = "\n".join(f"  {p.device} ({p.description})" for p in ports)
    sys.exit(f"Multiple serial ports found, set SERIAL_PORT to one of:\n{port_list}")


class SerialReader(QtCore.QThread):
    """Owns the serial port. Only this thread touches the port: it reads
    measurement lines from the Arduino and writes the "SET PWM ... DIR ..."
    commands that the GUI thread queues with send_command().
    """

    measurement = QtCore.Signal(dict)  # one accepted DATA record, see parse_data_record()
    line_rejected = QtCore.Signal(str)  # the text of a complete line that was ignored
    connected = QtCore.Signal()
    error = QtCore.Signal(str)
    command_sent = QtCore.Signal(str)
    commands_dropped = QtCore.Signal(int)

    def __init__(self, port, baud_rate, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud_rate = baud_rate
        self._running = True
        self._outgoing = deque()
        self._outgoing_lock = threading.Lock()
        self._port_open = False

    @property
    def is_connected(self):
        with self._outgoing_lock:
            return self._port_open

    def run(self):
        try:
            with serial.Serial(
                self._port,
                self._baud_rate,
                timeout=SERIAL_READ_TIMEOUT_S,
                write_timeout=SERIAL_WRITE_TIMEOUT_S,
            ) as connection:
                with self._outgoing_lock:
                    self._port_open = True
                self.connected.emit()
                # Bytes arrive in arbitrary chunks, so they collect in
                # `buffer` and only text up to a newline is handed on. A line
                # still being received stays in the buffer until its newline
                # arrives, so only complete lines are ever parsed.
                buffer = b""
                while self._running:
                    self._write_queued_commands(connection)
                    buffer += connection.read(max(1, connection.in_waiting))
                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        self._handle_line(raw_line)
        except serial.SerialException as error:
            self.error.emit(str(error))
        finally:
            with self._outgoing_lock:
                self._port_open = False
                dropped = len(self._outgoing)
                self._outgoing.clear()
            if dropped:
                self.commands_dropped.emit(dropped)

    def _write_queued_commands(self, connection):
        while True:
            with self._outgoing_lock:
                if not self._outgoing:
                    return
                # Peek, write, then remove: if the write raises, the command
                # stays queued and is reported as dropped instead of vanishing.
                command = self._outgoing[0]
            connection.write((command + "\n").encode("utf-8"))
            with self._outgoing_lock:
                self._outgoing.popleft()
            self.command_sent.emit(command)

    def _handle_line(self, raw_line):
        # errors="replace" turns any corrupted bytes into a placeholder
        # character instead of raising, and strip() removes the "\r".
        text = raw_line.decode("utf-8", errors="replace").strip()
        if not text:
            return  # an empty line isn't a measurement or a rejection
        record = parse_data_record(text)
        if record is None:
            self.line_rejected.emit(text)
        else:
            self.measurement.emit(record)

    def send_command(self, command_text):
        """Queue one command line, e.g. "SET PWM 120 DIR HEAT", for the reader
        thread to write. Returns False if the port is not open, so the caller
        can report that the command was not sent.
        """
        with self._outgoing_lock:
            if not self._port_open:
                return False
            self._outgoing.append(command_text)
            return True

    def stop(self):
        self._running = False
        self.wait()


class TemperaturePlotWindow(QtWidgets.QMainWindow):
    def __init__(self, port, baud_rate):
        super().__init__()
        self.setWindowTitle(f"TEC Temperature & PI Controller - {port}")

        # Current control-panel state (what we intend to send to the
        # Arduino). In Manual mode these come straight from the direction
        # radios / PWM slider; in PI mode compute_pi_control() overwrites
        # them every time a new measurement arrives.
        self.current_pwm = 0
        self.current_direction = "COOL"
        self.control_mode = "MANUAL"  # or "PI"

        # PI state. integral is q (degree C * s). previous_pi_time_s is the
        # Arduino time of the last measurement the PI step used, so dt comes
        # from real elapsed time; None means the next step has no previous
        # sample and integrates over dt = 0.
        self.integral = 0.0
        self.previous_pi_time_s = None
        self.saved_ki = DEFAULT_KI  # Ki to restore when P-only is turned off

        # ----- Data storage for the plots -----
        # History lists used to draw the strip charts. Every accepted record
        # appends exactly one entry to EVERY list below (NaN where there is
        # no value, e.g. a faulted thermistor), so entry i of each list
        # always belongs to the same record as self.times[i]. Old entries
        # are dropped from all lists together once they scroll off the left
        # edge of the window.
        self.times = []
        # One list per temperature trace, keyed by the record field name:
        # self.temperature_history["rod3_C"] is rod 3's recent values.
        self.temperature_history = {name: [] for name in TEMPERATURE_FIELDNAMES}
        self.pwms = []
        self.directions = []  # "HEAT" or "COOL" for each sample, same length as above
        self.setpoints = []
        self.errors = []
        self.p_terms = []  # u_P = Kp * e; NaN for Manual-mode samples (gap in the plot)
        self.i_terms = []  # u_I = Ki * q_n+1; NaN for Manual-mode samples

        # Serial line counters shown in the "Serial Lines" box.
        self.accepted_line_count = 0
        self.rejected_line_count = 0

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        temperatures_row = QtWidgets.QHBoxLayout()
        temperatures_row.addWidget(self._build_temperature_readings_box(), stretch=1)
        temperatures_row.addWidget(self._build_serial_lines_box())
        main_layout.addLayout(temperatures_row)
        main_layout.addWidget(self._build_live_readings_box())
        main_layout.addWidget(self._build_pi_readings_box())
        main_layout.addWidget(self._build_mode_box())
        main_layout.addWidget(self._build_manual_control_box())
        main_layout.addWidget(self._build_pi_control_box())
        main_layout.addWidget(self._build_temperature_plot())
        main_layout.addWidget(self._build_pwm_plot())
        main_layout.addWidget(self._build_error_plot())

        # Controls are disabled until the serial port actually opens, so we
        # can't try to write to a port that isn't ready yet.
        self.manual_control_box.setEnabled(False)

        started_at = datetime.now()
        self.raw_csv_file, self.raw_csv_writer, raw_path = create_new_csv(
            RAW_CSV_PREFIX, RAW_CSV_FIELDNAMES, started_at
        )
        self.pi_log_file, self.pi_log_writer, pi_log_path = create_new_csv(
            PI_LOG_CSV_PREFIX, PI_LOG_CSV_FIELDNAMES, started_at
        )
        print(f"Raw data: {raw_path}")
        print(f"PI log:   {pi_log_path}")
        self.raw_file_label.setText(f"Raw CSV: {raw_path.name}")

        self.redraw_timer = QtCore.QTimer(self)
        self.redraw_timer.timeout.connect(self.redraw_plots)
        self.redraw_timer.start(PLOT_UPDATE_INTERVAL_MS)

        self.manual_send_timer = QtCore.QTimer(self)
        self.manual_send_timer.setSingleShot(True)
        self.manual_send_timer.setInterval(MANUAL_SEND_INTERVAL_MS)
        self.manual_send_timer.timeout.connect(self.send_current_settings)

        self.reader = SerialReader(port, baud_rate)
        self.reader.measurement.connect(self.on_measurement)
        self.reader.line_rejected.connect(self.on_line_rejected)
        self.reader.connected.connect(self.on_serial_connected)
        self.reader.error.connect(self.on_error)
        self.reader.command_sent.connect(self.on_command_sent)
        self.reader.commands_dropped.connect(self.on_commands_dropped)
        self.reader.start()

    # -----------------------------------------------------------------
    # GUI widget construction
    # -----------------------------------------------------------------
    def _build_temperature_readings_box(self):
        """Build one live readout per thermistor, colored like its trace on
        the temperature plot. self.temperature_labels["rod2_C"] is rod 2's
        label, so on_measurement() can update them all in one loop.
        """
        box = QtWidgets.QGroupBox("Temperatures (C)")
        layout = QtWidgets.QHBoxLayout(box)

        self.temperature_labels = {}
        for field_name, label_text, color in TEMPERATURE_TRACES:
            label = QtWidgets.QLabel(f"{label_text}: --")
            weight = "bold" if field_name == "tec_C" else "normal"
            label.setStyleSheet(
                f"font-size: 14pt; font-weight: {weight}; color: rgb{color};"
            )
            self.temperature_labels[field_name] = label
            layout.addWidget(label)

        return box

    def _build_serial_lines_box(self):
        """Build the accepted/rejected serial line counters. "Rejected"
        counts every non-empty complete line that wasn't a valid DATA record,
        including the Arduino's one-time header line, so it normally reads 1
        right after connecting. The most recent rejected line is shown so you
        can see why.
        """
        box = QtWidgets.QGroupBox("Serial Lines")
        layout = QtWidgets.QVBoxLayout(box)

        self.accepted_count_label = QtWidgets.QLabel("Accepted: 0")
        self.rejected_count_label = QtWidgets.QLabel("Rejected: 0")
        counts_row = QtWidgets.QHBoxLayout()
        counts_row.addWidget(self.accepted_count_label)
        counts_row.addWidget(self.rejected_count_label)
        layout.addLayout(counts_row)

        self.last_rejected_label = QtWidgets.QLabel("Last rejected: --")
        self.last_rejected_label.setStyleSheet("color: gray;")
        self.last_rejected_label.setMaximumWidth(360)
        layout.addWidget(self.last_rejected_label)

        self.raw_file_label = QtWidgets.QLabel("Raw CSV: --")
        self.raw_file_label.setStyleSheet("color: gray;")
        layout.addWidget(self.raw_file_label)

        return box

    def _build_live_readings_box(self):
        """Build the row of read-only labels showing the latest values
        reported back by the Arduino (not just what we asked it to do), plus
        the setpoint/error this script is currently working from.
        """
        box = QtWidgets.QGroupBox("Live Readings")
        layout = QtWidgets.QHBoxLayout(box)

        # QLabel is just a piece of text on screen. We keep a reference to
        # each one (self.pwm_label, etc.) so we can update its text
        # later whenever a new measurement arrives.
        self.pwm_label = QtWidgets.QLabel("PWM: --")
        self.direction_label = QtWidgets.QLabel("Direction: --")
        self.setpoint_label = QtWidgets.QLabel("Setpoint: -- C")
        self.error_label = QtWidgets.QLabel("Error: -- C")
        self.safety_label = QtWidgets.QLabel("Safety: --")
        self.time_label = QtWidgets.QLabel("Time: -- s")

        labels = (
            self.pwm_label,
            self.direction_label,
            self.setpoint_label,
            self.error_label,
            self.safety_label,
            self.time_label,
        )
        for label in labels:
            label.setStyleSheet("font-size: 14pt;")
            layout.addWidget(label)

        return box

    def _build_pi_readings_box(self):
        """Build the row of labels showing the latest PI step: the error,
        both terms, the integral, the requested (unclamped) command, the
        applied (clamped, signed) command, and whether anti-windup held q.
        """
        box = QtWidgets.QGroupBox("PI Terms (latest step)")
        layout = QtWidgets.QHBoxLayout(box)

        self.pi_error_label = QtWidgets.QLabel("e: -- C")
        self.p_term_label = QtWidgets.QLabel("u_P: --")
        self.i_term_label = QtWidgets.QLabel("u_I: --")
        self.integral_label = QtWidgets.QLabel("q: 0.00 C*s")
        self.u_requested_label = QtWidgets.QLabel("Requested u: --")
        self.u_applied_label = QtWidgets.QLabel("Applied u: --")
        self.integrator_label = QtWidgets.QLabel("Integrator: --")

        labels = (
            self.pi_error_label,
            self.p_term_label,
            self.i_term_label,
            self.integral_label,
            self.u_requested_label,
            self.u_applied_label,
            self.integrator_label,
        )
        for label in labels:
            label.setStyleSheet("font-size: 12pt;")
            layout.addWidget(label)

        return box

    def _build_mode_box(self):
        """Build the Manual/PI Control switch. Only one mode drives the
        Arduino at a time - the other mode's widgets stay visible (and, for
        the PI setpoint/gains, editable) but don't send anything.
        """
        box = QtWidgets.QGroupBox("Control Mode")
        layout = QtWidgets.QHBoxLayout(box)

        self.manual_mode_radio = QtWidgets.QRadioButton("Manual")
        self.pi_mode_radio = QtWidgets.QRadioButton("PI Control")
        self.manual_mode_radio.setChecked(True)  # start open-loop, same as Module 4
        self.mode_button_group = QtWidgets.QButtonGroup(self)
        self.mode_button_group.addButton(self.manual_mode_radio)
        self.mode_button_group.addButton(self.pi_mode_radio)
        layout.addWidget(self.manual_mode_radio)
        layout.addWidget(self.pi_mode_radio)
        self.pi_mode_radio.toggled.connect(self.on_mode_changed)

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

    def _build_pi_control_box(self):
        """Build the setpoint, Kp, and Ki inputs plus the integral reset
        button. Editable regardless of the current mode, but only actually
        drives the Arduino while Control Mode is PI Control.
        """
        self.pi_control_box = QtWidgets.QGroupBox("PI Control")
        box_layout = QtWidgets.QVBoxLayout(self.pi_control_box)
        layout = QtWidgets.QHBoxLayout()
        box_layout.addLayout(layout)

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
        layout.addWidget(QtWidgets.QLabel("u = Kp*e + Ki*q; sign(u) -> direction, |u| -> PWM"))

        # --- Ki slider + text box ------------------------------------------
        # QSlider only holds integers, so it stores Ki * KI_SLIDER_SCALE.
        # The two widgets are kept in sync the same way as the PWM slider and
        # text box, with signals blocked so neither re-triggers the other.
        ki_layout = QtWidgets.QHBoxLayout()
        box_layout.addLayout(ki_layout)

        self.ki_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.ki_slider.setMinimum(round(KI_MIN * KI_SLIDER_SCALE))
        self.ki_slider.setMaximum(round(KI_MAX * KI_SLIDER_SCALE))
        self.ki_slider.setValue(round(DEFAULT_KI * KI_SLIDER_SCALE))
        self.ki_slider.valueChanged.connect(self.on_ki_slider_moved)

        self.ki_spinbox = QtWidgets.QDoubleSpinBox()
        self.ki_spinbox.setRange(KI_MIN, KI_MAX)
        self.ki_spinbox.setDecimals(KI_DECIMALS)
        self.ki_spinbox.setSingleStep(1 / KI_SLIDER_SCALE)
        self.ki_spinbox.setValue(DEFAULT_KI)
        self.ki_spinbox.valueChanged.connect(self.on_ki_spinbox_changed)

        self.reset_integral_button = QtWidgets.QPushButton("Reset integral (q = 0)")
        self.reset_integral_button.clicked.connect(self.reset_integral)

        # Checkable: while pressed, Ki is forced to 0 and its slider/text box
        # are grayed out, so the controller is P-only.
        self.p_only_button = QtWidgets.QPushButton("P Control (Ki = 0)")
        self.p_only_button.setCheckable(True)
        self.p_only_button.toggled.connect(self.on_p_only_toggled)

        ki_layout.addWidget(QtWidgets.QLabel(f"Ki ({KI_MIN:g}-{KI_MAX:g}):"))
        ki_layout.addWidget(self.ki_slider)
        ki_layout.addWidget(self.ki_spinbox)
        ki_layout.addWidget(self.p_only_button)
        ki_layout.addWidget(self.reset_integral_button)

        return self.pi_control_box

    def _build_temperature_plot(self):
        self.temperature_plot = pg.PlotWidget()
        self.temperature_plot.setBackground("w")
        self.temperature_plot.setLabel("left", "Temperature", units="C")
        self.temperature_plot.setLabel("bottom", "Time", units="s")
        self.temperature_plot.showGrid(x=True, y=True)
        # The legend must exist before the curves so plot(name=...) adds them.
        # Four columns keeps its seven entries to two short rows.
        self.temperature_plot.addLegend(colCount=4, **LEGEND_OPTIONS)

        # One curve per thermistor, with the fixed label/color/width from
        # TEMPERATURE_TRACES. self.temperature_curves["rod4_C"] is rod 4's
        # curve; redraw_plots() feeds it temperature_history["rod4_C"].
        self.temperature_curves = {}
        for field_name, label_text, color in TEMPERATURE_TRACES:
            width = TEC_TRACE_WIDTH if field_name == "tec_C" else ROD_TRACE_WIDTH
            self.temperature_curves[field_name] = self.temperature_plot.plot(
                pen=pg.mkPen(color=color, width=width), name=label_text
            )
        self.setpoint_curve = self.temperature_plot.plot(
            pen=pg.mkPen(color="g", width=2, style=QtCore.Qt.DashLine), name="Setpoint"
        )
        return self.temperature_plot

    def _build_pwm_plot(self):
        """Build the PWM strip chart, drawn as two curves so the line color
        reflects the direction that was active at each point in time:
        solid red while heating, solid blue while cooling.
        """
        self.pwm_plot = pg.PlotWidget()
        self.pwm_plot.setBackground("w")
        self.pwm_plot.setLabel("left", "PWM", units="")
        self.pwm_plot.setLabel("bottom", "Time", units="s")
        self.pwm_plot.showGrid(x=True, y=True)
        self.pwm_plot.setYRange(PWM_MIN, PWM_MAX, padding=0)
        # The legend must exist before the curves so plot(name=...) adds them.
        self.pwm_plot.addLegend(**LEGEND_OPTIONS)
        self.pwm_heat_curve = self.pwm_plot.plot(
            pen=pg.mkPen(color="r", width=2), name="Heating"
        )
        self.pwm_cool_curve = self.pwm_plot.plot(
            pen=pg.mkPen(color="b", width=2), name="Cooling"
        )
        return self.pwm_plot

    def _build_error_plot(self):
        """Build the error (Tset - T) strip chart with u_P and u_I drawn
        alongside it. Error is in C on the left axis; u_P and u_I are in PWM
        counts on the right axis, in a second ViewBox that shares the time
        axis. redraw_plots() keeps both y ranges symmetric about zero, so the
        dashed zero line is zero on both axes.
        """
        self.error_plot = pg.PlotWidget()
        self.error_plot.setBackground("w")
        plot_item = self.error_plot.getPlotItem()
        plot_item.setLabel("left", "Error (Tset - T)", units="C")
        plot_item.setLabel("bottom", "Time", units="s")
        plot_item.showGrid(x=True, y=True)
        zero_line = pg.InfiniteLine(
            pos=0, angle=0, pen=pg.mkPen(color=(128, 128, 128), style=QtCore.Qt.DashLine)
        )
        plot_item.addItem(zero_line)

        legend = plot_item.addLegend(**LEGEND_OPTIONS)
        self.error_curve = plot_item.plot(
            pen=pg.mkPen(color="orange", width=2), name="Error e"
        )

        self.u_viewbox = pg.ViewBox()
        plot_item.showAxis("right")
        plot_item.scene().addItem(self.u_viewbox)
        plot_item.getAxis("right").linkToView(self.u_viewbox)
        plot_item.getAxis("right").setLabel("u_P, u_I (PWM)")
        self.u_viewbox.setXLink(plot_item)
        self.u_viewbox.setZValue(plot_item.vb.zValue() + 1)

        def match_main_viewbox():
            self.u_viewbox.setGeometry(plot_item.vb.sceneBoundingRect())
            self.u_viewbox.linkedViewChanged(plot_item.vb, self.u_viewbox.XAxis)

        plot_item.vb.sigResized.connect(match_main_viewbox)

        # connect="finite" leaves gaps at the NaNs logged for Manual mode.
        # u_P = Kp * e has the same shape as e, so it is dashed and drawn on
        # top of the error curve; otherwise it can hide exactly behind it.
        self.p_term_curve = pg.PlotDataItem(
            pen=pg.mkPen(color=(128, 0, 160), width=2, style=QtCore.Qt.DashLine),
            connect="finite",
        )
        self.i_term_curve = pg.PlotDataItem(
            pen=pg.mkPen(color=(0, 140, 140), width=2), connect="finite"
        )
        self.u_viewbox.addItem(self.p_term_curve)
        self.u_viewbox.addItem(self.i_term_curve)
        # These curves live in the second ViewBox, so add them to the legend
        # by hand.
        legend.addItem(self.p_term_curve, "u_P = Kp*e")
        legend.addItem(self.i_term_curve, "u_I = Ki*q")
        return self.error_plot

    # -----------------------------------------------------------------
    # Serial command sending
    # -----------------------------------------------------------------
    def send_current_settings(self):
        """Queue the currently selected PWM value and direction as one
        command line, e.g. "SET PWM 120 DIR HEAT". The PWM value and
        direction always travel together in a single command so the Arduino
        never receives one without the other.
        """
        command = f"SET PWM {self.current_pwm} DIR {self.current_direction}"
        if not self.reader.send_command(command):
            print(f"Not sent (port not open): {command}")

    @QtCore.Slot(str)
    def on_command_sent(self, command):
        # Printed only after the reader thread has actually written the line.
        print(f"Sent: {command}")

    @QtCore.Slot(int)
    def on_commands_dropped(self, count):
        print(f"Not sent (port closed): {count} queued command(s) discarded")

    def apply_pwm(self, value):
        """Clamp a requested PWM value, then keep the slider, the text box,
        and self.current_pwm all in agreement before sending it out. Only
        called from the Manual-mode widgets, which are disabled while PI
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
        when compute_pi_control() wants the GUI to show what it just
        commanded (PI mode), so the panel always shows the truth.
        """
        # blockSignals stops these widgets from firing their own
        # "value changed" signals while we set them programmatically, which
        # would otherwise cause an infinite slider <-> text box update loop
        # (or re-entrant sends in PI mode).
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
        # Drags emit many value changes; the timer sends the latest value once
        # per interval instead of one command per tick.
        self.current_pwm = clamp_pwm(int(value))
        self.pwm_edit.blockSignals(True)
        self.pwm_edit.setText(str(self.current_pwm))
        self.pwm_edit.blockSignals(False)
        if not self.manual_send_timer.isActive():
            self.manual_send_timer.start()

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

    @QtCore.Slot(int)
    def on_ki_slider_moved(self, value):
        self.ki_spinbox.blockSignals(True)
        self.ki_spinbox.setValue(value / KI_SLIDER_SCALE)
        self.ki_spinbox.blockSignals(False)

    @QtCore.Slot(float)
    def on_ki_spinbox_changed(self, value):
        self.ki_slider.blockSignals(True)
        self.ki_slider.setValue(round(value * KI_SLIDER_SCALE))
        self.ki_slider.blockSignals(False)

    @QtCore.Slot(bool)
    def on_p_only_toggled(self, p_only):
        """Turn P-only control on (Ki -> 0, Ki widgets grayed out) or off
        (Ki restored to its value before P-only was turned on). q is reset
        either way, so a stale integral never kicks in when Ki comes back.
        """
        if p_only:
            self.saved_ki = self.ki_spinbox.value()
            self.ki_spinbox.setValue(0.0)  # on_ki_spinbox_changed moves the slider too
        else:
            self.ki_spinbox.setValue(self.saved_ki)
        self.ki_slider.setEnabled(not p_only)
        self.ki_spinbox.setEnabled(not p_only)
        self.reset_integral()

    @QtCore.Slot()
    def reset_integral(self):
        """Set q = 0, e.g. before starting a new comparison run. The dt
        reference is kept, so the next step still integrates over the real
        time since the previous measurement.
        """
        self.integral = 0.0
        self.integral_label.setText(f"q: {self.integral:.2f} C*s")
        print("Integral reset: q = 0")

    @QtCore.Slot(bool)
    def on_mode_changed(self, pi_is_checked):
        self.control_mode = "PI" if pi_is_checked else "MANUAL"
        # Manual widgets are disabled in PI mode so the two controllers can
        # never fight over the same serial link.
        self.manual_control_box.setEnabled(not pi_is_checked and self.reader.is_connected)
        # Each PI run starts from q = 0 with no previous sample, so time
        # spent in Manual mode is never integrated.
        self.previous_pi_time_s = None
        if pi_is_checked:
            self.reset_integral()
        else:
            # Switching back to Manual: resume from whatever the slider/
            # radio buttons are currently showing, rather than leaving the
            # Arduino running on the last PWM computed by the PI controller.
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
    # PI control
    # -----------------------------------------------------------------
    def compute_pi_control(self, time_s, temperature_c):
        """PI control law, run once per incoming (already
        1000-sample-averaged) temperature measurement while Control Mode is
        PI Control:

            e_n   = Tset - T_n
            q_n+1 = q_n + e_n * dt_n     (unless anti-windup holds it)
            u_n   = Kp * e_n + Ki * q_n+1

        dt_n is the Arduino time since the previous accepted measurement
        (0 on the first PI step, and never negative).

        Conditional integration: the command requested with the old
        integral, Kp * e_n + Ki * q_n, is checked first. If it is already
        beyond the PWM limit and e_n has the same sign (integrating would
        push it farther into saturation), q is not updated on this step.

        The sign of u becomes the direction (u >= 0 -> HEAT, since a
        positive error means we're colder than the setpoint; u < 0 -> COOL),
        and |u| becomes the PWM magnitude, rounded to the nearest integer
        and clamped to 0-255 before being sent to the Arduino.

        Returns a dict of everything the caller logs and displays; the send
        itself already happened here.
        """
        setpoint = self.setpoint_spinbox.value()
        kp = self.kp_spinbox.value()
        ki = self.ki_spinbox.value()
        error = setpoint - temperature_c

        if self.previous_pi_time_s is None:
            dt = 0.0
        else:
            dt = max(0.0, time_s - self.previous_pi_time_s)
        self.previous_pi_time_s = time_s

        u_before = kp * error + ki * self.integral
        integral_held = abs(u_before) > PWM_MAX and error * u_before > 0
        if not integral_held:
            self.integral += error * dt

        p_term = kp * error
        i_term = ki * self.integral
        u_requested = p_term + i_term

        direction = "HEAT" if u_requested >= 0 else "COOL"
        pwm_magnitude = clamp_pwm(int(round(abs(u_requested))))
        u_applied = pwm_magnitude if direction == "HEAT" else -pwm_magnitude

        self.current_pwm = pwm_magnitude
        self.current_direction = direction
        self._sync_manual_widgets(pwm_magnitude, direction)
        self.send_current_settings()

        return {
            "setpoint": setpoint,
            "error": error,
            "kp": kp,
            "ki": ki,
            "dt": dt,
            "p_term": p_term,
            "i_term": i_term,
            "integral": self.integral,
            "integral_held": integral_held,
            "u_requested": u_requested,
            "u_applied": u_applied,
        }

    # -----------------------------------------------------------------
    # Incoming measurements + plot updates
    # -----------------------------------------------------------------
    @QtCore.Slot(str)
    def on_line_rejected(self, text):
        self.rejected_line_count += 1
        self.rejected_count_label.setText(f"Rejected: {self.rejected_line_count}")
        self.last_rejected_label.setText(f"Last rejected: {text[:60]}")

    @QtCore.Slot(dict)
    def on_measurement(self, record):
        """Runs once for every accepted DATA record, in this order:
        write the raw CSV row, run the PI step, store the values for the
        plots, update the live readouts, write the PI log row.
        """
        self.accepted_line_count += 1
        self.accepted_count_label.setText(f"Accepted: {self.accepted_line_count}")

        # ----- 1. Raw CSV: the record exactly as the Arduino sent it -----
        # record["raw"] maps each of the 11 column names to the original
        # text, so the file holds exactly what came over the serial line:
        # no rounding, no unit changes, no calibration.
        self.raw_csv_writer.writerow(record["raw"])
        # flush() hands the row to the operating system right away instead
        # of letting Python hold it in memory, so if the GUI crashes or is
        # killed every row written so far is already in the file. At about
        # one record per 0.75 s this costs nothing noticeable.
        self.raw_csv_file.flush()

        time_s = record["time_s"]
        temperature_c = record["tec_C"]  # TEC-base thermistor: the only feedback channel
        pwm = record["pwm"]
        heat_cool = record["heat_cool"]
        safety = record["safety"]
        tec_valid = math.isfinite(temperature_c)

        # ----- 2. PI control (uses tec_C only) -----
        pi = None
        setpoint = self.setpoint_spinbox.value()
        if self.control_mode == "PI" and tec_valid:
            pi = self.compute_pi_control(time_s, temperature_c)
            setpoint, error = pi["setpoint"], pi["error"]
        else:
            # Manual mode still drives nothing off temperature, but we keep
            # computing/showing setpoint and error against the current
            # spinbox values so they're ready to read the moment you switch
            # to PI Control. With no valid TEC reading (sensor fault) there
            # is no error to act on: the PI step is skipped (the Arduino has
            # already forced the output off), and the next valid step starts
            # over at dt = 0 so the fault's duration isn't integrated.
            error = setpoint - temperature_c  # NaN when tec_C is NaN
            if not tec_valid:
                self.previous_pi_time_s = None

        direction = DIRECTION_LABELS[heat_cool]

        # ----- 3. Data storage for the plots -----
        # Exactly one entry per list per record (see __init__). A NaN
        # temperature is stored as NaN, which pyqtgraph draws as a gap.
        self.times.append(time_s)
        for name in TEMPERATURE_FIELDNAMES:
            self.temperature_history[name].append(record[name])
        self.pwms.append(pwm)
        self.directions.append(direction)
        self.setpoints.append(setpoint)
        self.errors.append(error)
        self.p_terms.append(pi["p_term"] if pi is not None else float("nan"))
        self.i_terms.append(pi["i_term"] if pi is not None else float("nan"))

        # ----- 4. Live readouts -----
        for field_name, label_text, _color in TEMPERATURE_TRACES:
            value = record[field_name]
            shown = f"{value:.2f}" if math.isfinite(value) else "FAULT"
            self.temperature_labels[field_name].setText(f"{label_text}: {shown}")

        if tec_valid:
            self.error_label.setText(f"Error: {error:+.2f} C")
            self.pi_error_label.setText(f"e: {error:+.2f} C")
        else:
            self.error_label.setText("Error: -- C")
            self.pi_error_label.setText("e: -- C")
        self.pwm_label.setText(f"PWM: {pwm}")
        self.direction_label.setText(f"Direction: {direction}")
        self.setpoint_label.setText(f"Setpoint: {setpoint:.2f} C")
        self.safety_label.setText(f"Safety: {safety}")
        self.safety_label.setStyleSheet(
            "font-size: 14pt;" + ("" if safety == "OK" else " color: red; font-weight: bold;")
        )
        self.time_label.setText(f"Time: {time_s:.2f} s")

        # ----- 5. PI log: what this script computed for this record -----
        row = {
            "time_s": record["raw"]["time_s"],  # same text as the raw file, so rows join exactly
            "tec_C": record["raw"]["tec_C"],
            "mode": self.control_mode,
            "setpoint_C": setpoint,
            "kp": self.kp_spinbox.value(),
            "error_C": error,
        }
        if pi is not None:
            self.p_term_label.setText(f"u_P: {pi['p_term']:+.1f}")
            self.i_term_label.setText(f"u_I: {pi['i_term']:+.1f}")
            self.integral_label.setText(f"q: {pi['integral']:.2f} C*s")
            self.u_requested_label.setText(f"Requested u: {pi['u_requested']:+.1f}")
            self.u_applied_label.setText(f"Applied u: {pi['u_applied']:+d}")
            self.integrator_label.setText(
                "Integrator: HELD" if pi["integral_held"] else "Integrator: running"
            )
            row.update({
                "ki": pi["ki"],
                "dt_s": pi["dt"],
                "p_term": pi["p_term"],
                "i_term": pi["i_term"],
                "integral_C_s": pi["integral"],
                "integral_held": int(pi["integral_held"]),
                "u_requested": pi["u_requested"],
                "u_applied": pi["u_applied"],
            })
        self.pi_log_writer.writerow(row)
        self.pi_log_file.flush()

    def redraw_plots(self):
        """Runs on a timer (see PLOT_UPDATE_INTERVAL_MS) to redraw all three
        strip charts and drop any data older than STRIP_CHART_WINDOW_S.
        """
        if not self.times:
            return

        latest_time = self.times[-1]
        window_start = latest_time - STRIP_CHART_WINDOW_S

        # Drop old samples that have scrolled off the left edge of the chart.
        # Every list loses its first entry together, so they stay lined up.
        while self.times and self.times[0] < window_start:
            self.times.pop(0)
            for history in self.temperature_history.values():
                history.pop(0)
            self.pwms.pop(0)
            self.directions.pop(0)
            self.setpoints.pop(0)
            self.errors.pop(0)
            self.p_terms.pop(0)
            self.i_terms.pop(0)

        # ----- Plot updates -----
        # Each temperature curve gets the history list with the SAME field
        # name it was created for, against the shared Arduino time list.
        for name in TEMPERATURE_FIELDNAMES:
            self.temperature_curves[name].setData(self.times, self.temperature_history[name])
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
        self.p_term_curve.setData(self.times, self.p_terms)
        self.i_term_curve.setData(self.times, self.i_terms)

        # Both y axes are symmetric about zero so the zero line is shared.
        # The u axis gets more headroom than the error axis so u_P, which is
        # a scaled copy of e, sits visibly inside the error curve, not on it.
        # NaN values (faults, Manual-mode PI terms) are skipped.
        finite_errors = [abs(e) for e in self.errors if math.isfinite(e)]
        error_extent = max(0.5, max(finite_errors, default=0.0)) * 1.1
        finite_terms = [abs(u) for u in self.p_terms + self.i_terms if math.isfinite(u)]
        term_extent = max(1.0, max(finite_terms, default=0.0)) * 1.5
        self.error_plot.setYRange(-error_extent, error_extent, padding=0)
        self.u_viewbox.setYRange(-term_extent, term_extent, padding=0)

        # The temperature axis follows the TEC and rod samples still visible
        # in the rolling window. This makes small temperature changes easier
        # to see. If every visible sample is NaN, the axis is left as it is.
        visible_temperatures = [
            value
            for history in self.temperature_history.values()
            for value in history
            if math.isfinite(value)
        ]
        if visible_temperatures:
            lowest_temperature = min(visible_temperatures)
            highest_temperature = max(visible_temperatures)
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
        self.raw_csv_file.close()
        self.pi_log_file.close()
        super().closeEvent(event)


def main():
    port = SERIAL_PORT or find_default_port()

    app = QtWidgets.QApplication(sys.argv)
    window = TemperaturePlotWindow(port, BAUD_RATE)
    window.resize(1050, 1000)
    window.show()
    sys.exit(app.exec())


# Run with:
#   cd "/Users/joshbub/Documents/PHYS39A_Repo/PHY39A_repo/Module 7" && venv/bin/python Python/serial_plot_mod7.py
if __name__ == "__main__":
    main()
