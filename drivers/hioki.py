import socket
import time


class HiokiDriver:
    def __init__(self, port=6866, timeout=5):
        self.ip = ""
        self.port = port
        self.timeout = timeout
        self.client = None
        self.is_connected = False
        self.last_comm_ok = False
        self.simulation_mode = False
        self.reconnect_delay = 0.5
        self.use_table_switch_command = True
        self.table_command_template = ":TABLE:SELECT {table}"
        self.table_settle_sec = 0.8
        self.remote_before_start = True
        self.test_wait_sec = 5.0

    @staticmethod
    def normalize_ip(ip_address):
        """兼容仪器界面显示的 192.168.010.005 这种补零写法。"""
        if not ip_address:
            return ""
        parts = str(ip_address).strip().split(".")
        if len(parts) != 4:
            return str(ip_address).strip()
        try:
            return ".".join(str(int(part)) for part in parts)
        except ValueError:
            return str(ip_address).strip()

    def connect(self, ip_address=None):
        """建立 LAN Socket 连接。仪器页面 TERM 需为 CR+LF。"""
        if ip_address:
            self.ip = self.normalize_ip(ip_address)
        if not self.ip:
            return False

        if self.simulation_mode:
            self.is_connected = True
            self.last_comm_ok = True
            return True

        self.close()
        try:
            print(f"=== 连接 Hioki: {self.ip}:{self.port} ===")
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.settimeout(self.timeout)
            self.client.connect((self.ip, int(self.port)))
            self.is_connected = True
            self.last_comm_ok = True
            print("✅ 连接成功")
            time.sleep(0.2)
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            self.last_comm_ok = False
            self.close()
            return False

    def ensure_connected(self):
        if self.simulation_mode:
            self.is_connected = True
            return True
        if self.is_connected and self.client:
            return True
        return self.connect(self.ip)

    def send_cmd(self, cmd_str, retry=True):
        if self.simulation_mode:
            return True
        if not self.ensure_connected():
            return False

        try:
            print(f"[Hioki] >> {cmd_str}")
            full_cmd = f"{cmd_str}\r\n"
            self.client.sendall(full_cmd.encode("ascii"))
            return True
        except Exception as e:
            print(f"发送异常: {e}")
            self.last_comm_ok = False
            self.close()
            if retry and self.ip:
                print("Hioki 连接已断开，正在重连并重发指令...")
                time.sleep(self.reconnect_delay)
                if self.connect(self.ip):
                    return self.send_cmd(cmd_str, retry=False)
            return False

    def read_resp(self):
        if not self.client:
            return None
        try:
            data = self.client.recv(4096)
            if data:
                return data.decode("ascii", errors="ignore").strip()
            self.last_comm_ok = False
            self.close()
            return None
        except socket.timeout:
            return None
        except Exception as e:
            print(f"读取异常: {e}")
            self.last_comm_ok = False
            self.close()
            return None

    def query_cmd(self, cmd_str, wait_sec=0.1):
        if not self.send_cmd(cmd_str, retry=False):
            return None
        time.sleep(wait_sec)
        return self.read_resp()

    def diagnose(self):
        """返回一组基础通讯诊断结果，用来判断命令解释器是否响应。"""
        if not self.connect(self.ip):
            return {"connect": "FAIL"}

        commands = [
            "*IDN?",
            ":SYSTem:REMote",
            "*IDN?",
            ":SYSTem:ERRor?",
            ":STATus:ERRor?",
            ":ESR?",
            ":MEMory:FETCh?",
            ":FETCh?"
        ]

        result = {"connect": "OK"}
        try:
            for cmd in commands:
                if cmd.endswith("?"):
                    result[cmd] = self.query_cmd(cmd, wait_sec=0.2)
                else:
                    result[cmd] = "SEND_OK" if self.send_cmd(cmd, retry=False) else "SEND_FAIL"
                    time.sleep(0.2)
            return result
        finally:
            self.close()

    def switch_table(self, table_num):
        table_num = int(table_num)
        if self.simulation_mode:
            print(f"[Hioki] 模拟切换到 Table {table_num}")
            return True

        if not self.use_table_switch_command:
            print(f"[Hioki] 跳过通讯切表，使用仪器当前 TABLE（目标: {table_num:03d}）")
            return True

        if self.remote_before_start:
            if not self.send_cmd(":SYSTem:REMote", retry=False):
                return False
            time.sleep(0.2)

        cmd = self.table_command_template.format(table=table_num, table03=f"{table_num:03d}")
        print(f"[Hioki] 发送切换指令: {cmd}")
        if not self.send_cmd(cmd, retry=False):
            return False
        time.sleep(self.table_settle_sec)
        return True

    def run_test(self, table_num):
        """用一条全新的连接完成切表、启动、读取，避免复用失效 socket。"""
        if self.simulation_mode:
            self.switch_table(table_num)
            return self.get_data()

        last_error = {"Error": "Unknown"}
        for attempt in range(2):
            self.close()
            if not self.connect(self.ip):
                return "ERR", {"Error": "Connect failed"}

            try:
                if not self.switch_table(table_num):
                    last_error = {"Error": "Switch table failed"}
                    continue

                result, data = self.get_data()
                if result != "ERR":
                    self.last_comm_ok = True
                    return result, data
                last_error = data
                print(f"Hioki 第 {attempt + 1} 次测试流程失败: {data.get('Error', 'Unknown')}")
            finally:
                self.close()

            if attempt == 0:
                time.sleep(0.8)

        self.last_comm_ok = False
        return "ERR", last_error

    def get_data(self):
        """执行匝间测试并返回 (判定, 数据字典)。"""
        if self.simulation_mode:
            time.sleep(1)
            fake_data = {
                "AREA": "-2.68", "DIFF": "4.01", "FLTR": "2079",
                "LAPC": "141", "LC": "1.181E-14", "RC": "2.251E-08", "DCHG": "2.51"
            }
            return "PASS", fake_data

        if not self.ensure_connected():
            return "ERR", {"Error": "Not connected"}

        if self.remote_before_start:
            # ST4030A 面板底部显示 LOCAL 时，先切到远程控制再启动测试。
            self.send_cmd(":SYSTem:REMote", retry=False)
            time.sleep(0.2)

        if not self.send_cmd(":START", retry=False):
            self.last_comm_ok = False
            return "ERR", {"Error": "Start command failed"}

        time.sleep(self.test_wait_sec)

        raw_data = self.fetch_all()
        if not raw_data:
            self.last_comm_ok = False
            return "ERR", {"Error": "Timeout"}

        self.last_comm_ok = True
        return self.parse_fetch_all(raw_data)

    def fetch_all(self):
        commands = [":MEMory:FETCh?", ":FETCh?", ":FETCh? ALL", ":FETCh:ALL?"]
        for cmd in commands:
            for attempt in range(2):
                if not self.ensure_connected():
                    return None
                if not self.send_cmd(cmd, retry=False):
                    break
                raw_data = self.read_resp()
                if raw_data:
                    print(f"🎉 {cmd} 收到原始数据: {raw_data}")
                    return raw_data
                if attempt == 0:
                    print(f"Hioki {cmd} 首次读取为空，重试...")
                    time.sleep(0.8)

            print(f"Hioki {cmd} 未读到数据，尝试下一种读取命令...")
            self.close()
            time.sleep(0.3)
        return None

    @staticmethod
    def parse_fetch_all(raw_data):
        parts = [p.strip().strip('"') for p in raw_data.split(",")]
        if len(parts) < 10:
            return "ERR", {"Raw": raw_data, "Error": "Data too short"}

        label_values = {}
        for i in range(0, len(parts) - 1, 2):
            label_values[parts[i].upper()] = parts[i + 1]

        if "TOTAL JUDGE" in label_values:
            data = {
                "Raw": raw_data,
                "Status": label_values.get("TOTAL JUDGE", "ERR"),
                "AREA": label_values.get("AREA VALUE", ""),
                "DIFF": label_values.get("DIFF VALUE", ""),
                "FLTR": label_values.get("FLUTTER VALUE", ""),
                "LAPC": label_values.get("LAPLACIAN VALUE", ""),
                "LC": "",
                "RC": "",
                "DCHG": label_values.get("DISCHARGE VALUE", "")
            }
            return data["Status"], data

        data = {
            "Raw": raw_data,
            "Status": parts[1],
            "AREA": parts[2],
            "DIFF": parts[4],
            "FLTR": parts[6],
            "LAPC": parts[8],
            "LC": parts[10] if len(parts) > 10 else "",
            "RC": parts[11] if len(parts) > 11 else "",
            "DCHG": parts[-2] if len(parts) >= 14 else ""
        }
        return data["Status"], data

    def close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self.is_connected = False
