"""Read the Switch_Control sketch's serial output, plot temperature and PWM
vs. time, and send open-loop PWM/direction commands back to the Arduino.

Incoming lines from the Arduino are expected in the form:
    Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1

Outgoing commands sent TO the Arduino look like:
    SET PWM 120 DIR HEAT
    SET PWM 45 DIR COOL

This tool does NOT do any feedback/closed-loop control on its own - it just
lets you pick a PWM value and a direction with the GUI, sends that exact
setting to the Arduino, and plots whatever the Arduino reports back.
"""

import csv
import re
import sys

import serial
import serial.tools.list_ports
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERIAL_PORT = "/dev/cu.usbmodem101"  # e.g. "/dev/tty.usbmodem1101"; None = auto-detect
BAUD_RATE = 9600

STRIP_CHART_WINDOW_S = 60.0  # seconds of history visible on the plots
PLOT_UPDATE_INTERVAL_MS = 100  # how often the plots redraw

TEMPERATURE_AXIS_MIN_C = 0.0
TEMPERATURE_AXIS_MAX_C = 50.0

PWM_MIN = 0
PWM_MAX = 255

OUTPUT_CSV_FILENAME = "data/temperature_log.csv"
# ---------------------------------------------------------------------------

LINE_PATTERN = re.compile(
    r"Temperature \(C\):\s*(?P<temperature>-?\d+\.?\d*),\s*"
    r"Time \(s\):\s*(?P<time>-?\d+\.?\d*),\s*"
    r"PWM:\s*(?P<pwm>\d+),\s*"
    r"Heat/Cool:\s*(?P<heat_cool>[01])"
)

CSV_FIELDNAMES = ["time_s", "temperature_C", "pwm", "heat_cool"]

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
        self.setWindowTitle(f"TEC Temperature & PWM Controller - {port}")

        # Current control-panel state (what we intend to send to the Arduino).
        self.current_pwm = 0
        self.current_direction = "COOL"

        # History lists used to draw the strip charts. Every new measurement
        # appends one entry to each of these, and old entries are dropped
        # once they scroll off the left edge of the window.
        self.times = []
        self.temperatures = []
        self.pwms = []
        self.directions = []  # "HEAT" or "COOL" for each sample, same length as above

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        main_layout.addWidget(self._build_live_readings_box())
        main_layout.addWidget(self._build_control_box())
        main_layout.addWidget(self._build_temperature_plot())
        main_layout.addWidget(self._build_pwm_plot())

        # Controls are disabled until the serial port actually opens, so we
        # can't try to write to a port that isn't ready yet.
        self.control_box.setEnabled(False)

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
        reported back by the Arduino (not just what we asked it to do).
        """
        box = QtWidgets.QGroupBox("Live Readings")
        layout = QtWidgets.QHBoxLayout(box)

        # QLabel is just a piece of text on screen. We keep a reference to
        # each one (self.temperature_label, etc.) so we can update its text
        # later whenever a new measurement arrives.
        self.temperature_label = QtWidgets.QLabel("Temperature: -- C")
        self.pwm_label = QtWidgets.QLabel("PWM: --")
        self.direction_label = QtWidgets.QLabel("Direction: --")
        self.time_label = QtWidgets.QLabel("Time: -- s")

        for label in (self.temperature_label, self.pwm_label, self.direction_label, self.time_label):
            label.setStyleSheet("font-size: 14pt;")
            layout.addWidget(label)

        return box

    def _build_control_box(self):
        """Build the heat/cool switch and the synchronized PWM slider + text box."""
        self.control_box = QtWidgets.QGroupBox("Controls")
        layout = QtWidgets.QHBoxLayout(self.control_box)

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

        return self.control_box

    def _build_temperature_plot(self):
        self.temperature_plot = pg.PlotWidget()
        self.temperature_plot.setLabel("left", "Temperature", units="C")
        self.temperature_plot.setLabel("bottom", "Time", units="s")
        self.temperature_plot.showGrid(x=True, y=True)
        self.temperature_plot.setYRange(TEMPERATURE_AXIS_MIN_C, TEMPERATURE_AXIS_MAX_C, padding=0)
        self.temperature_curve = self.temperature_plot.plot(pen=pg.mkPen(color="r", width=2))
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
        and self.current_pwm all in agreement before sending it out.
        """
        value = clamp_pwm(int(value))

        # blockSignals stops these widgets from firing their own
        # "value changed" signals while we set them programmatically, which
        # would otherwise cause an infinite slider <-> text box update loop.
        self.pwm_slider.blockSignals(True)
        self.pwm_slider.setValue(value)
        self.pwm_slider.blockSignals(False)

        self.pwm_edit.blockSignals(True)
        self.pwm_edit.setText(str(value))
        self.pwm_edit.blockSignals(False)

        self.current_pwm = value
        self.send_current_settings()

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

    @QtCore.Slot()
    def on_serial_connected(self):
        # Now that the port is open it's safe to write to it, so unlock the
        # controls and tell the Arduino our starting PWM/direction.
        self.control_box.setEnabled(True)
        self.send_current_settings()

    # -----------------------------------------------------------------
    # Incoming measurements + plot updates
    # -----------------------------------------------------------------
    @QtCore.Slot(float, float, int, int)
    def on_measurement(self, time_s, temperature_c, pwm, heat_cool):
        direction = DIRECTION_LABELS[heat_cool]

        self.times.append(time_s)
        self.temperatures.append(temperature_c)
        self.pwms.append(pwm)
        self.directions.append(direction)

        # Update the live readout labels with what the Arduino just reported.
        self.temperature_label.setText(f"Temperature: {temperature_c:.2f} C")
        self.pwm_label.setText(f"PWM: {pwm}")
        self.direction_label.setText(f"Direction: {direction}")
        self.time_label.setText(f"Time: {time_s:.2f} s")

        self.csv_writer.writerow({
            "time_s": time_s,
            "temperature_C": temperature_c,
            "pwm": pwm,
            "heat_cool": heat_cool,
        })
        self.csv_file.flush()

    def redraw_plots(self):
        """Runs on a timer (see PLOT_UPDATE_INTERVAL_MS) to redraw both
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

        self.temperature_curve.setData(self.times, self.temperatures)

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

        self.temperature_plot.setXRange(window_start, latest_time, padding=0)
        self.pwm_plot.setXRange(window_start, latest_time, padding=0)

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
    window.resize(950, 750)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
