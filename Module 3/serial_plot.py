"""Read the Switch_Control sketch's serial output and plot temperature vs. time.

Expects lines in the form:
    Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1

This is a display-only tool: it only ever reads from the serial port and
never writes to it, so it cannot send commands to the Arduino.
"""

import csv
import re
import sys

import serial
import serial.tools.list_ports
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERIAL_PORT = "/dev/cu.usbmodem101"  # e.g. "/dev/tty.usbmodem1101"; None = auto-detect
BAUD_RATE = 9600

STRIP_CHART_WINDOW_S = 60.0  # seconds of history visible on the plot
PLOT_UPDATE_INTERVAL_MS = 100  # how often the plot redraws

TEMPERATURE_AXIS_MIN_C = 0.0
TEMPERATURE_AXIS_MAX_C = 50.0

OUTPUT_CSV_FILENAME = "temperature_log.csv"
# ---------------------------------------------------------------------------

LINE_PATTERN = re.compile(
    r"Temperature \(C\):\s*(?P<temperature>-?\d+\.?\d*),\s*"
    r"Time \(s\):\s*(?P<time>-?\d+\.?\d*),\s*"
    r"PWM:\s*(?P<pwm>\d+),\s*"
    r"Heat/Cool:\s*(?P<heat_cool>[01])"
)

CSV_FIELDNAMES = ["time_s", "temperature_C", "pwm", "heat_cool"]


def find_default_port():
    ports = list(serial.tools.list_ports.comports())
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        sys.exit("No serial ports found. Connect the Arduino or set SERIAL_PORT.")
    port_list = "\n".join(f"  {p.device} ({p.description})" for p in ports)
    sys.exit(f"Multiple serial ports found, set SERIAL_PORT to one of:\n{port_list}")


class SerialReader(QtCore.QThread):
    measurement = QtCore.Signal(float, float, int, int)
    error = QtCore.Signal(str)

    def __init__(self, port, baud_rate, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud_rate = baud_rate
        self._running = True

    def run(self):
        try:
            with serial.Serial(self._port, self._baud_rate, timeout=1) as connection:
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

    def stop(self):
        self._running = False
        self.wait()


class TemperaturePlotWindow(QtWidgets.QMainWindow):
    def __init__(self, port, baud_rate):
        super().__init__()
        self.setWindowTitle(f"TEC Temperature Monitor (display-only) - {port}")

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "Temperature", units="C")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setYRange(TEMPERATURE_AXIS_MIN_C, TEMPERATURE_AXIS_MAX_C, padding=0)
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color="r", width=2))
        self.setCentralWidget(self.plot_widget)

        self.times = []
        self.temperatures = []

        self.csv_file = open(OUTPUT_CSV_FILENAME, "w", newline="")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=CSV_FIELDNAMES)
        self.csv_writer.writeheader()

        self.redraw_timer = QtCore.QTimer(self)
        self.redraw_timer.timeout.connect(self.redraw_plot)
        self.redraw_timer.start(PLOT_UPDATE_INTERVAL_MS)

        self.reader = SerialReader(port, baud_rate)
        self.reader.measurement.connect(self.on_measurement)
        self.reader.error.connect(self.on_error)
        self.reader.start()

    @QtCore.Slot(float, float, int, int)
    def on_measurement(self, time_s, temperature_c, pwm, heat_cool):
        self.times.append(time_s)
        self.temperatures.append(temperature_c)

        self.csv_writer.writerow({
            "time_s": time_s,
            "temperature_C": temperature_c,
            "pwm": pwm,
            "heat_cool": heat_cool,
        })
        self.csv_file.flush()

    def redraw_plot(self):
        if not self.times:
            return

        latest_time = self.times[-1]
        window_start = latest_time - STRIP_CHART_WINDOW_S

        while self.times and self.times[0] < window_start:
            self.times.pop(0)
            self.temperatures.pop(0)

        self.curve.setData(self.times, self.temperatures)
        self.plot_widget.setXRange(window_start, latest_time, padding=0)

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
    window.resize(900, 500)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
