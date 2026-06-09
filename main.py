import sys
import os
import time
import csv
import json
import copy
import numpy as np

import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QTableWidgetItem, QMessageBox, QDialog, QVBoxLayout
from PySide6.QtCore import QThread, Signal, QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QColor

from drivers.tonghui import TonghuiLCR
from drivers.hioki import HiokiDriver
from drivers.labjack_driver import LabJackDriver
from drivers.fins_plc import OmronFinsPlcDriver
from config.product_specs import SpecManager


# ==========================================
#   设置弹窗逻辑
# ==========================================
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        loader = QUiLoader()
        ui_file = QFile("settings.ui")
        if not ui_file.exists(): return
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()
        layout = QVBoxLayout(self)
        layout.addWidget(self.ui)
        layout.setContentsMargins(0, 0, 0, 0)
        self.resize(450, 350)
        self.setWindowTitle("通讯端口配置")


# ==========================================
#   核心测试线程
# ==========================================
class TestThread(QThread):
    finished_signal = Signal(dict)
    wave_render_signal = Signal(tuple)

    def __init__(self, lcr, hioki, labjack, sn, tasks, model_name, labjack_duration=1.0):
        super().__init__()
        self.lcr, self.hioki, self.labjack = lcr, hioki, labjack
        self.sn, self.tasks, self.model_name = sn, tasks, model_name
        self.labjack_duration = labjack_duration

    @staticmethod
    def _range_from_specs(specs, range_key, min_key, max_key, default_min, default_max):
        if range_key in specs and isinstance(specs[range_key], (list, tuple)) and len(specs[range_key]) >= 2:
            return float(specs[range_key][0]), float(specs[range_key][1])
        return float(specs.get(min_key, default_min)), float(specs.get(max_key, default_max))

    def run(self):
        specs = SpecManager.get_specs(self.model_name) or {}
        r_min, r_max = specs.get('R', [0.0, 999.0])
        l_min, l_max = specs.get('L', [0.0, 999.0])
        vp_min, vp_max = self._range_from_specs(specs, 'Vp', 'Vp_min', 'Vp_max', 4.0, 999.0)
        thd_min, thd_max = self._range_from_specs(specs, 'THD', 'THD_min', 'THD_max', 0.0, 5.0)

        result = {
            "sn": self.sn,
            "RL": {"val": "未测试", "pass": True},
            "Hioki": {"val": "未测试", "pass": True, "raw": 0.0},
            "U": {"val": "未测试", "pass": True},
            "V": {"val": "未测试", "pass": True},
            "W": {"val": "未测试", "pass": True},
            "Phase": {"val": "未测试", "pass": True, "raw_diffs": [0.0, 0.0, 0.0]},
            "is_pass": True,
            "R_raw": 0.0, "L_raw": 0.0,
            "BEMF": {
                "pass": True,
                "raw_peaks": [0.0, 0.0, 0.0],
                "raw_thds": [0.0, 0.0, 0.0],
                "raw_harmonics": [[0.0, 0.0, 0.0, 0.0] for _ in range(3)]
            }
        }

        # 1. 静态电阻电感
        if self.tasks.get('lcr'):
            raw = self.lcr.fetch_data()
            if raw:
                r_ok = r_min <= raw['R'] <= r_max
                l_ok = l_min <= raw['L'] <= l_max
                rl_str = f"R: {raw['R']:.4f} mΩ\n[{r_min}~{r_max}]\nL: {raw['L']:.4f} µH\n[{l_min}~{l_max}]"
                result["RL"] = {"val": rl_str, "pass": r_ok and l_ok}
                result["R_raw"] = float(raw['R'])
                result["L_raw"] = float(raw['L'])
                if not (r_ok and l_ok): result["is_pass"] = False
            else:
                result["RL"] = {"val": "通讯异常", "pass": False}
                result["is_pass"] = False
                self.lcr.is_connected = False

        # 2. 静态匝间
        if self.tasks.get('hioki'):
            try:
                table_id = specs.get('table_id', 1)
                if hasattr(self.hioki, 'run_test'):
                    res_h, data_dict = self.hioki.run_test(table_id)
                else:
                    if hasattr(self.hioki, 'switch_table') and not self.hioki.switch_table(table_id):
                        result["Hioki"] = {"val": "切表失败", "pass": False, "raw": 0.0}
                        result["is_pass"] = False
                        self.hioki.is_connected = False
                        self.finished_signal.emit(result)
                        return
                    time.sleep(0.8)
                    res_h, data_dict = self.hioki.get_data() if hasattr(self.hioki, 'get_data') else ("PASS", {})

                if res_h == "ERR":
                    err_msg = data_dict.get("Error", "通讯异常") if isinstance(data_dict, dict) else "通讯异常"
                    result["Hioki"] = {"val": err_msg, "pass": False, "raw": 0.0}
                    result["is_pass"] = False
                    self.hioki.is_connected = False
                else:
                    h_ok = (res_h == "PASS")
                    area_val = data_dict.get('AREA', 0.0)
                    try:
                        area_raw = float(area_val)
                    except (TypeError, ValueError):
                        area_raw = 0.0
                    result["Hioki"] = {"val": f"{area_val}", "pass": h_ok, "raw": area_raw}
                    if not h_ok: result["is_pass"] = False
            except Exception as e:
                result["Hioki"] = {"val": f"通讯异常: {e}", "pass": False, "raw": 0.0}
                result["is_pass"] = False
                self.hioki.is_connected = False

        # 3. 动态反电势
        if self.tasks.get('labjack'):
            if not self.labjack.is_connected:
                result["U"] = {"val": "设备未连接", "pass": False}
                result["V"] = {"val": "设备未连接", "pass": False}
                result["W"] = {"val": "设备未连接", "pass": False}
                result["Phase"]["pass"] = False
                result["BEMF"]["pass"] = False
                result["is_pass"] = False
            else:
                u, v, w = self.labjack.capture_data(self.labjack_duration)
                if u is not None and v is not None and w is not None and len(u) > 0:
                    self.wave_render_signal.emit((u, v, w))
                    thds, peaks, diffs, harmonics = self.labjack.analyze_phases(u, v, w)
                    h_u, h_v, h_w = harmonics

                    u_ok = (vp_min <= peaks[0] <= vp_max) and (thd_min <= thds[0] <= thd_max)
                    v_ok = (vp_min <= peaks[1] <= vp_max) and (thd_min <= thds[1] <= thd_max)
                    w_ok = (vp_min <= peaks[2] <= vp_max) and (thd_min <= thds[2] <= thd_max)

                    result["U"] = {
                        "val": f"Vp: {peaks[0]:.2f} V\nTHD: {thds[0]:.2f} %\n2345: {h_u[0]:.1f},{h_u[1]:.1f},{h_u[2]:.1f},{h_u[3]:.1f}",
                        "pass": u_ok}
                    result["V"] = {
                        "val": f"Vp: {peaks[1]:.2f} V\nTHD: {thds[1]:.2f} %\n2345: {h_v[0]:.1f},{h_v[1]:.1f},{h_v[2]:.1f},{h_v[3]:.1f}",
                        "pass": v_ok}
                    result["W"] = {
                        "val": f"Vp: {peaks[2]:.2f} V\nTHD: {thds[2]:.2f} %\n2345: {h_w[0]:.1f},{h_w[1]:.1f},{h_w[2]:.1f},{h_w[3]:.1f}",
                        "pass": w_ok}
                    result["Phase"] = {"val": f"UV: {diffs[0]:.1f}°\nVW: {diffs[1]:.1f}°\nWU: {diffs[2]:.1f}°",
                                       "pass": True, "raw_diffs": diffs}

                    bemf_ok = u_ok and v_ok and w_ok
                    result["BEMF"] = {"pass": bemf_ok, "raw_peaks": peaks, "raw_thds": thds, "raw_harmonics": harmonics}
                    if not bemf_ok: result["is_pass"] = False
                else:
                    result["U"] = {"val": "抓取失败", "pass": False}
                    result["V"] = {"val": "抓取失败", "pass": False}
                    result["W"] = {"val": "抓取失败", "pass": False}
                    result["Phase"]["pass"] = False
                    result["BEMF"]["pass"] = False
                    result["is_pass"] = False

        self.finished_signal.emit(result)


