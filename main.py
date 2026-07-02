import sys
import os
import time
import csv
import json
import copy
import numpy as np

import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QTableWidgetItem, QMessageBox, QDialog, QVBoxLayout
from PySide6.QtCore import QThread, Signal, QFile, Qt, QObject, QTimer
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


class UiLogEmitter(QObject):
    message_signal = Signal(str)


class StreamToUiLog:
    def __init__(self, emitter, original_stream=None):
        self.emitter = emitter
        self.original_stream = original_stream
        self._buffer = ""

    def write(self, text):
        if self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()

        if not text:
            return

        self._buffer += str(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self.emitter.message_signal.emit(line)

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

    @property
    def encoding(self):
        return getattr(self.original_stream, "encoding", "utf-8")

    def isatty(self):
        return bool(getattr(self.original_stream, "isatty", lambda: False)())


# ==========================================
#   核心测试线程
# ==========================================
class TestThread(QThread):
    finished_signal = Signal(dict)
    wave_render_signal = Signal(tuple)
    task_finished_signal = Signal(str)
    log_signal = Signal(str)

    def __init__(
        self,
        lcr,
        hioki,
        labjack,
        sn,
        tasks,
        model_name,
        labjack_duration=1.0,
        plc=None,
        plc_dm_config=None,
        resistance_compensations=None,
        inductance_compensations=None
    ):
        super().__init__()
        self.lcr, self.hioki, self.labjack = lcr, hioki, labjack
        self.sn, self.tasks, self.model_name = sn, tasks, model_name
        self.labjack_duration = labjack_duration
        self.plc = plc
        self.plc_dm_config = plc_dm_config or {}
        self.resistance_compensations = resistance_compensations or [0.0, -40.0, -41.0]
        self.inductance_compensations = inductance_compensations or [0.0, 0.0, 0.0]

    @staticmethod
    def _range_from_specs(specs, range_key, min_key, max_key, default_min, default_max):
        if range_key in specs and isinstance(specs[range_key], (list, tuple)) and len(specs[range_key]) >= 2:
            return float(specs[range_key][0]), float(specs[range_key][1])
        return float(specs.get(min_key, default_min)), float(specs.get(max_key, default_max))

    def get_task_config(self, task_name):
        return self.plc_dm_config.get("signals", {}).get(task_name, {})

    def get_task_label(self, task_name):
        return self.get_task_config(task_name).get("name", task_name)

    def get_task_sample_count(self, task_name):
        task_cfg = self.get_task_config(task_name)
        try:
            return max(1, int(task_cfg.get("sample_count", 1)))
        except (TypeError, ValueError):
            return 1

    def get_resistance_compensation(self, sample_index):
        compensation_index = sample_index - 1
        if compensation_index < len(self.resistance_compensations):
            return float(self.resistance_compensations[compensation_index])
        return 0.0

    def get_inductance_compensation(self, sample_index):
        compensation_index = sample_index - 1
        if compensation_index < len(self.inductance_compensations):
            return float(self.inductance_compensations[compensation_index])
        return 0.0

    def fetch_stable_lcr_data(self, sample_index):
        task_cfg = self.get_task_config("lcr")
        stabilize_sec = float(task_cfg.get("stabilize_read_sec", 0.0))
        poll_interval = float(task_cfg.get("stabilize_read_interval_sec", 0.2))
        required_count = max(1, int(task_cfg.get("stabilize_required_count", 3)))
        discard_count = max(0, int(task_cfg.get("stabilize_discard_count", 3)))
        r_tolerance = float(task_cfg.get("stabilize_r_tolerance_mohm", 2.0))
        l_tolerance = float(task_cfg.get("stabilize_l_tolerance_uh", 2.0))
        max_drop_mohm = float(task_cfg.get("stabilize_max_drop_mohm", 1.0))

        if stabilize_sec <= 0:
            return self.lcr.fetch_data()

        self.log(
            f"LCR 第 {sample_index} 组稳定读取最多 {stabilize_sec:.1f}s: "
            f"丢弃前 {discard_count} 次, 连续 {required_count} 次稳定后取平均"
        )
        deadline = time.time() + stabilize_sec
        valid_reads = []
        last_raw = None

        while True:
            raw = self.lcr.fetch_data()
            if raw and raw.get("R") is not None and raw.get("L") is not None:
                raw = dict(raw)
                raw["R"] = float(raw["R"])
                raw["L"] = float(raw["L"])
                last_raw = raw
                valid_reads.append(raw)

                usable_reads = valid_reads[discard_count:]
                window = usable_reads[-required_count:]
                if len(window) == required_count:
                    r_values = [item["R"] for item in window]
                    l_values = [item["L"] for item in window]
                    r_span = max(r_values) - min(r_values)
                    l_span = max(l_values) - min(l_values)
                    r_drop = r_values[0] - r_values[-1]
                    drop_ok = max_drop_mohm < 0 or r_drop <= max_drop_mohm
                    if r_span <= r_tolerance and l_span <= l_tolerance and drop_ok:
                        stable_read = dict(window[-1])
                        stable_read["R"] = sum(r_values) / len(r_values)
                        stable_read["L"] = sum(l_values) / len(l_values)
                        stable_read["stable"] = True
                        stable_read["r_span"] = r_span
                        stable_read["l_span"] = l_span
                        stable_read["r_drop"] = r_drop
                        self.log(
                            f"LCR 第 {sample_index} 组读数稳定: "
                            f"R波动 {r_span:.4f} mΩ, L波动 {l_span:.4f} µH, R下降 {r_drop:.4f} mΩ"
                        )
                        return stable_read

            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(max(poll_interval, 0.05), remaining))

        if last_raw:
            last_raw = dict(last_raw)
            last_raw["stable"] = False
            last_raw["error"] = "读数未稳定"
            self.log(
                f"LCR 第 {sample_index} 组读数未稳定，使用最后一次有效值: "
                f"R {last_raw['R']:.4f} mΩ / L {last_raw['L']:.4f} µH, "
                f"有效读数 {len(valid_reads)} 次"
            )
            return last_raw
        return None

    def log(self, message):
        self.log_signal.emit(message)

    def wait_plc_bit(self, bit_index, expected_value, label, timeout_sec):
        if not self.plc or not self.plc.is_connected:
            self.log(f"PLC 未连接，无法等待 {label}")
            return False

        word_addr = int(self.plc_dm_config.get("word_addr", 3500))
        poll_interval = float(self.plc_dm_config.get("poll_interval_sec", 0.2))
        deadline = time.time() + timeout_sec if timeout_sec and timeout_sec > 0 else None
        last_log_at = 0

        while True:
            value, msg = self.plc.read_dm_bit(word_addr, bit_index)
            if value is not None and bool(value) == bool(expected_value):
                self.log(f"PLC {label}: DM{word_addr}.{int(bit_index):02d}={int(bool(expected_value))}")
                return True

            now = time.time()
            if deadline and now > deadline:
                self.log(f"等待 PLC {label} 超时: {msg}")
                return False

            if now - last_log_at >= 1.0:
                value_text = "?" if value is None else str(int(bool(value)))
                self.log(f"等待 PLC {label}: DM{word_addr}.{int(bit_index):02d}={value_text}")
                last_log_at = now
            time.sleep(poll_interval)

    def wait_initial_task_ready(self, task_name):
        task_cfg = self.get_task_config(task_name)
        if "ready_bit" not in task_cfg:
            return True
        if not self.plc or not self.plc.is_connected:
            return True

        ready_bit = int(task_cfg["ready_bit"])
        timeout_sec = float(task_cfg.get("position_switch_timeout_sec", 60.0))
        return self.wait_plc_bit(
            ready_bit,
            True,
            f"{self.get_task_label(task_name)} 当前工位就绪",
            timeout_sec
        )

    def delay_after_task_ready(self, task_name, position_index):
        task_cfg = self.get_task_config(task_name)
        delay_sec = float(task_cfg.get("ready_delay_sec", 0.0))
        if delay_sec <= 0:
            return

        self.log(f"{self.get_task_label(task_name)} 第 {position_index} 组就绪后延迟 {delay_sec:.1f}s")
        time.sleep(delay_sec)

    def delay_before_position_done(self, task_name, position_index):
        task_cfg = self.get_task_config(task_name)
        delay_sec = float(task_cfg.get("position_done_delay_sec", 0.0))
        if delay_sec <= 0:
            return

        self.log(f"{self.get_task_label(task_name)} 第 {position_index} 组完成后延迟 {delay_sec:.1f}s 再通知 PLC")
        time.sleep(delay_sec)

    def complete_position_sample(self, task_name, position_index, total_positions):
        task_cfg = self.get_task_config(task_name)
        if "position_done_bit" not in task_cfg:
            return True
        if not self.plc or not self.plc.is_connected:
            self.log(f"PLC 未连接，未写入 {self.get_task_label(task_name)} 第 {position_index} 组位置完成位")
            return False

        self.delay_before_position_done(task_name, position_index)

        word_addr = int(self.plc_dm_config.get("word_addr", 3500))
        position_done_bit = int(task_cfg["position_done_bit"])
        ok, msg = self.plc.write_dm_bit(word_addr, position_done_bit, True)
        if ok:
            self.log(
                f"已写入 PLC {self.get_task_label(task_name)} 第 {position_index}/{total_positions} 组位置完成位: "
                f"DM{word_addr}.{position_done_bit:02d}=1"
            )
        else:
            self.log(f"写入 PLC 位置完成位失败: {msg}")
            return False

        if position_index >= total_positions:
            return True

        if getattr(self.plc, "simulation_mode", False):
            self.plc.write_dm_bit(word_addr, position_done_bit, False)
            self.log(f"仿真模式自动复位位置完成位: DM{word_addr}.{position_done_bit:02d}=0")
            return True

        timeout_sec = float(task_cfg.get("position_switch_timeout_sec", 60.0))
        if not self.wait_plc_bit(position_done_bit, False, "读取位置完成位复位", timeout_sec):
            return False

        if "ready_bit" in task_cfg:
            ready_bit = int(task_cfg["ready_bit"])
            return self.wait_plc_bit(ready_bit, True, f"{self.get_task_label(task_name)} 下一位置就绪", timeout_sec)
        return True

    @staticmethod
    def format_lcr_samples(samples, sample_count, r_min, r_max, l_min, l_max):
        lines = []
        phase_labels = ["U", "V", "W"]
        for index in range(sample_count):
            sample_no = phase_labels[index] if index < len(phase_labels) else str(index + 1)
            if index >= len(samples):
                lines.append(f"{sample_no}: 未完成")
                continue
            sample = samples[index]
            if sample.get("R") is None or sample.get("L") is None:
                lines.append(f"{sample_no}: {sample.get('error', '通讯异常')}")
            else:
                stability_text = "" if sample.get("stable", True) else " / 读数未稳定"
                lines.append(f"{sample_no}: R {sample['R']:.4f} mΩ / L {sample['L']:.4f} µH{stability_text}")
        lines.append(f"R[{r_min}~{r_max}] L[{l_min}~{l_max}]")
        return "\n".join(lines)

    @staticmethod
    def format_hioki_samples(samples, sample_count):
        lines = []
        for index in range(sample_count):
            sample_no = index + 1
            if index >= len(samples):
                lines.append(f"{sample_no}: 未完成")
                continue
            sample = samples[index]
            if sample.get("error"):
                lines.append(f"{sample_no}: {sample['error']}")
            else:
                lines.append(f"{sample_no}: {sample.get('value', '')}")
        return "\n".join(lines)

    def run(self):
        specs = SpecManager.get_specs(self.model_name) or {}
        r_min, r_max = specs.get('R', [0.0, 999.0])
        l_min, l_max = specs.get('L', [0.0, 999.0])
        vp_min, vp_max = self._range_from_specs(specs, 'Vp', 'Vp_min', 'Vp_max', 4.0, 999.0)
        thd_min, thd_max = self._range_from_specs(specs, 'THD', 'THD_min', 'THD_max', 0.0, 5.0)

        result = {
            "sn": self.sn,
            "RL": {"val": "未测试", "pass": True, "samples": []},
            "Hioki": {"val": "未测试", "pass": True, "raw": 0.0, "samples": []},
            "U": {"val": "未测试", "pass": True},
            "V": {"val": "未测试", "pass": True},
            "W": {"val": "未测试", "pass": True},
            "Phase": {"val": "未测试", "pass": True, "raw_diffs": [0.0, 0.0, 0.0]},
            "is_pass": True,
            "R_raw": 0.0, "L_raw": 0.0,
            "R_raws": [], "L_raws": [], "Hioki_raws": [],
            "BEMF": {
                "pass": True,
                "raw_peaks": [0.0, 0.0, 0.0],
                "raw_thds": [0.0, 0.0, 0.0],
                "raw_harmonics": [[0.0, 0.0, 0.0, 0.0] for _ in range(3)]
            }
        }

        # 1. 静态电阻电感
        if self.tasks.get('lcr'):
            lcr_sample_count = self.get_task_sample_count('lcr')
            lcr_samples = []
            if not self.wait_initial_task_ready('lcr'):
                lcr_samples.append({"R": None, "L": None, "pass": False, "error": "PLC未就绪"})
                result["is_pass"] = False
            else:
                for sample_index in range(1, lcr_sample_count + 1):
                    self.delay_after_task_ready('lcr', sample_index)
                    raw = self.fetch_stable_lcr_data(sample_index)
                    if raw:
                        r_measured = float(raw['R'])
                        r_compensation = self.get_resistance_compensation(sample_index)
                        r_raw = r_measured + r_compensation
                        l_measured = float(raw['L'])
                        l_compensation = self.get_inductance_compensation(sample_index)
                        l_raw = l_measured + l_compensation
                        stable_ok = bool(raw.get("stable", True))
                        r_ok = r_min <= r_raw <= r_max
                        l_ok = l_min <= l_raw <= l_max
                        lcr_samples.append({
                            "R": r_raw,
                            "R_measured": r_measured,
                            "R_compensation": r_compensation,
                            "L": l_raw,
                            "L_measured": l_measured,
                            "L_compensation": l_compensation,
                            "stable": stable_ok,
                            "error": raw.get("error", ""),
                            "pass": stable_ok and r_ok and l_ok
                        })
                        if not (stable_ok and r_ok and l_ok):
                            result["is_pass"] = False
                    else:
                        lcr_samples.append({"R": None, "L": None, "pass": False, "error": "通讯异常"})
                        result["is_pass"] = False
                        self.lcr.is_connected = False

                    if not self.complete_position_sample('lcr', sample_index, lcr_sample_count):
                        lcr_samples[-1]["pass"] = False
                        if not lcr_samples[-1].get("error"):
                            lcr_samples[-1]["error"] = "PLC切位失败"
                        result["is_pass"] = False
                        break

            lcr_pass = len(lcr_samples) == lcr_sample_count and all(sample.get("pass") for sample in lcr_samples)
            r_values = [sample.get("R") for sample in lcr_samples]
            l_values = [sample.get("L") for sample in lcr_samples]
            result["RL"] = {
                "val": self.format_lcr_samples(lcr_samples, lcr_sample_count, r_min, r_max, l_min, l_max),
                "pass": lcr_pass,
                "samples": copy.deepcopy(lcr_samples)
            }
            result["R_raws"] = r_values
            result["L_raws"] = l_values
            first_r = next((value for value in r_values if value is not None), 0.0)
            first_l = next((value for value in l_values if value is not None), 0.0)
            result["R_raw"] = float(first_r)
            result["L_raw"] = float(first_l)
            if not lcr_pass:
                result["is_pass"] = False
            self.task_finished_signal.emit('lcr')

        # 2. 静态匝间
        if self.tasks.get('hioki'):
            hioki_sample_count = self.get_task_sample_count('hioki')
            hioki_samples = []
            for sample_index in range(1, hioki_sample_count + 1):
                try:
                    table_id = specs.get('table_id', 1)
                    if hasattr(self.hioki, 'run_test'):
                        res_h, data_dict = self.hioki.run_test(table_id)
                    else:
                        if hasattr(self.hioki, 'switch_table') and not self.hioki.switch_table(table_id):
                            hioki_samples.append({"value": "切表失败", "pass": False, "raw": None, "error": "切表失败"})
                            result["is_pass"] = False
                            self.hioki.is_connected = False
                            if not self.complete_position_sample('hioki', sample_index, hioki_sample_count):
                                hioki_samples[-1]["error"] = "PLC切位失败"
                            break
                        time.sleep(0.8)
                        res_h, data_dict = self.hioki.get_data() if hasattr(self.hioki, 'get_data') else ("PASS", {})

                    if res_h == "ERR":
                        err_msg = data_dict.get("Error", "通讯异常") if isinstance(data_dict, dict) else "通讯异常"
                        hioki_samples.append({"value": err_msg, "pass": False, "raw": None, "error": err_msg})
                        result["is_pass"] = False
                        self.hioki.is_connected = False
                    else:
                        h_ok = (res_h == "PASS")
                        area_val = data_dict.get('AREA', 0.0)
                        try:
                            area_raw = float(area_val)
                        except (TypeError, ValueError):
                            area_raw = None
                        hioki_samples.append({"value": f"{area_val}", "pass": h_ok, "raw": area_raw})
                        if not h_ok:
                            result["is_pass"] = False
                except Exception as e:
                    hioki_samples.append({"value": f"通讯异常: {e}", "pass": False, "raw": None, "error": f"通讯异常: {e}"})
                    result["is_pass"] = False
                    self.hioki.is_connected = False

                if not self.complete_position_sample('hioki', sample_index, hioki_sample_count):
                    hioki_samples[-1]["pass"] = False
                    if not hioki_samples[-1].get("error"):
                        hioki_samples[-1]["error"] = "PLC切位失败"
                    result["is_pass"] = False
                    break

            hioki_pass = len(hioki_samples) == hioki_sample_count and all(sample.get("pass") for sample in hioki_samples)
            hioki_raws = [sample.get("raw") for sample in hioki_samples]
            first_hioki = next((value for value in hioki_raws if value is not None), 0.0)
            result["Hioki"] = {
                "val": self.format_hioki_samples(hioki_samples, hioki_sample_count),
                "pass": hioki_pass,
                "raw": float(first_hioki),
                "samples": copy.deepcopy(hioki_samples)
            }
            result["Hioki_raws"] = hioki_raws
            if not hioki_pass:
                result["is_pass"] = False
            self.task_finished_signal.emit('hioki')

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
            self.task_finished_signal.emit('labjack')

        self.finished_signal.emit(result)


