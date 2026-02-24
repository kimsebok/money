#!/usr/bin/env python3
"""
시리얼 통신 테스트 (지폐 인식기/동전·지폐 배출기 포트 확인용)

실행: python3 serial_test.py
종료: Ctrl+C

필요: pip install pyserial
라즈비안 권한: sudo usermod -aG dialout $USER  후 재로그인
"""
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial 없음. 설치: pip install pyserial")
    sys.exit(1)

# 라즈베리 파이(라즈비안) 전용 포트. Windows(COM3)는 사용하지 않음.
SERIAL_PORTS = ["/dev/bill", "/dev/serial0", "/dev/ttyAMA0", "/dev/ttyS0", "/dev/ttyUSB0"]
BAUD = 9600
PARITY = "E"  # EVEN

def list_ports():
    """시스템에서 사용 가능한 시리얼 포트 목록 출력."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("  (감지된 포트 없음)")
            return
        for p in ports:
            print(f"  {p.device} - {p.description}")
    except Exception as e:
        print(f"  목록 조회 실패: {e}")

def open_serial(port):
    """포트 열기 (앱과 동일: 9600 8E1)."""
    try:
        parity = serial.PARITY_EVEN
        ser = serial.Serial(port, BAUD, parity=parity, timeout=0.5)
        return ser
    except Exception:
        return None

def main():
    # 라즈베리 파이 환경 전용
    port_list = SERIAL_PORTS

    print("=" * 60)
    print("시리얼 통신 테스트 (지폐 교환기 포트)")
    print("=" * 60)
    print("\n[1] 사용 가능한 시리얼 포트 목록:")
    list_ports()
    print("\n[2] 테스트할 포트 순서:", port_list)

    ser = None
    opened_port = None
    for port in port_list:
        print(f"\n    열기 시도: {port} ... ", end="", flush=True)
        ser = open_serial(port)
        if ser:
            print("OK")
            opened_port = port
            break
        print("실패")

    if not ser:
        print("\n[결과] 모든 포트 열기 실패. 권한 확인: sudo usermod -aG dialout $USER 후 재로그인")
        return 1

    print(f"\n[3] 수신 대기 중 (포트: {opened_port}, {BAUD} 8E1)")
    print("    지폐 넣거나 장비에서 데이터가 오면 hex로 출력됩니다. 종료: Ctrl+C\n")

    try:
        while True:
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                hex_str = " ".join(f"{b:02X}" for b in data)
                safe = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
                print(f"  RX ({len(data)} bytes): {hex_str}  |  {safe}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n\n종료.")
    finally:
        ser.close()
        print(f"포트 {opened_port} 닫음.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
