import json
import os
import time

from drivers.hioki import HiokiDriver


def load_hioki_from_config():
    driver = HiokiDriver()
    config_path = os.path.join("config", "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        comm = data.get("communication", {})
        driver.ip = comm.get("hioki_ip", "")
        driver.port = int(comm.get("hioki_port", driver.port))
        driver.remote_before_start = comm.get("hioki_remote_before_start", True)
        driver.test_wait_sec = float(comm.get("hioki_test_wait_sec", driver.test_wait_sec))
    return driver


def print_response(cmd, resp):
    print(f"{cmd:<22} => {resp if resp else '<无响应>'}")


def main():
    hioki = load_hioki_from_config()
    print(f"Hioki LAN: {hioki.normalize_ip(hioki.ip)}:{hioki.port}")

    if not hioki.connect(hioki.ip):
        print("连接失败：检查网线、IP、端口、电脑网段。")
        return

    try:
        print("\n=== 基础命令响应测试 ===")
        for cmd in ["*IDN?", ":SYSTem:ERRor?", ":STATus:ERRor?", ":ESR?"]:
            print_response(cmd, hioki.query_cmd(cmd, wait_sec=0.2))

        print("\n=== 远程模式测试 ===")
        print_response(":SYSTem:REMote", "SEND_OK" if hioki.send_cmd(":SYSTem:REMote", retry=False) else "SEND_FAIL")
        time.sleep(0.3)
        print_response("*IDN?", hioki.query_cmd("*IDN?", wait_sec=0.2))

        print("\n=== 启动命令测试 ===")
        for cmd in [":START", ":INITiate", "*TRG"]:
            print_response(cmd, "SEND_OK" if hioki.send_cmd(cmd, retry=False) else "SEND_FAIL")
            time.sleep(0.8)

        print("\n=== 结果读取测试 ===")
        time.sleep(hioki.test_wait_sec)
        for cmd in [":MEMory:FETCh?", ":FETCh?", ":FETCh? ALL", ":FETCh:ALL?"]:
            print_response(cmd, hioki.query_cmd(cmd, wait_sec=0.5))

        print("\n如果 *IDN? 都无响应：LAN 只建立了 socket，但仪器命令解释器没回包。")
        print("如果 *IDN? 有响应但 START 无动作：优先检查 STOP、INTERLOCK、REMOTE/LOCAL、治具安全回路。")
    finally:
        hioki.close()


if __name__ == "__main__":
    main()