# ==========================================
#   自动模式后台轮询线程
# ==========================================
class AutoTestThread(QThread):
    log_signal = Signal(str)
    trigger_test_signal = Signal(str)

    def __init__(self, plc, plc_dm_config, task_order, task_index=0):
        super().__init__()
        self.plc = plc
        self.plc_dm_config = plc_dm_config
        self.task_order = task_order
        self.task_index = task_index
        self.is_running = True
        self.word_addr = int(plc_dm_config.get("word_addr", 3500))
        self.poll_interval = float(plc_dm_config.get("poll_interval_sec", 0.2))

    def run(self):
        if self.task_index >= len(self.task_order):
            return

        if not self.plc.is_connected:
            self.log_signal.emit("PLC 未连接，等待已停止")
            return

        if self.task_index > 0:
            prev_task = self.task_order[self.task_index - 1]
            if not self.wait_previous_ready_clear(prev_task):
                return
            self.clear_task_bits(prev_task)

        task_name = self.task_order[self.task_index]
        task_cfg = self.get_task_config(task_name)
        if not task_cfg:
            self.log_signal.emit(f"PLC 配置中找不到任务: {task_name}")
            return

        ready_bit = int(task_cfg["ready_bit"])
        start_bit = int(task_cfg["start_bit"])
        label = task_cfg.get("name", task_name)
        ok, msg = self.set_task_bit(task_name, "start_bit", True)
        if ok:
            self.log_signal.emit(f"已发送 PLC {label} 开始信号: DM{self.word_addr}.{start_bit:02d}=1")
        else:
            self.log_signal.emit(f"发送 PLC {label} 开始信号失败: {msg}")
        self.log_signal.emit(f"等待 PLC {label} 就绪: DM{self.word_addr}.{ready_bit:02d}")

        last_read_log_at = 0
        while self.is_running:
            ready, msg = self.plc.read_dm_bit(self.word_addr, ready_bit)
            if ready is None:
                self.log_signal.emit(f"读取 PLC 就绪位失败: {msg}")
            elif ready:
                self.log_signal.emit(f"读取 PLC {label} 就绪位: DM{self.word_addr}.{ready_bit:02d}=1")
                self.log_signal.emit(f"PLC {label} 已就绪，开始上位机采集")
                self.trigger_test_signal.emit(task_name)
                self.is_running = False
                break
            else:
                now = time.time()
                if now - last_read_log_at >= 1.0:
                    self.log_signal.emit(f"读取 PLC {label} 就绪位: DM{self.word_addr}.{ready_bit:02d}=0")
                    last_read_log_at = now
            time.sleep(self.poll_interval)

    def get_task_config(self, task_name):
        return self.plc_dm_config.get("signals", {}).get(task_name, {})

    def set_task_bit(self, task_name, bit_key, bit_value):
        task_cfg = self.get_task_config(task_name)
        if bit_key not in task_cfg:
            return False, f"{task_name} 未配置 {bit_key}"
        bit_index = int(task_cfg[bit_key])
        return self.plc.write_dm_bit(self.word_addr, bit_index, bit_value)

    def clear_task_bits(self, task_name):
        task_cfg = self.get_task_config(task_name)
        bit_values = {}
        for bit_key in ("start_bit", "done_bit", "position_done_bit"):
            if bit_key in task_cfg:
                bit_values[int(task_cfg[bit_key])] = False
        if bit_values:
            self.plc.write_dm_bits(self.word_addr, bit_values)

    def wait_previous_ready_clear(self, task_name):
        task_cfg = self.get_task_config(task_name)
        if not task_cfg:
            return True
        ready_bit = int(task_cfg["ready_bit"])
        label = task_cfg.get("name", task_name)
        self.log_signal.emit(f"等待 PLC 释放 {label} 就绪位: DM{self.word_addr}.{ready_bit:02d}")
        last_read_log_at = 0
        while self.is_running:
            ready, msg = self.plc.read_dm_bit(self.word_addr, ready_bit)
            if ready is None:
                self.log_signal.emit(f"读取 PLC 就绪位失败: {msg}")
            elif not ready:
                self.log_signal.emit(f"读取 PLC {label} 就绪位: DM{self.word_addr}.{ready_bit:02d}=0")
                return True
            else:
                now = time.time()
                if now - last_read_log_at >= 1.0:
                    self.log_signal.emit(f"读取 PLC {label} 就绪位: DM{self.word_addr}.{ready_bit:02d}=1")
                    last_read_log_at = now
            time.sleep(self.poll_interval)
        return False

    def stop(self):
        self.is_running = False


