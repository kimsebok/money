import threading
import time

import serial


class BillSerialManager:
    """Handle bill acceptor/dispenser serial communications."""
    _MAX_RX_BUFFER = 2048
    _TAIL_KEEP_BYTES = 64

    def __init__(self, root, port, on_bill_detected, on_error=None):
        self.root = root
        self.port = port
        self.on_bill_detected = on_bill_detected
        self.on_error = on_error
        self.ser = None
        self.rx_buffer = bytearray()
        self.last_counts = (0, 0, 0)

    def start(self):
        """Open serial port and start reader thread. port can be str or list (try each)."""
        ports = [self.port] if isinstance(self.port, str) else self.port
        for p in ports:
            try:
                self.ser = serial.Serial(
                    p, 9600, parity=serial.PARITY_EVEN, timeout=0.5
                )
                self.port = p
                threading.Thread(target=self._read_loop, daemon=True).start()
                self.clear_bill_acceptor()
                self.enable_bill_acceptor()
                return
            except Exception:
                continue

    def enable_bill_acceptor(self):
        """Enable bill acceptor."""
        self._write_hex("5B A4 03 10 01 00 12")

    def clear_bill_acceptor(self):
        """투입기 리셋(상태 클리어). 최초 포트 오픈 직후 호출됨."""
        self._write_hex("5B A4 03 10 02 00 11")

    def disable_bill_acceptor(self):
        """Disable bill acceptor."""
        self._write_hex("5B A4 03 10 00 00 13")

    def reset_coin_hopper(self):
        """Reset coin hopper."""
        self._write_hex("73 8C 05 01 01 00 00 00 05")

    def reset_bill_dispenser(self):
        """Reset bill dispenser."""
        self._write_hex("73 8C 05 01 00 00 01 00 05")

    def payout_coins(self, count):
        """Dispense coins by count."""
        commands = {
            2: "73 8C 05 00 02 00 00 00 07",
            4: "73 8C 05 00 04 00 00 00 01",
            6: "73 8C 05 00 06 00 00 00 03",
            8: "73 8C 05 00 08 00 00 00 0D",
            10: "73 8C 05 00 0A 00 00 00 0F",
            12: "73 8C 05 00 0C 00 00 00 09",
            14: "73 8C 05 00 0E 00 00 00 0B",
            16: "73 8C 05 00 10 00 00 00 15",
            18: "73 8C 05 00 12 00 00 00 17",
            20: "73 8C 05 00 14 00 00 00 11",
        }
        hex_cmd = commands.get(count)
        if not hex_cmd:
            return
        self._write_hex(hex_cmd)

    def send_combined_payout(self, coin_count, bill_count):
        """Send combined coin/bill payout command."""
        command_map = {
            # 5000원 (동전/지폐)
            (2, 4): "73 8C 05 00 02 00 04 00 03",
            (4, 3): "73 8C 05 00 04 00 03 00 02",
            (6, 2): "73 8C 05 00 06 00 02 00 01",
            (8, 1): "73 8C 05 00 08 00 01 00 0C",
            (10, 0): "73 8C 05 00 0A 00 00 00 0F",
            # 10000원 (동전/지폐)
            (2, 9): "73 8C 05 00 02 00 09 00 0E",
            (4, 8): "73 8C 05 00 04 00 08 00 09",
            (6, 7): "73 8C 05 00 06 00 07 00 04",
            (8, 6): "73 8C 05 00 08 00 06 00 0B",
            (10, 5): "73 8C 05 00 0A 00 05 00 0A",
            (12, 4): "73 8C 05 00 0C 00 04 00 0D",
            (14, 3): "73 8C 05 00 0E 00 03 00 08",
            (16, 2): "73 8C 05 00 10 00 02 00 17",
            (18, 1): "73 8C 05 00 12 00 01 00 16",
            (20, 0): "73 8C 05 00 14 00 00 00 11",
        }
        hex_cmd = command_map.get((coin_count, bill_count))
        if not hex_cmd:
            return
        self._write_hex(hex_cmd)

    def _read_loop(self):
        while True:
            try:
                if not self.ser or not self.ser.is_open:
                    break
                waiting = self.ser.in_waiting
                if waiting:
                    data = self.ser.read(waiting)
                else:
                    # timeout 기반 1바이트 블로킹 읽기: 바쁜 루프 방지
                    data = self.ser.read(1)
                if data:
                    self.rx_buffer.extend(data)
                    if len(self.rx_buffer) > self._MAX_RX_BUFFER:
                        # 비정상/잡음 누적 보호: 최근 일부만 유지
                        del self.rx_buffer[:-self._TAIL_KEEP_BYTES]
                    self._parse_bill_packet(self.rx_buffer)
                else:
                    # timeout=0.5 이후 빈 응답일 때 CPU 점유 완화
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.05)

    def _parse_bill_packet(self, buffer):
        if len(buffer) > self._MAX_RX_BUFFER:
            del buffer[:-self._TAIL_KEEP_BYTES]

        while buffer and buffer[0] in (0x11, 0xEE):
            del buffer[0]

        er_header = bytes.fromhex("33 0F 05 15")
        er_idx = buffer.find(er_header)
        if er_idx != -1 and len(buffer) >= er_idx + 18:
            packet = buffer[er_idx:er_idx + 18]
            del buffer[:er_idx + 18]
            if packet[12] != 0x04 and self.on_error:
                self.root.after(0, self.on_error)
            return

        # 정해진 형식: 33 0B 05 18 + 카운트 (14바이트)
        header = bytes.fromhex("33 0B 05 18")
        idx = buffer.find(header)
        if idx == -1:
            # 헤더가 없으면 버퍼가 계속 커지지 않게 꼬리만 보존
            if len(buffer) > self._TAIL_KEEP_BYTES:
                del buffer[:-self._TAIL_KEEP_BYTES]
            return
        if len(buffer) < idx + 14:
            return

        packet = buffer[idx:idx + 14]
        b1, b2, b3 = packet[4], packet[5], packet[6]

        prev = self.last_counts
        self.last_counts = (b1, b2, b3)

        if b1 > prev[0]:
            amount = 1000
        elif b2 > prev[1]:
            amount = 5000
        elif b3 > prev[2]:
            amount = 10000
        else:
            return

        del buffer[:idx + 14]
        self.root.after(0, self.on_bill_detected, amount)

    def _write_hex(self, hex_str):
        try:
            if not self.ser:
                return
            self.ser.write(bytes.fromhex(hex_str))
        except Exception:
            pass
