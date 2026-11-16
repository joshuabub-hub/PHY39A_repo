import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import serial_plot_mod8 as gui


class Value:
    def __init__(self, value):
        self.value_ = value

    def value(self):
        return self.value_

    def isChecked(self):
        return self.value_


class FakeController:
    compute_pi_control = gui.TemperaturePlotWindow.compute_pi_control
    compute_corrected_control = gui.TemperaturePlotWindow.compute_corrected_control

    def __init__(self):
        self.control_mode = "PI"
        self.cooling_ratio = 4.0
        self.susceptibility_curve = gui.load_susceptibility_curve(gui.STEADY_STATE_CSV)
        self.room_spinbox = Value(26.01)
        self.ff_checkbox = Value(False)
        self.kp_spinbox = Value(10.0)
        self.ki_spinbox = Value(1.0)
        self.raw_ua_spinbox = Value(20.0)
        self.raw_ub_spinbox = Value(10.0)
        self.period_spinbox = Value(100.0)
        self.waveform_button = Value(True)
        self.waveform_start_s = 0.0
        self.previous_pi_time_s = 0.0
        self.integral = 0.0
        self.setpoint = 25.0
        self.commands = []

    def current_setpoint(self, time_s):
        return self.setpoint

    def _sync_manual_widgets(self, pwm, direction):
        pass

    def send_current_settings(self):
        self.commands.append((self.current_pwm, self.current_direction))


class ControllerTests(unittest.TestCase):
    def test_interpolation_shift_and_outside_range(self):
        curve = gui.load_susceptibility_curve(gui.STEADY_STATE_CSV)
        self.assertAlmostEqual(gui.interpolate_feedforward(30.0, 30.0, curve), 0)
        self.assertAlmostEqual(gui.interpolate_feedforward(42.66, 30.0, curve), 23)
        self.assertAlmostEqual(gui.interpolate_feedforward(28.26, 30.0, curve), -14.5)
        with self.assertRaises(ValueError):
            gui.interpolate_feedforward(70, 30, curve)

    def test_cooling_compensation_and_anti_windup(self):
        controller = FakeController()
        result = controller.compute_pi_control(1, 26)
        self.assertEqual(result["u_requested"], -11)
        self.assertEqual(controller.commands[-1], (44, "COOL"))
        controller.kp_spinbox = Value(100)
        controller.integral = 0
        result = controller.compute_pi_control(2, 26)
        self.assertTrue(result["integral_held"])
        self.assertEqual(controller.integral, 0)
        self.assertEqual(controller.commands[-1], (255, "COOL"))

    def test_feedforward_is_not_double_compensated(self):
        controller = FakeController()
        controller.ff_checkbox = Value(True)
        controller.kp_spinbox = Value(0)
        controller.ki_spinbox = Value(0)
        controller.setpoint = 22.53
        result = controller.compute_pi_control(1, 22.53)
        self.assertAlmostEqual(result["u_ff"], -29)
        self.assertEqual(controller.commands[-1], (29, "COOL"))

    def test_diagnostic_modes_ignore_compensation(self):
        controller = FakeController()
        controller.control_mode = "RAW_AC"
        controller.compute_pi_control(75, 25)
        self.assertEqual(controller.commands[-1], (10, "COOL"))
        controller.control_mode = "RAW_HEAT"
        controller.compute_pi_control(75, 25)
        self.assertEqual(controller.commands[-1], (10, "HEAT"))

    def test_symmetric_pwm_at_requested_periods(self):
        for period in (100, 200, 500):
            with self.subTest(period=period):
                controller = FakeController()
                controller.control_mode = "RAW_AC"
                controller.period_spinbox = Value(period)
                controller.raw_ub_spinbox = Value(100.0)
                controller.raw_ua_spinbox = Value(80.0)
                for fraction, expected in ((0, (0, "HEAT")),
                                           (0.25, (100, "HEAT")),
                                           (0.5, (0, "HEAT")),
                                           (0.75, (100, "COOL")),
                                           (1, (0, "COOL"))):
                    controller.compute_pi_control(period * fraction, 25)
                    self.assertEqual(controller.commands[-1], expected)

    def test_record_validation(self):
        record = gui.parse_data_record("DATA,1.00,24,24,24,24,24,24,12,1,nan,OK")
        self.assertEqual(record["pwm"], 12)
        self.assertTrue(math.isnan(float(record["raw"]["setpoint_C"])))
        self.assertIsNone(gui.parse_data_record("DATA,1,24"))
        self.assertIsNone(gui.parse_data_record("DATA,1,24,24,24,24,24,24,300,1,nan,OK"))


