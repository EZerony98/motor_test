import socket
import binascii
import struct


class OmronFinsPlcDriver:
    def __init__(self, ip='192.168.250.1', port=9600, pc_node=2, plc_node=1, timeout=1.0):
        self.ip = ip
        self.port = port
        self.pc_node = pc_node
        self.plc_node = plc_node
        self.timeout = timeout
        self.is_connected = False
        self.simulation_mode = False
        self.ping_address = 3500
        self._sim_words = {}

    def ping(self):
        """利用读取配置的 DM 寄存器来测试 PLC 是否在线"""
        if self.simulation_mode:
            self.is_connected = True
            return True
        data, msg = self.read_dm(self.ping_address, 1)
        self.is_connected = (data is not None)
        return self.is_connected

    def read_dm(self, dm_address, num_elements=1):
        """读取 DM 区数据"""
        if self.simulation_mode:
            payload = b''
            for offset in range(num_elements):
                value = self._sim_words.get(dm_address + offset, 0)
                payload += value.to_bytes(2, 'big', signed=False)
            return payload, "仿真模式"

        ic, rsv, gct, dna = b'\x80', b'\x00', b'\x02', b'\x00'
        da1 = self.plc_node.to_bytes(1, 'big')
        da2, sna = b'\x00', b'\x00'
        sa1 = self.pc_node.to_bytes(1, 'big')
        sa2, sid = b'\x00', b'\x01'

        cm = b'\x01\x01'  # 读内存区
        mem_area = b'\x82'
        start_addr = dm_address.to_bytes(2, 'big') + b'\x00'
        num_elems = num_elements.to_bytes(2, 'big')

        fins_request = ic + rsv + gct + dna + da1 + da2 + sna + sa1 + sa2 + sid + cm + mem_area + start_addr + num_elems

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(fins_request, (self.ip, self.port))
            fins_response, _ = sock.recvfrom(1024)
            if len(fins_response) < 14:
                return None, "响应包过短"
            if fins_response[12:14] == b'\x00\x00':
                return fins_response[14:], "读取成功"
            else:
                return None, f"读取错误，End Code: {binascii.hexlify(fins_response[12:14]).decode('utf-8')}"
        except Exception as e:
            return None, f"通信异常: {e}"
        finally:
            sock.close()

    def write_dm_int16(self, dm_address, values_to_write):
        """写入 16位整数 (INT16) 到 DM 区"""
        if self.simulation_mode:
            for offset, val in enumerate(values_to_write):
                self._sim_words[dm_address + offset] = int(val) & 0xFFFF
            return True, "仿真模式"

        ic, rsv, gct, dna = b'\x80', b'\x00', b'\x02', b'\x00'
        da1 = self.plc_node.to_bytes(1, 'big')
        da2, sna = b'\x00', b'\x00'
        sa1 = self.pc_node.to_bytes(1, 'big')
        sa2, sid = b'\x00', b'\x01'

        cm = b'\x01\x02'  # 写内存区
        mem_area = b'\x82'
        start_addr = dm_address.to_bytes(2, 'big') + b'\x00'

        num_elements = len(values_to_write)
        num_elems = num_elements.to_bytes(2, 'big')

        data_payload = b''
        for val in values_to_write:
            data_payload += val.to_bytes(2, 'big', signed=True)

        fins_request = ic + rsv + gct + dna + da1 + da2 + sna + sa1 + sa2 + sid + cm + mem_area + start_addr + num_elems + data_payload

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(fins_request, (self.ip, self.port))
            fins_response, _ = sock.recvfrom(1024)
            if len(fins_response) < 14:
                return False, "响应包过短"
            if fins_response[12:14] == b'\x00\x00':
                return True, "写入成功"
            else:
                return False, f"写入错误: {binascii.hexlify(fins_response[12:14]).decode('utf-8')}"
        except Exception as e:
            return False, f"通信异常: {e}"
        finally:
            sock.close()

    def write_dm_float(self, dm_address, float_values):
        """写入 32位浮点数 (REAL)，自动处理欧姆龙 CDAB 字序翻转"""
        if self.simulation_mode: return True, "仿真模式"

        ic, rsv, gct, dna = b'\x80', b'\x00', b'\x02', b'\x00'
        da1 = self.plc_node.to_bytes(1, 'big')
        da2, sna = b'\x00', b'\x00'
        sa1 = self.pc_node.to_bytes(1, 'big')
        sa2, sid = b'\x00', b'\x01'
        cm = b'\x01\x02'
        mem_area = b'\x82'
        start_addr = dm_address.to_bytes(2, 'big') + b'\x00'

        data_payload = b''
        for val in float_values:
            packed_float = struct.pack('>f', float(val))
            omron_float = packed_float[2:4] + packed_float[0:2]
            data_payload += omron_float

        num_elements = len(float_values) * 2
        num_elems = num_elements.to_bytes(2, 'big')

        fins_request = ic + rsv + gct + dna + da1 + da2 + sna + sa1 + sa2 + sid + cm + mem_area + start_addr + num_elems + data_payload

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(fins_request, (self.ip, self.port))
            fins_response, _ = sock.recvfrom(1024)
            if len(fins_response) < 14: return False, "响应包过短"
            if fins_response[12:14] == b'\x00\x00':
                return True, "写入成功"
            else:
                return False, f"写入错误"
        except Exception as e:
            return False, f"通信异常: {e}"
        finally:
            sock.close()

    def write_dm_bit(self, dm_address, bit_index, bit_value):
        """读-改-写 (Read-Modify-Write) 机制修改单 Bit"""
        self._validate_bit_index(bit_index)
        bit_index = int(bit_index)
        read_data, msg = self.read_dm(dm_address, 1)
        if not read_data or len(read_data) != 2:
            return False, f"读取底层状态失败: {msg}"

        current_val = self.bytes_to_uint16(read_data)
        if bit_value:
            new_val = current_val | (1 << bit_index)
        else:
            new_val = current_val & ~(1 << bit_index)

        return self.write_dm_int16(dm_address, [self.uint16_to_int16(new_val)])

    def write_dm_bits(self, dm_address, bit_values):
        """一次读改写多个 Bit，减少同一个 DM 字的写入次数"""
        read_data, msg = self.read_dm(dm_address, 1)
        if not read_data or len(read_data) != 2:
            return False, f"读取底层状态失败: {msg}"

        new_val = self.bytes_to_uint16(read_data)
        for bit_index, bit_value in bit_values.items():
            self._validate_bit_index(bit_index)
            bit_index = int(bit_index)
            if bit_value:
                new_val |= (1 << bit_index)
            else:
                new_val &= ~(1 << bit_index)

        return self.write_dm_int16(dm_address, [self.uint16_to_int16(new_val)])

    def read_dm_bit(self, dm_address, bit_index):
        """读取 DM 字中的单个 Bit，返回 (bool_or_None, msg)"""
        self._validate_bit_index(bit_index)
        bit_index = int(bit_index)
        data, msg = self.read_dm(dm_address, 1)
        if not data or len(data) < 2:
            return None, msg
        word = self.bytes_to_uint16(data[:2])
        return bool(word & (1 << bit_index)), msg

    def read_dm_bits(self, dm_address, bit_map):
        """批量读取 DM 字中的 Bit，bit_map 形如 {'ready': 3}"""
        data, msg = self.read_dm(dm_address, 1)
        if not data or len(data) < 2:
            return None, msg
        word = self.bytes_to_uint16(data[:2])
        values = {}
        for name, bit_index in bit_map.items():
            self._validate_bit_index(bit_index)
            bit_index = int(bit_index)
            values[name] = bool(word & (1 << bit_index))
        return values, msg

    @staticmethod
    def _validate_bit_index(bit_index):
        if not 0 <= int(bit_index) <= 15:
            raise ValueError(f"DM bit index must be 0-15, got {bit_index}")

    @staticmethod
    def bytes_to_int16(data):
        return int.from_bytes(data, 'big', signed=True)

    @staticmethod
    def bytes_to_uint16(data):
        return int.from_bytes(data, 'big', signed=False)

    @staticmethod
    def uint16_to_int16(value):
        value = int(value) & 0xFFFF
        if value > 32767:
            return value - 65536
        return value

    @staticmethod
    def bytes_to_float32(data):
        if len(data) != 4: return 0.0
        omron_swapped = data[2:4] + data[0:2]
        return struct.unpack('>f', omron_swapped)[0]