# ==========================================
#   自动模式后台轮询线程
# ==========================================
class AutoTestThread(QThread):
    log_signal = Signal(str)
    trigger_test_signal = Signal()

    def __init__(self, plc, ctrl_addr=100, res_addr=101):
        super().__init__()
        self.plc = plc
        self.is_running = True
        self.ctrl_addr = ctrl_addr
        self.res_addr = res_addr

    def run(self):
        self.log_signal.emit("进入全自动模式...")
        while self.is_running:
            if self.plc.is_connected:
                data, msg = self.plc.read_dm(self.ctrl_addr, 1)
                if data:
                    if self.plc.bytes_to_int16(data) == 1:
                        self.plc.write_dm_int16(self.res_addr, [3])
                        self.plc.write_dm_int16(self.ctrl_addr, [0])
                        self.trigger_test_signal.emit()
                        self.is_running = False
                        break
            time.sleep(0.5)

    def stop(self):
        self.is_running = False


# ==========================================
#   主程序窗口
# ==========================================
class MotorTestApp:
    def __init__(self):
        self.stat_total = 0
        self.stat_pass = 0
        self.stat_fail = 0

        self.y_min = -2.0
        self.y_max = 2.0
        self.labjack_duration = 1.0
        self.current_sn = ""
        self.latest_test_result = None  # 🌟 用于暂存当前完成的测试结果，供手动点击保存
        self.sn_result_cache = {}
        self.sn_row_map = {}
        self.current_batch_id = time.strftime("%Y%m%d_%H%M%S")
        self.current_batch_file = os.path.join("data", "batches", f"batch_{self.current_batch_id}.csv")
        self.auto_thread = None
        self.is_auto_mode = False
        self.plc_ctrl_addr = 100
        self.plc_res_addr = 101

        self.data_schema = {}
        self.load_data_schema()

        loader = QUiLoader()
        loader.registerCustomWidget(pg.PlotWidget)
        f = QFile("motor_test.ui")
        f.open(QFile.ReadOnly)
        self.ui = loader.load(f)
        f.close()

        # 8 列自适应布局
        if hasattr(self.ui, 'table_data'):
            self.ui.table_data.horizontalHeader().setMinimumHeight(65)
            self.ui.table_data.setWordWrap(True)
            self.ui.table_data.setColumnCount(8)
            self.ui.table_data.setColumnWidth(0, 120)  # SN
            self.ui.table_data.setColumnWidth(1, 120)  # 电阻电感
            self.ui.table_data.setColumnWidth(2, 80)  # 匝间
            self.ui.table_data.setColumnWidth(3, 140)  # U相综合
            self.ui.table_data.setColumnWidth(4, 140)  # V相综合
            self.ui.table_data.setColumnWidth(5, 140)  # W相综合
            self.ui.table_data.setColumnWidth(6, 100)  # 相位差
            self.ui.table_data.setColumnWidth(7, 80)  # 判断

        self.lcr = TonghuiLCR(port='', baudrate=9600)
        self.hioki = HiokiDriver()
        self.labjack = LabJackDriver()
        self.plc = OmronFinsPlcDriver(ip='192.168.250.1')

        self.setup_graph()

        if hasattr(self.ui, 'combo_model'):
            self.ui.combo_model.clear()
            models = SpecManager.get_model_names()
            if not models: models = ["JSON配置报错"]
            self.ui.combo_model.addItems(models)

        # 🌟 4. 绑定控件 (加上你新调整的两个按钮事件)
        if hasattr(self.ui, 'btn_start'): self.ui.btn_start.clicked.connect(self.on_start)
        if hasattr(self.ui, 'btn_stop'): self.ui.btn_stop.clicked.connect(self.on_stop)
        if hasattr(self.ui, 'btn_save_data'): self.ui.btn_save_data.clicked.connect(self.on_save_data_clicked)
        if hasattr(self.ui, 'btn_upload_data'): self.ui.btn_upload_data.clicked.connect(self.on_upload_data_clicked)

        self.refresh_hardware_status()
        self.ui.show()

    def load_data_schema(self):
        schema_path = "config/data_schema.json"
        if os.path.exists(schema_path):
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    self.data_schema = json.load(f)
            except Exception as e:
                print(f"⚠️ 解析 data_schema.json 失败: {e}")

    def setup_graph(self):
        if not hasattr(self.ui, 'graph_widget'): return
        self.plot_item = self.ui.graph_widget.getPlotItem()
        self.plot_item.addLegend()
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.plot_item.setYRange(self.y_min, self.y_max, padding=0)
        self.plot_item.setXRange(0, 1000, padding=0)
        self.plot_item.setLabel('bottom', '时间 (Time)', units='ms')
        self.plot_item.setMouseEnabled(x=False, y=False)
        pg.setConfigOptions(antialias=True)

        self.curve_u = self.ui.graph_widget.plot(pen=pg.mkPen('r', width=2), name="U Phase")
        self.curve_v = self.ui.graph_widget.plot(pen=pg.mkPen('g', width=2), name="V Phase")
        self.curve_w = self.ui.graph_widget.plot(pen=pg.mkPen('b', width=2), name="W Phase")

        self.text_u = pg.TextItem("等待测试...", color='r', anchor=(1, 0))
        self.text_v = pg.TextItem("等待测试...", color='g', anchor=(1, 0))
        self.text_w = pg.TextItem("等待测试...", color='b', anchor=(1, 0))
        self.text_phase = pg.TextItem("等待测试...", color='w', anchor=(1, 0))
        self.text_harmonics = pg.TextItem("等待测试...", color='y', anchor=(1, 0))

        font = self.text_u.textItem.font()
        font.setPointSize(11);
        font.setBold(True)
        self.text_u.setFont(font);
        self.text_v.setFont(font);
        self.text_w.setFont(font)
        self.text_phase.setFont(font);
        self.text_harmonics.setFont(font)

        for item in [self.text_u, self.text_v, self.text_w, self.text_phase, self.text_harmonics]:
            self.plot_item.addItem(item)
        self.reposition_text(1000)

    def reposition_text(self, total_ms):
        if not hasattr(self, 'text_u'): return
        x_pos = total_ms * 0.98
        y_range = self.y_max - self.y_min
        self.text_u.setPos(x_pos, self.y_max - y_range * 0.08)
        self.text_v.setPos(x_pos, self.y_max - y_range * 0.22)
        self.text_w.setPos(x_pos, self.y_max - y_range * 0.36)
        self.text_phase.setPos(x_pos, self.y_max - y_range * 0.50)
        self.text_harmonics.setPos(x_pos, self.y_max - y_range * 0.64)

    def load_settings(self):
        if os.path.exists("config/config.json"):
            try:
                with open("config/config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    comm = data.get("communication", {})
                    simulation = bool(comm.get("simulation", False))

                    self.lcr.port = comm.get("lcr_port", "")
                    self.lcr.baudrate = int(comm.get("lcr_baudrate", self.lcr.baudrate))
                    self.lcr.simulation_mode = simulation

                    self.hioki.ip = comm.get("hioki_ip", "")
                    self.hioki.port = int(comm.get("hioki_port", self.hioki.port))
                    self.hioki.use_table_switch_command = comm.get("hioki_use_table_command", True)
                    self.hioki.remote_before_start = comm.get("hioki_remote_before_start", True)
                    self.hioki.test_wait_sec = float(comm.get("hioki_test_wait_sec", self.hioki.test_wait_sec))
                    self.hioki.simulation_mode = simulation

                    self.plc.ip = comm.get("plc_ip", "192.168.250.1")
                    self.plc.port = int(comm.get("plc_port", self.plc.port))
                    self.plc.pc_node = int(comm.get("pc_node", self.plc.pc_node))
                    self.plc.plc_node = int(comm.get("plc_node", self.plc.plc_node))
                    self.plc.simulation_mode = simulation

                    self.labjack.simulation_mode = simulation
                    self.labjack_duration = float(comm.get("labjack_duration", 1.0))

                    plc_dm = data.get("plc_dm_addresses", {})
                    self.plc_ctrl_addr = int(plc_dm.get("ctrl_addr", self.plc_ctrl_addr))
                    self.plc_res_addr = int(plc_dm.get("res_addr", self.plc_res_addr))

                    compensation = data.get("compensation", {})
                    self.lcr.set_compensation(
                        compensation.get("lcr_comp_r", 0.0),
                        compensation.get("lcr_comp_l", 0.0)
                    )
            except Exception as e:
                print(f"⚠️ 加载 config/config.json 失败: {e}")

    def refresh_hardware_status(self):
        self.load_settings()
        if not getattr(self.lcr, 'is_connected', False):
            if hasattr(self.lcr, 'ser') and self.lcr.ser:
                try:
                    _ = self.lcr.ser.in_waiting
                except Exception:
                    self.lcr.is_connected = False
            if not getattr(self.lcr, 'is_connected', False): self.lcr.connect()

        if hasattr(self.hioki, 'client') and self.hioki.client:
            try:
                self.hioki.client.getpeername()
            except OSError:
                self.hioki.close()

        if not getattr(self.labjack, 'is_connected', False):
            self.labjack.connect()

        self.plc.ping()
        self.update_connection_ui()

    def update_connection_ui(self):
        if hasattr(self.ui, 'lbl_stat_lcr'):
            self.ui.lbl_stat_lcr.setStyleSheet(
                "color: green; font-weight: bold;" if self.lcr.is_connected else "color: gray;")
        if hasattr(self.ui, 'lbl_stat_hioki'):
            hioki_online = self.hioki.is_connected or getattr(self.hioki, "last_comm_ok", False)
            self.ui.lbl_stat_hioki.setStyleSheet(
                "color: green; font-weight: bold;" if hioki_online else "color: gray;")
        if hasattr(self.ui, 'lbl_stat_labjack'):
            self.ui.lbl_stat_labjack.setStyleSheet(
                "color: green; font-weight: bold;" if self.labjack.is_connected else "color: gray;")
        if hasattr(self.ui, 'lbl_stat_plc'):
            self.ui.lbl_stat_plc.setStyleSheet(
                "color: green; font-weight: bold;" if self.plc.is_connected else "color: gray;")

    def on_start(self):
        self.is_auto_mode = hasattr(self.ui, 'chk_auto') and self.ui.chk_auto.isChecked()
        if self.is_auto_mode:
            if self.auto_thread is None or not self.auto_thread.isRunning():
                self.auto_thread = AutoTestThread(self.plc, ctrl_addr=self.plc_ctrl_addr, res_addr=self.plc_res_addr)
                self.auto_thread.log_signal.connect(self.log_message)
                self.auto_thread.trigger_test_signal.connect(self.execute_hardware_test)
                self.auto_thread.start()
            if hasattr(self.ui, 'lbl_status'):
                self.ui.lbl_status.setText("AUTO WAITING...")
                self.ui.lbl_status.setStyleSheet("background-color: lightblue; color: black;")
            return
        self.execute_hardware_test()

    def log_message(self, msg):
        print(f"[AUTO] {msg}")

    def execute_hardware_test(self):
        tasks = {
            'lcr': self.ui.chk_lcr.isChecked() if hasattr(self.ui, 'chk_lcr') else False,
            'hioki': self.ui.chk_hioki.isChecked() if hasattr(self.ui, 'chk_hioki') else False,
            'labjack': self.ui.chk_labjack.isChecked() if hasattr(self.ui, 'chk_labjack') else False
        }
        if not any(tasks.values()):
            QMessageBox.warning(self.ui, "提示", "请至少勾选一个测试项目！")
            return

        sn = self.ui.input_sn.text().strip() if hasattr(self.ui, 'input_sn') else ""
        if not sn: sn = "SN_" + time.strftime("%Y%m%d%H%M%S")

        self.current_sn = sn
        current_model = self.ui.combo_model.currentText() if hasattr(self.ui, 'combo_model') else ""
        self.refresh_hardware_status()

        if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(False)
        if hasattr(self.ui, 'lbl_status'):
            self.ui.lbl_status.setText("TESTING...")
            self.ui.lbl_status.setStyleSheet("background-color: yellow; color: black;")

        self.worker = TestThread(self.lcr, self.hioki, self.labjack, sn, tasks, current_model, self.labjack_duration)
        self.worker.wave_render_signal.connect(self.render_captured_wave)
        self.worker.finished_signal.connect(self.on_test_finished)
        self.worker.start()

    def render_captured_wave(self, wave_data):
        u, v, w = wave_data
        if not hasattr(self, 'curve_u'): return
        total_ms = self.labjack_duration * 1000
        self.plot_item.setXRange(0, total_ms, padding=0)
        self.plot_item.setYRange(self.y_min, self.y_max, padding=0)
        self.reposition_text(total_ms)

        time_axis = np.linspace(0, total_ms, len(u), endpoint=False)
        self.curve_u.setData(time_axis, u)
        self.curve_v.setData(time_axis, v)
        self.curve_w.setData(time_axis, w)

        thds, peaks, diffs, harmonics = self.labjack.analyze_phases(u, v, w)
        h_u, _, _ = harmonics
        self.text_u.setText(f"U 相 | THD: {thds[0]:4.2f} %  |  Vp: {peaks[0]:4.2f} V")
        self.text_v.setText(f"V 相 | THD: {thds[1]:4.2f} %  |  Vp: {peaks[1]:4.2f} V")
        self.text_w.setText(f"W 相 | THD: {thds[2]:4.2f} %  |  Vp: {peaks[2]:4.2f} V")
        self.text_phase.setText(f"相位差 | U-V: {diffs[0]:5.1f}° | V-W: {diffs[1]:5.1f}° | W-U: {diffs[2]:5.1f}°")
        self.text_harmonics.setText(
            f"U相谐波 | 2阶: {h_u[0]:.2f}% | 3阶: {h_u[1]:.2f}% | 4阶: {h_u[2]:.2f}% | 5阶: {h_u[3]:.2f}%")

    def create_empty_result(self):
        return {
            "RL": {"val": "未测试", "pass": True},
            "Hioki": {"val": "未测试", "pass": True, "raw": 0.0},
            "U": {"val": "未测试", "pass": True},
            "V": {"val": "未测试", "pass": True},
            "W": {"val": "未测试", "pass": True},
            "Phase": {"val": "未测试", "pass": True, "raw_diffs": [0.0, 0.0, 0.0]},
            "is_pass": True,
            "R_raw": 0.0,
            "L_raw": 0.0,
            "BEMF": {
                "pass": True,
                "raw_peaks": [0.0, 0.0, 0.0],
                "raw_thds": [0.0, 0.0, 0.0],
                "raw_harmonics": [[0.0, 0.0, 0.0, 0.0] for _ in range(3)]
            }
        }

    def merge_result_for_sn(self, sn, new_result):
        merged = copy.deepcopy(self.sn_result_cache.get(sn, self.create_empty_result()))

        if new_result["RL"]["val"] != "未测试":
            merged["RL"] = copy.deepcopy(new_result["RL"])
            merged["R_raw"] = new_result["R_raw"]
            merged["L_raw"] = new_result["L_raw"]

        if new_result["Hioki"]["val"] != "未测试":
            merged["Hioki"] = copy.deepcopy(new_result["Hioki"])

        if new_result["U"]["val"] != "未测试":
            merged["U"] = copy.deepcopy(new_result["U"])
            merged["V"] = copy.deepcopy(new_result["V"])
            merged["W"] = copy.deepcopy(new_result["W"])
            merged["Phase"] = copy.deepcopy(new_result["Phase"])
            merged["BEMF"] = copy.deepcopy(new_result["BEMF"])

        merged["is_pass"] = self.calculate_merged_pass(merged)
        merged["sn"] = sn
        self.sn_result_cache[sn] = merged
        return merged

    def calculate_merged_pass(self, result_dict):
        is_pass = True
        if result_dict["RL"]["val"] != "未测试" and not result_dict["RL"]["pass"]:
            is_pass = False
        if result_dict["Hioki"]["val"] != "未测试" and not result_dict["Hioki"]["pass"]:
            is_pass = False
        if result_dict["U"]["val"] != "未测试" and not result_dict["BEMF"]["pass"]:
            is_pass = False
        return is_pass

    def build_table_items(self, sn, result_dict):
        is_pass = result_dict["is_pass"]
        items = [
            QTableWidgetItem(sn),
            QTableWidgetItem(result_dict["RL"]["val"]),
            QTableWidgetItem(result_dict["Hioki"]["val"]),
            QTableWidgetItem(result_dict["U"]["val"]),
            QTableWidgetItem(result_dict["V"]["val"]),
            QTableWidgetItem(result_dict["W"]["val"]),
            QTableWidgetItem(result_dict["Phase"]["val"]),
            QTableWidgetItem("PASS" if is_pass else "FAIL")
        ]

        bg_color = QColor(144, 238, 144) if is_pass else QColor(255, 182, 193)
        items[7].setBackground(bg_color)

        if not is_pass:
            items[7].setForeground(QColor("red"))
            if not result_dict["RL"]["pass"]: items[1].setForeground(QColor("red"))
            if not result_dict["Hioki"]["pass"]: items[2].setForeground(QColor("red"))
            if not result_dict["U"]["pass"]: items[3].setForeground(QColor("red"))
            if not result_dict["V"]["pass"]: items[4].setForeground(QColor("red"))
            if not result_dict["W"]["pass"]: items[5].setForeground(QColor("red"))

        for item in items:
            item.setTextAlignment(Qt.AlignCenter)
        return items

    def upsert_result_table_row(self, sn, result_dict):
        if not hasattr(self.ui, 'table_data'): return

        if sn in self.sn_row_map:
            row_idx = self.sn_row_map[sn]
        else:
            row_idx = self.ui.table_data.rowCount()
            self.ui.table_data.insertRow(row_idx)
            self.sn_row_map[sn] = row_idx

        for i, item in enumerate(self.build_table_items(sn, result_dict)):
            self.ui.table_data.setItem(row_idx, i, item)

        self.ui.table_data.resizeRowToContents(row_idx)
        self.ui.table_data.scrollToItem(self.ui.table_data.item(row_idx, 0))

    def build_csv_row_map(self, result_dict, sn_to_save):
        chk_lcr_active = result_dict["RL"]["val"] != "未测试"
        chk_hioki_active = result_dict["Hioki"]["val"] != "未测试"
        chk_lj_active = result_dict["U"]["val"] != "未测试"

        u_h = result_dict["BEMF"].get("raw_harmonics", [[0, 0, 0, 0]])[0]
        v_h = result_dict["BEMF"].get("raw_harmonics", [[0, 0, 0, 0], [0, 0, 0, 0]])[1]
        w_h = result_dict["BEMF"].get("raw_harmonics", [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])[2]
        format_h = lambda h: ",".join([f"{x:.2f}" for x in h]) if chk_lj_active else "未测试"

        return {
            "sn": sn_to_save,
            "r_val": result_dict["R_raw"] if chk_lcr_active else "未测试",
            "l_val": result_dict["L_raw"] if chk_lcr_active else "未测试",
            "hioki_val": result_dict["Hioki"]["raw"] if chk_hioki_active else "未测试",
            "u_vp": result_dict["BEMF"]["raw_peaks"][0] if chk_lj_active else "未测试",
            "v_vp": result_dict["BEMF"]["raw_peaks"][1] if chk_lj_active else "未测试",
            "w_vp": result_dict["BEMF"]["raw_peaks"][2] if chk_lj_active else "未测试",
            "u_thd": result_dict["BEMF"]["raw_thds"][0] if chk_lj_active else "未测试",
            "v_thd": result_dict["BEMF"]["raw_thds"][1] if chk_lj_active else "未测试",
            "w_thd": result_dict["BEMF"]["raw_thds"][2] if chk_lj_active else "未测试",
            "u_harmonics": format_h(u_h),
            "v_harmonics": format_h(v_h),
            "w_harmonics": format_h(w_h),
            "uv_phase": result_dict["Phase"]["raw_diffs"][0] if chk_lj_active else "未测试",
            "vw_phase": result_dict["Phase"]["raw_diffs"][1] if chk_lj_active else "未测试",
            "wu_phase": result_dict["Phase"]["raw_diffs"][2] if chk_lj_active else "未测试",
            "judgment": "PASS" if result_dict["is_pass"] else "FAIL",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    # ==========================================================================
    #   💾 核心修改：数据清洗保存函数 (严格契合 18 列 Excel 格式)
    # ==========================================================================
    def get_ordered_cached_results(self):
        ordered_sns = [
            sn for sn, _ in sorted(self.sn_row_map.items(), key=lambda item: item[1])
            if sn in self.sn_result_cache
        ]
        ordered_sns.extend(sn for sn in self.sn_result_cache.keys() if sn not in ordered_sns)
        return [(sn, self.sn_result_cache[sn]) for sn in ordered_sns]

    def execute_csv_save(self, result_dict, sn_to_save):
        result_to_save = self.sn_result_cache.get(sn_to_save, result_dict)
        success, _ = self.execute_csv_save_many([(sn_to_save, result_to_save)])
        return success

    def execute_csv_save_many(self, records, file_path=None):
        if not self.data_schema: return False, 0
        if file_path is None:
            file_path = self.current_batch_file
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        headers = [self.data_schema[k]["col_name"] for k in self.data_schema.keys()]
        rows_by_sn = {}
        ordered_sns = []

        for sn, result_dict in records:
            if not sn:
                continue
            row_map = self.build_csv_row_map(result_dict, sn)
            rows_by_sn[sn] = [row_map.get(k, "") for k in self.data_schema.keys()]
            if sn not in ordered_sns:
                ordered_sns.append(sn)

        if not rows_by_sn:
            return False, 0

        try:
            old_rows = []
            if os.path.exists(file_path):
                with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
                    old_rows = list(csv.reader(f))

            data_rows = old_rows[1:] if old_rows else []
            new_rows = []
            replaced_sns = set()
            for row in data_rows:
                row_sn = row[0] if row else ""
                if row_sn in rows_by_sn:
                    if row_sn not in replaced_sns:
                        new_rows.append(rows_by_sn[row_sn])
                        replaced_sns.add(row_sn)
                    continue
                new_rows.append(row)

            for sn in ordered_sns:
                if sn not in replaced_sns:
                    new_rows.append(rows_by_sn[sn])

            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(new_rows)
            return True, len(rows_by_sn)
        except Exception as e:
            print(f"⚠️ 无法写入CSV: {e}")
            return False, 0

    # 🌟 核心新增：点击本地数据保存按钮事件
    def on_save_data_clicked(self):
        records = self.get_ordered_cached_results()
        if not records:
            QMessageBox.warning(self.ui, "警告", "当前没有可导出的测试结果，请先进行单次测试！")
            return

        success, saved_count = self.execute_csv_save_many(records)
        if success:
            QMessageBox.information(
                self.ui,
                "提示",
                f"本批次 [{self.current_batch_id}] 的 {saved_count} 个产品数据已成功保存至：\n{self.current_batch_file}"
            )
        else:
            QMessageBox.critical(self.ui, "错误", "CSV文件正在被其他程序占用，请关闭后重试！")

    # 🌟 核心新增：点击上传数据按钮事件 (为你留好的未来 MES 上传通道接口)
    def on_upload_data_clicked(self):
        # 留空方便后续添加网络请求、WebAPI等对接MES系统的上传逻辑
        QMessageBox.information(self.ui, "提示", "数据网络上传通道就绪！功能正在对接中，后续将接入全局 MES 数据追溯系统。")

    def on_test_finished(self, result_dict):
        finished_sn = result_dict.get("sn", self.current_sn)
        self.current_sn = finished_sn

        if not self.is_auto_mode:
            if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(True)

        result_dict = self.merge_result_for_sn(finished_sn, result_dict)
        is_pass = result_dict["is_pass"]
        if hasattr(self.ui, 'lbl_status'):
            if is_pass:
                self.ui.lbl_status.setText("PASS")
                self.ui.lbl_status.setStyleSheet("background-color: green; color: white;")
                self.stat_pass += 1
            else:
                self.ui.lbl_status.setText("FAIL")
                self.ui.lbl_status.setStyleSheet("background-color: red; color: white;")
                self.stat_fail += 1

        self.stat_total += 1
        self.update_stats()
        self.update_connection_ui()

        # 🌟 暂存最新测试结果，以便随时手动点击保存
        self.latest_test_result = result_dict

        # 🌟 如果处于全自动运行状态，为了防止堵塞线体，这里执行自动保存备份
        if self.is_auto_mode:
            self.execute_csv_save(result_dict, finished_sn)

        self.upsert_result_table_row(finished_sn, result_dict)

        if self.is_auto_mode and self.plc.is_connected:
            result_code = 1 if is_pass else 2
            self.plc.write_dm_int16(self.plc_res_addr, [result_code])
            self.auto_thread.is_running = True
            self.auto_thread.start()

    def update_stats(self):
        if hasattr(self.ui, 'lbl_total'): self.ui.lbl_total.setText(str(self.stat_total))
        if hasattr(self.ui, 'lbl_pass'): self.ui.lbl_pass.setText(str(self.stat_pass))
        if hasattr(self.ui, 'lbl_fail'): self.ui.lbl_fail.setText(str(self.stat_fail))

    def on_stop(self):
        QMessageBox.information(self.ui, "提示", "已重置并退出自动模式")
        self.is_auto_mode = False
        if self.auto_thread: self.auto_thread.stop()
        if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(True)
        if hasattr(self.ui, 'lbl_status'):
            self.ui.lbl_status.setText("READY")
            self.ui.lbl_status.setStyleSheet("background-color: lightgray; color: black;")

    def cleanup(self):
        if self.auto_thread: self.auto_thread.stop()
        self.lcr.close() if hasattr(self.lcr, 'close') else None
        self.hioki.close() if hasattr(self.hioki, 'close') else None
        self.labjack.close() if hasattr(self.labjack, 'close') else None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MotorTestApp()
    app.aboutToQuit.connect(window.cleanup)
    sys.exit(app.exec())