class FakeReader(gui.QtCore.QObject):
    measurement = gui.QtCore.Signal(dict)
    line_rejected = gui.QtCore.Signal(str)
    connected = gui.QtCore.Signal()
    error = gui.QtCore.Signal(str)
    command_sent = gui.QtCore.Signal(str)
    commands_dropped = gui.QtCore.Signal(int)

    def __init__(self, port, baud_rate):
        super().__init__()
        self.is_connected = True
        self.commands = []

    def start(self):
        pass

    def send_command(self, command):
        self.commands.append(command)
        return True

    def stop(self):
        pass


class GuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QtWidgets.QApplication.instance() or gui.QtWidgets.QApplication([])

    def test_raw_mode_and_return_to_manual_zero_output(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(gui, "SerialReader", FakeReader), patch.object(gui, "DATA_DIR", Path(directory)):
                window = gui.TemperaturePlotWindow("test", 9600)
                try:
                    window.mode_radios["RAW_AC"].setChecked(True)
                    window.raw_ub_spinbox.setValue(20)
                    window.waveform_button.setChecked(True)
                    record = gui.parse_data_record("DATA,1.00,24,24,24,24,24,24,0,0,nan,OK")
                    window.on_measurement(record)
                    record = gui.parse_data_record("DATA,76.00,24,24,24,24,24,24,0,0,nan,OK")
                    window.on_measurement(record)
                    self.assertIn("SET PWM 20 DIR COOL", window.reader.commands)
                    window.mode_radios["MANUAL"].setChecked(True)
                    self.assertEqual(window.reader.commands[-1], "SET PWM 0 DIR COOL")
                finally:
                    window.close()

    def test_pwm_mode_ignores_temperature_waveform_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(gui, "SerialReader", FakeReader), patch.object(gui, "DATA_DIR", Path(directory)):
                window = gui.TemperaturePlotWindow("test", 9600)
                try:
                    window.ta_spinbox.setValue(60)
                    self.assertFalse(window.waveform_button.isEnabled())
                    window.mode_radios["RAW_AC"].setChecked(True)
                    window.raw_ub_spinbox.setValue(100)
                    window.period_spinbox.setValue(200)
                    self.assertTrue(window.waveform_button.isEnabled())
                    self.assertIn("-100 to 100 PWM", window.ff_info_label.text())
                    window.waveform_button.setChecked(True)
                    for t in (0, 50, 150):
                        record = gui.parse_data_record(f"DATA,{t},24,24,24,24,24,24,0,0,nan,OK")
                        window.on_measurement(record)
                    self.assertIn("SET PWM 100 DIR HEAT", window.reader.commands)
                    self.assertIn("SET PWM 100 DIR COOL", window.reader.commands)
                    window.waveform_button.setChecked(False)
                    self.assertEqual(window.reader.commands[-1], "SET PWM 0 DIR COOL")
                    window.mode_radios["P"].setChecked(True)
                    self.assertFalse(window.waveform_button.isEnabled())
                finally:
                    window.close()

    def test_out_of_range_feedforward_stops_control(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(gui, "SerialReader", FakeReader), patch.object(gui, "DATA_DIR", Path(directory)):
                window = gui.TemperaturePlotWindow("test", 9600)
                try:
                    window.room_spinbox.setValue(20)
                    window.setpoint_spinbox.setValue(50)
                    window.mode_radios["OPEN"].setChecked(True)
                    record = gui.parse_data_record("DATA,1.00,24,24,24,24,24,24,0,0,nan,OK")
                    window.on_measurement(record)
                    self.assertEqual(window.control_mode, "MANUAL")
                    self.assertEqual(window.reader.commands[-1], "SET PWM 0 DIR COOL")
                    self.assertIn("outside the measured", window.last_rejected_label.text())
                finally:
                    window.close()


if __name__ == "__main__":
    unittest.main()
