import serial
import time
import random


class TonghuiLCR:
    def __init__(self, port, baudrate=9600, timeout=1):
        """
        :param port: 端口号 (如 'COM3' 或 '/dev/tty.usbserial-xxx')
        :param baudrate: 波特率 (必须与仪器设置一致)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.is_connected = False
        self.simulation_mode = False

        # --- 新增：初始化补偿值 ---
        self.comp_r = 0.0  # 单位：mΩ
        self.comp_l = 0.0  # 单位：µH

    def set_compensation(self, comp_r, comp_l):
        """设置线阻和线感补偿值"""
        self.comp_r = float(comp_r)
        self.comp_l = float(comp_l)

    def connect(self):
        """尝试打开串口并握手"""
        if self.simulation_mode:
            print("[同惠仿真] 虚拟连接成功")
            self.is_connected = True
            return True

        try:
            # 1. 打开串口
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=self.timeout
            )

            # 2. 发送握手指令 (*IDN?)
            print(f"正在尝试连接同惠 LCR {self.port} ...")
            self.ser.write(b"*IDN?\n")

            # 3. 读取回应
            response = self.ser.readline().decode('utf-8', errors='ignore').strip()

            if response:
                print(f"✅ 同惠 LCR 连接成功: {response}")
                self.is_connected = True
                return True
            else:
                print("❌ 串口已打开，但仪器没回话 (请检查波特率或指令)")
                self.ser.close()
                return False

        except serial.SerialException as e:
            print(f"❌ 串口打开失败: {e}")
            print("提示：请检查 USB 线是否插好，或者端口号是否填错。")
            return False
        except Exception as e:
            print(f"❌ 未知错误: {e}")
            return False

    def fetch_data(self):
        """发送测试指令并读取结果"""
        # 仿真模式数据
        if self.simulation_mode:
            return {
                "R": 54.0 + random.random(),
                "L": 3.4 + random.random(),
                "status": "PASS"
            }

        if not self.is_connected or not self.ser:
            return None

        try:
            self.ser.write(b"FETCH?\n")

            # 典型返回格式: "+3.4470E-06,+5.4741E-02,0"
            raw = self.ser.readline().decode('utf-8', errors='ignore').strip()

            if not raw:
                return None

            # 解析数据
            parts = raw.split(',')
            if len(parts) >= 2:
                try:
                    val_1_raw = float(parts[0])  # 电感 (H)
                    val_2_raw = float(parts[1])  # 电阻 (Ω)

                    # 单位换算
                    raw_l_uh = abs(val_1_raw * 1000000)
                    raw_r_mmo = abs(val_2_raw * 1000)

                    # --- 核心修改：扣除夹具和线路的补偿值 ---
                    calibrated_r = raw_r_mmo - self.comp_r
                    calibrated_l = raw_l_uh - self.comp_l

                    # 避免极端情况下减出负数
                    if calibrated_r < 0: calibrated_r = 0.0
                    if calibrated_l < 0: calibrated_l = 0.0

                    return {
                        "R": calibrated_r,
                        "L": calibrated_l,
                        "status": "PASS"
                    }
                except ValueError:
                    print(f"数据解析错误: {raw}")
                    return None
            return None

        except Exception as e:
            print(f"读取异常: {e}")
            return None

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.is_connected = False