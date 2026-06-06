import socket
import time


class HiokiDriver:
    def __init__(self, port=6866, timeout=5):
        self.ip = ""
        self.port = port
        self.timeout = timeout
        self.client = None
        self.is_connected = False
        self.simulation_mode = False

    def connect(self, ip_address):
        """建立 Socket 连接"""
        if not ip_address: return False
        self.ip = ip_address

        if self.simulation_mode:
            self.is_connected = True
            return True

        try:
            print(f"=== 连接 Hioki (ST9000兼容模式): {self.ip}:{self.port} ===")
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.settimeout(self.timeout)
            self.client.connect((self.ip, self.port))
            print("✅ Socket 连接成功")
            self.is_connected = True
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            self.close()
            return False

    import socket
    import time

    class HiokiDriver:
        def __init__(self, port=6866, timeout=5):
            self.ip = ""
            self.port = port
            self.timeout = timeout
            self.client = None
            self.is_connected = False
            self.simulation_mode = False

        def connect(self, ip_address):
            """建立 Socket 连接"""
            if not ip_address: return False
            self.ip = ip_address

            if self.simulation_mode:
                self.is_connected = True
                return True

            try:
                print(f"=== 连接 Hioki (ST9000兼容模式): {self.ip}:{self.port} ===")
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.settimeout(self.timeout)
                self.client.connect((self.ip, self.port))
                print("✅ Socket 连接成功")
                self.is_connected = True
                return True
            except Exception as e:
                print(f"❌ 连接失败: {e}")
                self.close()
                return False

        def send_cmd(self, cmd_str):
            if not self.client: return
            try:
                # 必须加 \r\n，对应屏幕上的 TERM: CR+LF
                full_cmd = f"{cmd_str}\r\n"
                self.client.sendall(full_cmd.encode('ascii'))
            except Exception as e:
                print(f"发送异常: {e}")

        def read_resp(self):
            if not self.client: return None
            try:
                data = self.client.recv(4096)
                if data:
                    return data.decode('ascii', errors='ignore').strip()
                return None
            except socket.timeout:
                return None
            except Exception as e:
                print(f"读取异常: {e}")
                return None

        def switch_table(self, table_num):
            """
            发送指令切换测试 Table
            """
            if self.simulation_mode:
                print(f"[Hioki] 模拟切换到 Table {table_num}")
                return True

            if not self.is_connected:
                return False

            try:
                cmd = f":table:select {table_num}"
                print(f"[Hioki] 发送切换指令: {cmd}")
                self.send_cmd(cmd)
                # 切换表格可能需要一点时间，建议等待 0.2 ~ 0.5 秒
                time.sleep(0.3)
                return True
            except Exception as e:
                print(f"❌ 切换 Table 失败: {e}")
                return False

        def get_data(self):
            """
            执行标准测试流程并解析所有参数
            返回: (Status, Data_Dict)
            """
            # 模拟模式 (调试用)
            if self.simulation_mode:
                time.sleep(1)
                fake_data = {
                    "AREA": "-2.68", "DIFF": "4.01", "FLTR": "2079",
                    "LAPC": "141", "LC": "1.181E-14", "RC": "2.251E-08", "DCHG": "2.51"
                }
                return "PASS", fake_data

            if not self.is_connected: return "ERR", {}

            try:
                # 1. 启动测试
                self.send_cmd(":start")

                # 2. 等待测试完成 (ST4030 通常需要几秒)
                time.sleep(3.0)

                # 3. 获取全量数据
                self.send_cmd(":fetch? all")

                # 4. 读取并解析
                raw_data = self.read_resp()

                if raw_data:
                    print(f"🎉 收到原始数据: {raw_data}")
                    # 示例数据: 0,PASS, -2.68,IN , 4.01,IN , 2079,IN , 141,IN , 1.181E-14, 2.251E-08,IN , 2.51,IN

                    # 去除空格并分割
                    parts = [p.strip() for p in raw_data.split(',')]

                    # 创建数据字典
                    data = {
                        "Raw": raw_data,
                        "Status": "ERR"
                    }

                    # 根据您的截图，数据长度至少有 14 项
                    if len(parts) >= 10:
                        # --- 基础解析 ---
                        data["Status"] = parts[1]  # PASS/FAIL
                        data["AREA"] = parts[2]  # 面积差 (例如 -2.68)
                        data["DIFF"] = parts[4]  # 差分面积 (例如 4.01)
                        data["FLTR"] = parts[6]  # 波形颤动 (例如 2079)

                        # --- 关键参数 (您特别关注的) ---
                        data["LAPC"] = parts[8]  # 二阶微分 (例如 141)

                        # --- LCRC 参数 (屏幕右上角/底部) ---
                        data["LC"] = parts[10]  # 电感/电容 (例如 1.181E-14 -> 11.81f)
                        data["RC"] = parts[11]  # 电阻/响应 (例如 2.251E-08 -> 22.51n)

                        # --- 放电量 (通常在倒数第2位) ---
                        if len(parts) >= 14:
                            data["DCHG"] = parts[-2]  # 例如 2.51

                        # 返回: (总判定, 详细数据字典)
                        return data["Status"], data
                    else:
                        return "ERR", {"Raw": raw_data, "Error": "Data too short"}
                else:
                    return "ERR", {"Error": "Timeout"}

            except Exception as e:
                print(f"❌ 流程异常: {e}")
                return "ERR", {"Error": str(e)}

        def close(self):
            if self.client:
                try:
                    self.client.close()
                except:
                    pass
            self.is_connected = False

    def switch_table(self, table_num):
        """
        发送指令切换测试 Table
        """
        if self.simulation_mode:
            print(f"[Hioki] 模拟切换到 Table {table_num}")
            return True

        if not self.is_connected:
            return False

        try:
            cmd = f":table:select {table_num}"
            print(f"[Hioki] 发送切换指令: {cmd}")
            self.send_cmd(cmd)
            # 切换表格可能需要一点时间，建议等待 0.2 ~ 0.5 秒
            time.sleep(0.3)
            return True
        except Exception as e:
            print(f"❌ 切换 Table 失败: {e}")
            return False

    def get_data(self):
        """
        执行标准测试流程并解析所有参数
        返回: (Status, Data_Dict)
        """
        # 模拟模式 (调试用)
        if self.simulation_mode:
            time.sleep(1)
            fake_data = {
                "AREA": "-2.68", "DIFF": "4.01", "FLTR": "2079",
                "LAPC": "141", "LC": "1.181E-14", "RC": "2.251E-08", "DCHG": "2.51"
            }
            return "PASS", fake_data

        if not self.is_connected: return "ERR", {}

        try:
            # 1. 启动测试
            self.send_cmd(":start")

            # 2. 等待测试完成 (ST4030 通常需要几秒)
            time.sleep(3.0)

            # 3. 获取全量数据
            self.send_cmd(":fetch? all")

            # 4. 读取并解析
            raw_data = self.read_resp()

            if raw_data:
                print(f"🎉 收到原始数据: {raw_data}")
                # 示例数据: 0,PASS, -2.68,IN , 4.01,IN , 2079,IN , 141,IN , 1.181E-14, 2.251E-08,IN , 2.51,IN

                # 去除空格并分割
                parts = [p.strip() for p in raw_data.split(',')]

                # 创建数据字典
                data = {
                    "Raw": raw_data,
                    "Status": "ERR"
                }

                # 根据您的截图，数据长度至少有 14 项
                if len(parts) >= 10:
                    # --- 基础解析 ---
                    data["Status"] = parts[1]  # PASS/FAIL
                    data["AREA"] = parts[2]  # 面积差 (例如 -2.68)
                    data["DIFF"] = parts[4]  # 差分面积 (例如 4.01)
                    data["FLTR"] = parts[6]  # 波形颤动 (例如 2079)

                    # --- 关键参数 (您特别关注的) ---
                    data["LAPC"] = parts[8]  # 二阶微分 (例如 141)

                    # --- LCRC 参数 (屏幕右上角/底部) ---
                    data["LC"] = parts[10]  # 电感/电容 (例如 1.181E-14 -> 11.81f)
                    data["RC"] = parts[11]  # 电阻/响应 (例如 2.251E-08 -> 22.51n)

                    # --- 放电量 (通常在倒数第2位) ---
                    if len(parts) >= 14:
                        data["DCHG"] = parts[-2]  # 例如 2.51

                    # 返回: (总判定, 详细数据字典)
                    return data["Status"], data
                else:
                    return "ERR", {"Raw": raw_data, "Error": "Data too short"}
            else:
                return "ERR", {"Error": "Timeout"}

        except Exception as e:
            print(f"❌ 流程异常: {e}")
            return "ERR", {"Error": str(e)}

    def close(self):
        if self.client:
            try:
                self.client.close()
            except:
                pass
        self.is_connected = False