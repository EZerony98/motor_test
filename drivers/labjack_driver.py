import numpy as np
import time

try:
    from labjack import ljm
except ImportError:
    ljm = None
    print("⚠️ 警告: 未安装 labjack-ljm 库，只能使用仿真模式。")


class LabJackDriver:
    def __init__(self, simulation_mode=False):
        self.handle = None
        self.is_connected = False
        self.stream_running = False
        self.simulation_mode = simulation_mode

        # 采集配置
        self.scan_rate = 10000
        self.scans_per_read = 10000

    def connect(self):
        if self.simulation_mode:
            self.is_connected = True
            return True

        if ljm is None: return False

        try:
            self.handle = ljm.openS("T7", "ANY", "ANY")
            self.is_connected = True
            return True
        except Exception as e:
            print(f"❌ LabJack 连接失败: {e}")
            self.is_connected = False
            return False

    def stop_stream(self):
        """停止流模式，允许在未开启时安全调用"""
        if self.simulation_mode:
            self.stream_running = False
            return

        if ljm is None or self.handle is None:
            self.stream_running = False
            return

        try:
            ljm.eStreamStop(self.handle)
        except Exception:
            pass
        self.stream_running = False

    def start_stream(self):
        """开启流模式"""
        if self.simulation_mode or not self.is_connected:
            self.stream_running = self.simulation_mode
            return self.stream_running

        try:
            # 开启前先停一次，清掉启动预热或上次异常残留的旧流/旧缓冲。
            self.stop_stream()

            ljm.eWriteName(self.handle, "AIN0_NEGATIVE_CH", 199)
            ljm.eWriteName(self.handle, "AIN1_NEGATIVE_CH", 199)
            ljm.eWriteName(self.handle, "AIN2_NEGATIVE_CH", 199)
            ljm.eWriteName(self.handle, "AIN0_RANGE", 10.0)
            ljm.eWriteName(self.handle, "AIN1_RANGE", 10.0)
            ljm.eWriteName(self.handle, "AIN2_RANGE", 10.0)

            scan_list_names = ["AIN0", "AIN1", "AIN2"]
            num_addresses = len(scan_list_names)
            aScanList = ljm.namesToAddresses(num_addresses, scan_list_names)[0]

            ljm.eStreamStart(self.handle, self.scans_per_read, num_addresses, aScanList, self.scan_rate)
            self.stream_running = True
            return True
        except Exception as e:
            print(f"❌ LabJack 开启流失败: {e}")
            self.stream_running = False
            return False

    def capture_data(self, duration_sec):
        """🌟 修复版：按需抓取指定时长的数据，用完立即释放流"""
        if self.simulation_mode:
            time.sleep(duration_sec)
            samples = int(10000 * duration_sec)
            t = np.linspace(0, duration_sec, samples, endpoint=False)
            u = 5 * np.sin(2 * np.pi * 50 * t) + np.random.normal(0, 0.1, samples)
            v = 5 * np.sin(2 * np.pi * 50 * t - 2 * np.pi / 3) + np.random.normal(0, 0.1, samples)
            w = 5 * np.sin(2 * np.pi * 50 * t + 2 * np.pi / 3) + np.random.normal(0, 0.1, samples)
            return u, v, w

        if not self.is_connected:
            return None, None, None

        # 每次测试都重新开启流，避免第一次采集读到程序启动后积压的旧缓冲。
        if not self.start_stream():
            return None, None, None

        u_total, v_total, w_total = [], [], []
        start_time = time.time()

        try:
            # 持续读取直到达到设定时长
            while (time.time() - start_time) < duration_sec:
                ret = ljm.eStreamRead(self.handle)
                aData = ret[0]
                u_total.extend(aData[0::3])
                v_total.extend(aData[1::3])
                w_total.extend(aData[2::3])

            # 🌟🌟🌟 修复 2：读取完成后，立即主动停止流！彻底杜绝后台缓冲区溢出
            self.stop_stream()

            return np.array(u_total), np.array(v_total), np.array(w_total)

        except ljm.LJMError as e:
            print(f"⚠️ 采集异常: {e}")
            self.stop_stream()
            return None, None, None
        except Exception as e:
            print(f"⚠️ 采集异常: {e}")
            self.stop_stream()
            return None, None, None

    def analyze_phases(self, u, v, w):
        """核心算法：统一分析中心（已升级为全三相谐波分析）"""
        u = u - np.mean(u)
        v = v - np.mean(v)
        w = w - np.mean(w)

        peak_u = (np.max(u) - np.min(u)) / 2.0
        peak_v = (np.max(v) - np.min(v)) / 2.0
        peak_w = (np.max(w) - np.min(w)) / 2.0

        window_len = len(u)
        window = np.hanning(window_len)
        fft_u = np.fft.rfft(u * window)
        fft_v = np.fft.rfft(v * window)
        fft_w = np.fft.rfft(w * window)

        abs_u = np.abs(fft_u)
        abs_v = np.abs(fft_v)
        abs_w = np.abs(fft_w)

        fund_idx_u = np.argmax(abs_u[1:]) + 1
        fund_idx_v = np.argmax(abs_v[1:]) + 1
        fund_idx_w = np.argmax(abs_w[1:]) + 1

        def get_thd(abs_fft, fund_idx):
            start_idx = max(1, fund_idx - 2)
            end_idx = min(len(abs_fft), fund_idx + 3)
            fund_energy = np.sum(abs_fft[start_idx:end_idx] ** 2)
            total_ac_energy = np.sum(abs_fft[1:] ** 2)
            harmonic_energy = max(0, total_ac_energy - fund_energy)
            if fund_energy == 0: return 0.0
            return (np.sqrt(harmonic_energy) / np.sqrt(fund_energy)) * 100.0

        thd_u = get_thd(abs_u, fund_idx_u)
        thd_v = get_thd(abs_v, fund_idx_v)
        thd_w = get_thd(abs_w, fund_idx_w)

        def get_harmonic_pct(abs_fft, fund_index, order):
            target_idx = fund_index * order
            if target_idx >= len(abs_fft): return 0.0
            search_start = max(1, target_idx - 1)
            search_end = min(len(abs_fft), target_idx + 2)
            harmonic_amp = np.max(abs_fft[search_start:search_end])
            fund_amp = abs_fft[fund_index]
            if fund_amp == 0: return 0.0
            return (harmonic_amp / fund_amp) * 100.0

        h_u = [get_harmonic_pct(abs_u, fund_idx_u, o) for o in [2, 3, 4, 5]]
        h_v = [get_harmonic_pct(abs_v, fund_idx_v, o) for o in [2, 3, 4, 5]]
        h_w = [get_harmonic_pct(abs_w, fund_idx_w, o) for o in [2, 3, 4, 5]]

        angle_u = np.angle(fft_u[fund_idx_u])
        angle_v = np.angle(fft_v[fund_idx_v])
        angle_w = np.angle(fft_w[fund_idx_w])

        def get_phase_diff(a1, a2):
            diff = np.degrees(a1 - a2)
            diff = (diff + 360) % 360
            if diff > 180: diff = 360 - diff
            return diff

        diff_uv = get_phase_diff(angle_u, angle_v)
        diff_vw = get_phase_diff(angle_v, angle_w)
        diff_wu = get_phase_diff(angle_w, angle_u)

        return (thd_u, thd_v, thd_w), (peak_u, peak_v, peak_w), (diff_uv, diff_vw, diff_wu), (h_u, h_v, h_w)

    def close(self):
        if self.handle is not None:
            self.stop_stream()
            ljm.close(self.handle)
        self.is_connected = False
        self.stream_running = False
