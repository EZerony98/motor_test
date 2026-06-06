import sys
import serial.tools.list_ports
from drivers.tonghui import TonghuiLCR


def list_ports():
    """列出电脑上所有可用的串口"""
    print("=== 正在扫描可用端口 ===")
    ports = serial.tools.list_ports.comports()

    if not ports:
        print("没找到任何串口设备！请检查 USB 线。")
        return []

    result = []
    for i, p in enumerate(ports):
        print(f"[{i}] {p.device} - {p.description}")
        result.append(p.device)
    print("========================")
    return result


def main():
    # 1. 扫描端口
    available_ports = list_ports()
    if not available_ports:
        return

    # 2. 让用户选择
    print("请选择你要连接的端口序号 (例如输入 0):")
    try:
        index = int(input(">>> "))
        selected_port = available_ports[index]
    except:
        print("输入无效，默认选择第一个。")
        selected_port = available_ports[0]

    print(f"\n🚀 准备连接: {selected_port}")
    print("默认波特率: 9600 (如果不通，请去仪器设置里查看)")

    # 3. 初始化驱动 (关闭仿真模式)
    driver = TonghuiLCR(port=selected_port, baudrate=9600)

    # 4. 尝试连接
    if driver.connect():
        print("\n🎉 连接成功！开始连续读取数据 (按 Ctrl+C 停止)...")
        try:
            while True:
                data = driver.fetch_data()
                if data:
                    print(f"读取数据: R = {data['R']:.4f} Ω, L = {data['L']:.4f} H")
                else:
                    print("读取为空 (Check Command)")

                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止测试。")
            driver.close()
    else:
        print("\n 连接失败。请检查：")
        print("1. 仪器开机了吗？")
        print("2. RS232 线接对了吗？")
        print("3. 波特率是 9600 吗？")


if __name__ == "__main__":
    main()