# ==========================================
#   主程序窗口
# ==========================================
class MotorTestApp(QObject):
    def __init__(self):
        super().__init__()
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
        self.plc_dm_config = self.default_plc_dm_config()
        self.auto_task_order = []
        self.auto_task_index = 0
        self.active_plc_task = None
        self.plc_sequence_mode = None
        self.manual_plc_tasks = []
        self.manual_plc_done_pending_count = 0
        self.plc_done_delay_sec = 1.0
        self.plc_left_servo_speed_addrs = [3800, 3802, 3804]
        self.plc_left_servo_speed_value = 3000.0
        self.plc_left_servo_speed_type = "float32"
        self.plc_pc_stop_addr = 4000
        self.plc_pc_stop_value = 1
        self.plc_pc_stop_idle_value = 0
        self.plc_pc_stop_reset_delay_sec = 0.5
        self.resistance_compensations = [0.0, -40.0, -41.0]
        self.inductance_compensations = [0.0, 0.0, 0.0]
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        self._stdout_proxy = None
        self._stderr_proxy = None
        self.log_emitter = None

        self.data_schema = {}
        self.load_data_schema()

        loader = QUiLoader()
        loader.registerCustomWidget(pg.PlotWidget)
        f = QFile("motor_test.ui")
        f.open(QFile.ReadOnly)
        self.ui = loader.load(f)
        f.close()

        self.setup_log_window()

        # 8 列自适应布局
        if hasattr(self.ui, 'table_data'):
            self.ui.table_data.horizontalHeader().setMinimumHeight(65)
            self.ui.table_data.setWordWrap(True)
            self.ui.table_data.setColumnCount(8)
            self.ui.table_data.setHorizontalHeaderLabels([
                "SN码",
                "静态测试\n电阻电感(3组)",
                "静态测试\n匝间(3组)",
                "U相\nVp/THD/谐波",
                "V相\nVp/THD/谐波",
                "W相\nVp/THD/谐波",
                "相位差",
                "判断"
            ])
            self.ui.table_data.setColumnWidth(0, 120)  # SN
            self.ui.table_data.setColumnWidth(1, 180)  # 电阻电感
            self.ui.table_data.setColumnWidth(2, 120)  # 匝间
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

    def setup_log_window(self):
        if not hasattr(self.ui, 'text_log'):
            return

        self.ui.text_log.setReadOnly(True)
        self.ui.text_log.document().setMaximumBlockCount(500)
        self.ui.text_log.clear()

        self.log_emitter = UiLogEmitter()
        self.log_emitter.message_signal.connect(self.append_log_message)
        self._stdout_proxy = StreamToUiLog(self.log_emitter, self._stdout_original)
        self._stderr_proxy = StreamToUiLog(self.log_emitter, self._stderr_original)
        sys.stdout = self._stdout_proxy
        sys.stderr = self._stderr_proxy
        print("[UI] 日志窗口已启动")

    def append_log_message(self, message):
        if not hasattr(self.ui, 'text_log'):
            return
        timestamp = time.strftime("%H:%M:%S")
        self.ui.text_log.append(f"[{timestamp}] {message}")
        scrollbar = self.ui.text_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def load_data_schema(self):
        schema_path = "config/data_schema.json"
        if os.path.exists(schema_path):
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    self.data_schema = json.load(f)
            except Exception as e:
                print(f"⚠️ 解析 data_schema.json 失败: {e}")

    @staticmethod
    def normalize_resistance_compensations(compensation):
        defaults = [0.0, -40.0, -41.0]
        if not isinstance(compensation, dict):
            return defaults

        def to_float(value, default):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        phase_config = compensation.get("resistance_compensation_mohm")
        if isinstance(phase_config, dict):
            return [
                to_float(phase_config.get("u"), defaults[0]),
                to_float(phase_config.get("v"), defaults[1]),
                to_float(phase_config.get("w"), defaults[2])
            ]

        list_config = compensation.get("resistance_comp_uvw")
        if isinstance(list_config, (list, tuple)):
            values = defaults[:]
            for index, value in enumerate(list_config[:3]):
                values[index] = to_float(value, defaults[index])
            return values

        return [
            to_float(compensation.get("resistance_comp_u"), defaults[0]),
            to_float(compensation.get("resistance_comp_v"), defaults[1]),
            to_float(compensation.get("resistance_comp_w"), defaults[2])
        ]

    @staticmethod
    def normalize_inductance_compensations(compensation):
        defaults = [0.0, 0.0, 0.0]
        if not isinstance(compensation, dict):
            return defaults

        def to_float(value, default):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        phase_config = compensation.get("inductance_compensation_uh")
        if isinstance(phase_config, dict):
            return [
                to_float(phase_config.get("u"), defaults[0]),
                to_float(phase_config.get("v"), defaults[1]),
                to_float(phase_config.get("w"), defaults[2])
            ]

        list_config = compensation.get("inductance_comp_uvw")
        if isinstance(list_config, (list, tuple)):
            values = defaults[:]
            for index, value in enumerate(list_config[:3]):
                values[index] = to_float(value, defaults[index])
            return values

        return [
            to_float(compensation.get("inductance_comp_u"), defaults[0]),
            to_float(compensation.get("inductance_comp_v"), defaults[1]),
            to_float(compensation.get("inductance_comp_w"), defaults[2])
        ]

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

    @staticmethod
    def default_plc_dm_config():
        return {
            "word_addr": 3500,
            "poll_interval_sec": 0.2,
            "sequence": ["lcr", "hioki", "labjack"],
            "heartbeat": {
                "enabled": False,
                "plc_to_pc_bit": 0,
                "pc_to_plc_bit": 0
            },
            "signals": {
                "lcr": {
                    "name": "电阻电感",
                    "ready_bit": 3,
                    "start_bit": 1,
                    "done_bit": 4,
                    "position_done_bit": 8,
                    "sample_count": 3,
                    "ready_delay_sec": 1.0,
                    "stabilize_read_sec": 2.0,
                    "stabilize_read_interval_sec": 0.2,
                    "stabilize_required_count": 3,
                    "stabilize_discard_count": 3,
                    "stabilize_r_tolerance_mohm": 2.0,
                    "stabilize_l_tolerance_uh": 2.0,
                    "stabilize_max_drop_mohm": 1.0,
                    "position_done_delay_sec": 1.0,
                    "position_switch_timeout_sec": 60.0
                },
                "hioki": {
                    "name": "匝间",
                    "ready_bit": 3,
                    "start_bit": 6,
                    "done_bit": 4,
                    "position_done_bit": 8,
                    "sample_count": 3,
                    "position_switch_timeout_sec": 60.0
                },
                "labjack": {"name": "反电势", "ready_bit": 3, "start_bit": 5, "done_bit": 14}
            }
        }

    def normalize_plc_dm_config(self, raw_config):
        config = copy.deepcopy(self.default_plc_dm_config())
        if not isinstance(raw_config, dict):
            return config

        for key in ("word_addr", "poll_interval_sec", "sequence"):
            if key in raw_config:
                config[key] = raw_config[key]

        if isinstance(raw_config.get("heartbeat"), dict):
            config["heartbeat"].update(raw_config["heartbeat"])

        raw_signals = raw_config.get("signals", {})
        if isinstance(raw_signals, dict):
            for task_name, task_cfg in raw_signals.items():
                if task_name not in config["signals"]:
                    config["signals"][task_name] = {}
                config["signals"][task_name].update(task_cfg)

        config["word_addr"] = int(config["word_addr"])
        config["poll_interval_sec"] = float(config["poll_interval_sec"])
        config["sequence"] = [task for task in config["sequence"] if task in config["signals"]]
        for task_cfg in config["signals"].values():
            for bit_key in ("ready_bit", "start_bit", "done_bit", "position_done_bit"):
                if bit_key in task_cfg:
                    task_cfg[bit_key] = int(task_cfg[bit_key])
            if "sample_count" in task_cfg:
                task_cfg["sample_count"] = max(1, int(task_cfg["sample_count"]))
            if "position_switch_timeout_sec" in task_cfg:
                task_cfg["position_switch_timeout_sec"] = float(task_cfg["position_switch_timeout_sec"])
            if "ready_delay_sec" in task_cfg:
                task_cfg["ready_delay_sec"] = float(task_cfg["ready_delay_sec"])
            if "stabilize_read_sec" in task_cfg:
                task_cfg["stabilize_read_sec"] = float(task_cfg["stabilize_read_sec"])
            if "stabilize_read_interval_sec" in task_cfg:
                task_cfg["stabilize_read_interval_sec"] = float(task_cfg["stabilize_read_interval_sec"])
            if "stabilize_required_count" in task_cfg:
                task_cfg["stabilize_required_count"] = max(1, int(task_cfg["stabilize_required_count"]))
            if "stabilize_discard_count" in task_cfg:
                task_cfg["stabilize_discard_count"] = max(0, int(task_cfg["stabilize_discard_count"]))
            if "stabilize_r_tolerance_mohm" in task_cfg:
                task_cfg["stabilize_r_tolerance_mohm"] = float(task_cfg["stabilize_r_tolerance_mohm"])
            if "stabilize_l_tolerance_uh" in task_cfg:
                task_cfg["stabilize_l_tolerance_uh"] = float(task_cfg["stabilize_l_tolerance_uh"])
            if "stabilize_max_drop_mohm" in task_cfg:
                task_cfg["stabilize_max_drop_mohm"] = float(task_cfg["stabilize_max_drop_mohm"])
            if "position_done_delay_sec" in task_cfg:
                task_cfg["position_done_delay_sec"] = float(task_cfg["position_done_delay_sec"])
        return config

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

                    self.plc_dm_config = self.normalize_plc_dm_config(data.get("plc_dm_addresses", {}))
                    self.plc.ping_address = self.plc_dm_config["word_addr"]

                    plc_control = data.get("plc_control", {})
                    self.plc_done_delay_sec = float(
                        plc_control.get("done_delay_sec", comm.get("plc_done_delay_sec", self.plc_done_delay_sec))
                    )
                    speed_addrs = plc_control.get("left_servo_speed_addrs")
                    if speed_addrs is None:
                        speed_addrs = [plc_control.get("left_servo_speed_addr", self.plc_left_servo_speed_addrs[0])]
                    self.plc_left_servo_speed_addrs = [int(addr) for addr in speed_addrs]
                    self.plc_left_servo_speed_value = float(
                        plc_control.get(
                            "left_servo_speed_value",
                            plc_control.get("left_servo_speed_rpm", self.plc_left_servo_speed_value)
                        )
                    )
                    self.plc_left_servo_speed_type = plc_control.get(
                        "left_servo_speed_type",
                        self.plc_left_servo_speed_type
                    )
                    self.plc_pc_stop_addr = int(
                        plc_control.get("pc_stop_addr", self.plc_pc_stop_addr)
                    )
                    self.plc_pc_stop_value = int(
                        plc_control.get("pc_stop_value", self.plc_pc_stop_value)
                    )
                    self.plc_pc_stop_idle_value = int(
                        plc_control.get("pc_stop_idle_value", self.plc_pc_stop_idle_value)
                    )
                    self.plc_pc_stop_reset_delay_sec = float(
                        plc_control.get("pc_stop_reset_delay_sec", self.plc_pc_stop_reset_delay_sec)
                    )

                    compensation = data.get("compensation", {})
                    self.lcr.set_compensation(
                        compensation.get("lcr_comp_r", 0.0),
                        compensation.get("lcr_comp_l", 0.0)
                    )
                    self.resistance_compensations = self.normalize_resistance_compensations(compensation)
                    self.inductance_compensations = self.normalize_inductance_compensations(compensation)
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
        if not getattr(self.hioki, 'is_connected', False):
            self.hioki.connect(self.hioki.ip)

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

    def get_selected_tasks(self, default_all=False):
        tasks = {
            'lcr': self.ui.chk_lcr.isChecked() if hasattr(self.ui, 'chk_lcr') else False,
            'hioki': self.ui.chk_hioki.isChecked() if hasattr(self.ui, 'chk_hioki') else False,
            'labjack': self.ui.chk_labjack.isChecked() if hasattr(self.ui, 'chk_labjack') else False
        }
        if default_all and not any(tasks.values()):
            tasks = {task: True for task in tasks}
        return tasks

    def get_plc_task_label(self, task_name):
        return self.plc_dm_config.get("signals", {}).get(task_name, {}).get("name", task_name)

    def write_plc_word(self, dm_address, value, label):
        if not self.plc.is_connected:
            self.log_message(f"PLC 未连接，未写入 {label}")
            return False

        ok, msg = self.plc.write_dm_int16(int(dm_address), [int(value)])
        if ok:
            self.log_message(f"已写入 PLC {label}: D{int(dm_address)}={int(value)}")
        else:
            self.log_message(f"写入 PLC {label} 失败: {msg}")
        return ok

    def write_plc_float(self, dm_address, value, label):
        if not self.plc.is_connected:
            self.log_message(f"PLC 未连接，未写入 {label}")
            return False

        ok, msg = self.plc.write_dm_float(int(dm_address), [float(value)])
        if ok:
            self.log_message(f"已写入 PLC {label}: D{int(dm_address)}=REAL {float(value):.1f}")
        else:
            self.log_message(f"写入 PLC {label} 失败: {msg}")
        return ok

    def write_plc_left_servo_speed(self):
        ok_all = True
        for dm_address in self.plc_left_servo_speed_addrs:
            label = f"左伺服电机转速({self.plc_left_servo_speed_type})"
            if self.plc_left_servo_speed_type.lower() in ("float", "float32", "real"):
                ok = self.write_plc_float(dm_address, self.plc_left_servo_speed_value, label)
            else:
                ok = self.write_plc_word(dm_address, int(self.plc_left_servo_speed_value), label)
            ok_all = ok_all and ok
        return ok_all

    def clear_plc_stop_signal(self):
        return self.write_plc_word(
            self.plc_pc_stop_addr,
            self.plc_pc_stop_idle_value,
            "停止/复位信号复位"
        )

    def write_plc_stop_signal(self):
        return self.write_plc_word(
            self.plc_pc_stop_addr,
            self.plc_pc_stop_value,
            "停止/复位信号"
        )

    def pulse_plc_stop_signal(self):
        if not self.write_plc_stop_signal():
            return False

        delay_ms = max(0, int(self.plc_pc_stop_reset_delay_sec * 1000))
        if delay_ms == 0:
            self.clear_plc_stop_signal()
        else:
            self.log_message(
                f"停止/复位信号将在 {self.plc_pc_stop_reset_delay_sec:.1f} 秒后复位为 "
                f"{self.plc_pc_stop_idle_value}"
            )
            QTimer.singleShot(delay_ms, self.clear_plc_stop_signal)
        return True

    def clear_plc_task_bits(self, task_names=None):
        if not self.plc.is_connected:
            return
        word_addr = int(self.plc_dm_config.get("word_addr", 3500))
        signals = self.plc_dm_config.get("signals", {})
        if task_names is None:
            task_names = signals.keys()
        bit_values = {}
        for task_name in task_names:
            task_cfg = signals.get(task_name, {})
            for bit_key in ("start_bit", "done_bit", "position_done_bit"):
                if bit_key in task_cfg:
                    bit_values[int(task_cfg[bit_key])] = False
        if bit_values:
            ok, msg = self.plc.write_dm_bits(word_addr, bit_values)
            if not ok:
                self.log_message(f"清除 PLC 位失败: {msg}")

    def get_plc_task_names_from_flags(self, tasks):
        sequence = self.plc_dm_config.get("sequence", ["lcr", "hioki", "labjack"])
        return [task_name for task_name in sequence if tasks.get(task_name)]

    def write_manual_plc_start_bits(self, task_names):
        if not task_names:
            return
        if not self.plc.is_connected:
            self.log_message("PLC 未连接，手动测试未发送开始信号")
            return

        word_addr = int(self.plc_dm_config.get("word_addr", 3500))
        signals = self.plc_dm_config.get("signals", {})
        bit_values = {}
        labels = []
        for task_name in task_names:
            task_cfg = signals.get(task_name, {})
            if "done_bit" in task_cfg:
                bit_values[int(task_cfg["done_bit"])] = False
            if "position_done_bit" in task_cfg:
                bit_values[int(task_cfg["position_done_bit"])] = False
            if "start_bit" in task_cfg:
                bit_values[int(task_cfg["start_bit"])] = True
                labels.append(self.get_plc_task_label(task_name))

        if not bit_values:
            return

        ok, msg = self.plc.write_dm_bits(word_addr, bit_values)
        if ok:
            self.log_message(f"手动测试已发送 PLC 开始信号: {', '.join(labels)}")
        else:
            self.log_message(f"手动测试发送 PLC 开始信号失败: {msg}")

    def write_manual_plc_done_bits(self, task_names):
        if not task_names:
            return
        if not self.plc.is_connected:
            self.log_message("PLC 未连接，手动测试未发送完成信号")
            return

        word_addr = int(self.plc_dm_config.get("word_addr", 3500))
        signals = self.plc_dm_config.get("signals", {})
        bit_values = {}
        labels = []
        for task_name in task_names:
            task_cfg = signals.get(task_name, {})
            if "start_bit" in task_cfg:
                bit_values[int(task_cfg["start_bit"])] = False
            if "done_bit" in task_cfg:
                bit_values[int(task_cfg["done_bit"])] = True
                labels.append(self.get_plc_task_label(task_name))

        if not bit_values:
            return

        ok, msg = self.plc.write_dm_bits(word_addr, bit_values)
        if ok:
            self.log_message(f"手动测试已发送 PLC 完成信号: {', '.join(labels)}")
        else:
            self.log_message(f"手动测试发送 PLC 完成信号失败: {msg}")

    def schedule_plc_done_signal(self, label, callback):
        delay_ms = max(0, int(self.plc_done_delay_sec * 1000))
        if delay_ms == 0:
            callback()
            return
        self.log_message(f"{label} 测试结束，{self.plc_done_delay_sec:.1f} 秒后发送 PLC 完成信号")
        QTimer.singleShot(delay_ms, callback)

    def schedule_manual_plc_done_bits(self, task_names):
        task_names = list(task_names)
        label = ", ".join(self.get_plc_task_label(task_name) for task_name in task_names)

        def send_done():
            self.write_manual_plc_done_bits(task_names)
            self.manual_plc_done_pending_count = max(0, self.manual_plc_done_pending_count - len(task_names))
            if not self.is_auto_mode and self.manual_plc_done_pending_count == 0 and hasattr(self.ui, 'btn_start'):
                self.ui.btn_start.setEnabled(True)

        self.schedule_plc_done_signal(label or "手动", send_done)

    def on_manual_task_finished(self, task_name):
        if self.is_auto_mode or task_name not in self.manual_plc_tasks:
            return
        self.manual_plc_tasks = [task for task in self.manual_plc_tasks if task != task_name]
        self.schedule_manual_plc_done_bits([task_name])

    def schedule_auto_plc_done_bit(self, task_name):
        label = self.get_plc_task_label(task_name)

        def send_done():
            if not self.plc_sequence_mode or self.active_plc_task != task_name:
                return
            self.mark_plc_task_finished(task_name)
            self.auto_task_index += 1
            self.active_plc_task = None
            self.start_auto_wait_thread()

        self.schedule_plc_done_signal(label, send_done)

    def start_auto_wait_thread(self):
        if self.auto_thread and self.auto_thread.isRunning():
            self.auto_thread.stop()
            self.auto_thread.wait(1000)

        if self.auto_task_index >= len(self.auto_task_order):
            finished_mode = self.plc_sequence_mode
            self.plc_sequence_mode = None
            self.active_plc_task = None
            if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(True)
            if finished_mode == "auto" and hasattr(self.ui, 'lbl_status'):
                self.ui.lbl_status.setText("AUTO DONE")
                self.ui.lbl_status.setStyleSheet("background-color: green; color: white;")
            elif finished_mode == "manual":
                self.log_message("手动 PLC 流程完成")
            return

        self.auto_thread = AutoTestThread(
            self.plc,
            self.plc_dm_config,
            self.auto_task_order,
            self.auto_task_index
        )
        self.auto_thread.log_signal.connect(self.log_message)
        self.auto_thread.trigger_test_signal.connect(self.execute_plc_task)
        self.auto_thread.start()

        task_name = self.auto_task_order[self.auto_task_index]
        if hasattr(self.ui, 'lbl_status'):
            self.ui.lbl_status.setText(f"WAIT PLC {self.get_plc_task_label(task_name)}")
            self.ui.lbl_status.setStyleSheet("background-color: lightblue; color: black;")
        mode_label = "自动模式" if self.plc_sequence_mode == "auto" else "手动模式"
        self.log_message(f"{mode_label}等待步骤 {self.auto_task_index + 1}/{len(self.auto_task_order)}: {self.get_plc_task_label(task_name)}")

    def execute_plc_task(self, task_name):
        self.active_plc_task = task_name
        tasks = {'lcr': False, 'hioki': False, 'labjack': False}
        tasks[task_name] = True
        self.execute_hardware_test(forced_tasks=tasks)

    def mark_plc_task_finished(self, task_name):
        task_cfg = self.plc_dm_config.get("signals", {}).get(task_name, {})
        if not task_cfg or not self.plc.is_connected:
            return

        word_addr = int(self.plc_dm_config.get("word_addr", 3500))
        done_bit = int(task_cfg["done_bit"])
        ok, msg = self.plc.write_dm_bit(word_addr, done_bit, True)
        if ok:
            self.log_message(f"已写入 PLC {self.get_plc_task_label(task_name)} 完成位: DM{word_addr}.{done_bit:02d}")
        else:
            self.log_message(f"写入 PLC 完成位失败: {msg}")

    def on_start(self):
        self.is_auto_mode = hasattr(self.ui, 'chk_auto') and self.ui.chk_auto.isChecked()
        self.refresh_hardware_status()
        if not self.plc.is_connected:
            QMessageBox.warning(self.ui, "提示", "PLC 未连接，请先检查网线、IP、FINS节点和端口。")
            return

        selected_tasks = self.get_selected_tasks(default_all=self.is_auto_mode)
        sequence = self.plc_dm_config.get("sequence", ["lcr", "hioki", "labjack"])
        self.auto_task_order = [task for task in sequence if selected_tasks.get(task)]
        if not self.auto_task_order:
            QMessageBox.warning(self.ui, "提示", "请至少勾选一个测试项目！")
            return

        if not self.write_plc_left_servo_speed():
            QMessageBox.warning(self.ui, "提示", "左伺服电机转速写入失败，请检查 PLC 通讯。")
            return

        self.plc_sequence_mode = "auto" if self.is_auto_mode else "manual"
        self.auto_task_index = 0
        self.active_plc_task = None
        self.manual_plc_tasks = []
        self.manual_plc_done_pending_count = 0
        self.clear_plc_task_bits(self.auto_task_order)
        if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(False)
        self.start_auto_wait_thread()

    def log_message(self, msg):
        print(f"[PLC] {msg}")

    def execute_hardware_test(self, forced_tasks=None):
        tasks = forced_tasks if forced_tasks is not None else self.get_selected_tasks()
        if not any(tasks.values()):
            QMessageBox.warning(self.ui, "提示", "请至少勾选一个测试项目！")
            return

        sn = self.ui.input_sn.text().strip() if hasattr(self.ui, 'input_sn') else ""
        if not sn: sn = "SN_" + time.strftime("%Y%m%d%H%M%S")

        self.current_sn = sn
        current_model = self.ui.combo_model.currentText() if hasattr(self.ui, 'combo_model') else ""
        task_labels = []
        if tasks.get('lcr'):
            task_labels.append("电阻电感")
        if tasks.get('hioki'):
            task_labels.append("匝间")
        if tasks.get('labjack'):
            task_labels.append("反电势")
        print(f"[TEST] 开始测试 SN={sn} 型号={current_model} 项目={','.join(task_labels)}")
        self.refresh_hardware_status()
        if not self.is_auto_mode and forced_tasks is None:
            self.manual_plc_tasks = self.get_plc_task_names_from_flags(tasks)
            self.manual_plc_done_pending_count = len(self.manual_plc_tasks) if self.plc.is_connected else 0
            self.write_manual_plc_start_bits(self.manual_plc_tasks)
            if not self.plc.is_connected:
                self.manual_plc_tasks = []

        if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(False)
        if hasattr(self.ui, 'lbl_status'):
            if self.is_auto_mode and self.active_plc_task:
                self.ui.lbl_status.setText(f"TESTING {self.get_plc_task_label(self.active_plc_task)}")
            else:
                self.ui.lbl_status.setText("TESTING...")
            self.ui.lbl_status.setStyleSheet("background-color: yellow; color: black;")

        self.worker = TestThread(
            self.lcr,
            self.hioki,
            self.labjack,
            sn,
            tasks,
            current_model,
            self.labjack_duration,
            self.plc,
            self.plc_dm_config,
            self.resistance_compensations,
            self.inductance_compensations
        )
        self.worker.wave_render_signal.connect(self.render_captured_wave)
        self.worker.log_signal.connect(self.log_message)
        if not self.is_auto_mode and forced_tasks is None and self.manual_plc_tasks:
            self.worker.task_finished_signal.connect(self.on_manual_task_finished)
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
            "RL": {"val": "未测试", "pass": True, "samples": []},
            "Hioki": {"val": "未测试", "pass": True, "raw": 0.0, "samples": []},
            "U": {"val": "未测试", "pass": True},
            "V": {"val": "未测试", "pass": True},
            "W": {"val": "未测试", "pass": True},
            "Phase": {"val": "未测试", "pass": True, "raw_diffs": [0.0, 0.0, 0.0]},
            "is_pass": True,
            "R_raw": 0.0,
            "L_raw": 0.0,
            "R_raws": [],
            "L_raws": [],
            "Hioki_raws": [],
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
            merged["R_raws"] = copy.deepcopy(new_result.get("R_raws", [new_result["R_raw"]]))
            merged["L_raws"] = copy.deepcopy(new_result.get("L_raws", [new_result["L_raw"]]))

        if new_result["Hioki"]["val"] != "未测试":
            merged["Hioki"] = copy.deepcopy(new_result["Hioki"])
            merged["Hioki_raws"] = copy.deepcopy(new_result.get("Hioki_raws", [new_result["Hioki"].get("raw", 0.0)]))

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

    @staticmethod
    def format_csv_number(value, decimals):
        if value in ("未测试", "异常", None, ""):
            return value
        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return value

    def build_csv_row_map(self, result_dict, sn_to_save):
        chk_lcr_active = result_dict["RL"]["val"] != "未测试"
        chk_hioki_active = result_dict["Hioki"]["val"] != "未测试"
        chk_lj_active = result_dict["U"]["val"] != "未测试"

        r_values = result_dict.get("R_raws") or [result_dict.get("R_raw", 0.0)]
        l_values = result_dict.get("L_raws") or [result_dict.get("L_raw", 0.0)]
        hioki_values = result_dict.get("Hioki_raws") or [result_dict.get("Hioki", {}).get("raw", 0.0)]

        def sample_value(values, index, active, decimals):
            if not active:
                return "未测试"
            if index < len(values) and values[index] is not None:
                return self.format_csv_number(values[index], decimals)
            return "异常"

        u_h = result_dict["BEMF"].get("raw_harmonics", [[0, 0, 0, 0]])[0]
        v_h = result_dict["BEMF"].get("raw_harmonics", [[0, 0, 0, 0], [0, 0, 0, 0]])[1]
        w_h = result_dict["BEMF"].get("raw_harmonics", [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])[2]
        format_h = lambda h: ",".join([f"{x:.2f}" for x in h]) if chk_lj_active else "未测试"

        return {
            "sn": sn_to_save,
            "r_val": sample_value(r_values, 0, chk_lcr_active, 4),
            "l_val": sample_value(l_values, 0, chk_lcr_active, 4),
            "r_val_2": sample_value(r_values, 1, chk_lcr_active, 4),
            "l_val_2": sample_value(l_values, 1, chk_lcr_active, 4),
            "r_val_3": sample_value(r_values, 2, chk_lcr_active, 4),
            "l_val_3": sample_value(l_values, 2, chk_lcr_active, 4),
            "hioki_val": sample_value(hioki_values, 0, chk_hioki_active, 2),
            "hioki_val_2": sample_value(hioki_values, 1, chk_hioki_active, 2),
            "hioki_val_3": sample_value(hioki_values, 2, chk_hioki_active, 2),
            "u_vp": self.format_csv_number(result_dict["BEMF"]["raw_peaks"][0], 2) if chk_lj_active else "未测试",
            "v_vp": self.format_csv_number(result_dict["BEMF"]["raw_peaks"][1], 2) if chk_lj_active else "未测试",
            "w_vp": self.format_csv_number(result_dict["BEMF"]["raw_peaks"][2], 2) if chk_lj_active else "未测试",
            "u_thd": self.format_csv_number(result_dict["BEMF"]["raw_thds"][0], 2) if chk_lj_active else "未测试",
            "v_thd": self.format_csv_number(result_dict["BEMF"]["raw_thds"][1], 2) if chk_lj_active else "未测试",
            "w_thd": self.format_csv_number(result_dict["BEMF"]["raw_thds"][2], 2) if chk_lj_active else "未测试",
            "u_harmonics": format_h(u_h),
            "v_harmonics": format_h(v_h),
            "w_harmonics": format_h(w_h),
            "uv_phase": self.format_csv_number(result_dict["Phase"]["raw_diffs"][0], 2) if chk_lj_active else "未测试",
            "vw_phase": self.format_csv_number(result_dict["Phase"]["raw_diffs"][1], 2) if chk_lj_active else "未测试",
            "wu_phase": self.format_csv_number(result_dict["Phase"]["raw_diffs"][2], 2) if chk_lj_active else "未测试",
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

        should_wait_manual_done = (not self.is_auto_mode and bool(self.plc_sequence_mode))
        if not self.is_auto_mode and not should_wait_manual_done:
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

        print(f"[TEST] 完成测试 SN={finished_sn} 结果={'PASS' if is_pass else 'FAIL'}")
        self.stat_total += 1
        self.update_stats()
        self.update_connection_ui()

        # 🌟 暂存最新测试结果，以便随时手动点击保存
        self.latest_test_result = result_dict

        # 🌟 如果处于全自动运行状态，为了防止堵塞线体，这里执行自动保存备份
        if self.is_auto_mode:
            self.execute_csv_save(result_dict, finished_sn)

        self.upsert_result_table_row(finished_sn, result_dict)

        if self.plc_sequence_mode and self.plc.is_connected and self.active_plc_task:
            finished_task = self.active_plc_task
            self.schedule_auto_plc_done_bit(finished_task)

    def update_stats(self):
        if hasattr(self.ui, 'lbl_total'): self.ui.lbl_total.setText(str(self.stat_total))
        if hasattr(self.ui, 'lbl_pass'): self.ui.lbl_pass.setText(str(self.stat_pass))
        if hasattr(self.ui, 'lbl_fail'): self.ui.lbl_fail.setText(str(self.stat_fail))

    def on_stop(self):
        self.load_settings()
        if not self.plc.is_connected:
            self.plc.ping()
        self.is_auto_mode = False
        if self.auto_thread: self.auto_thread.stop()
        self.clear_plc_task_bits(self.auto_task_order or None)
        self.pulse_plc_stop_signal()
        self.plc_sequence_mode = None
        self.manual_plc_tasks = []
        self.manual_plc_done_pending_count = 0
        self.auto_task_order = []
        self.auto_task_index = 0
        self.active_plc_task = None
        if hasattr(self.ui, 'btn_start'): self.ui.btn_start.setEnabled(True)
        if hasattr(self.ui, 'lbl_status'):
            self.ui.lbl_status.setText("READY")
            self.ui.lbl_status.setStyleSheet("background-color: lightgray; color: black;")
        QMessageBox.information(self.ui, "提示", "已重置并退出测试流程")

    def cleanup(self):
        if self.auto_thread: self.auto_thread.stop()
        if self.plc_sequence_mode:
            self.clear_plc_task_bits(self.auto_task_order or None)
        self.lcr.close() if hasattr(self.lcr, 'close') else None
        self.hioki.close() if hasattr(self.hioki, 'close') else None
        self.labjack.close() if hasattr(self.labjack, 'close') else None
        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MotorTestApp()
    app.aboutToQuit.connect(window.cleanup)
    sys.exit(app.exec())
