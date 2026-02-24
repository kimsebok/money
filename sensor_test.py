# -*- coding: utf-8 -*-
"""
TOF050C(VL6180X) 거리 센서 테스트.
sensor_test2.py 방식: board + busio + adafruit_vl6180x

실행: python3 sensor_test.py
종료: Ctrl+C

필요: pip install adafruit-blinka adafruit-circuitpython-vl6180x (venv 권장)
"""
import sys
import time

if not sys.platform.startswith("linux"):
    print("Linux(라즈베리 파이)에서만 동작합니다.")
    sys.exit(1)

from sensor import _get_sensor, reset_i2c_connection

def main():
    sensor = _get_sensor()
    if sensor is None:
        print("VL6180X 초기화 실패.")
        print("  설치: pip install adafruit-blinka adafruit-circuitpython-vl6180x")
        print("  I2C 활성화: sudo raspi-config → Interface Options → I2C")
        return 1

    print("TOF050C 거리 센서 테스트 (종료: Ctrl+C)")
    print("=" * 50)

    try:
        while True:
            d = sensor.range
            print(f"Distance: {d} mm")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n종료.")
    finally:
        reset_i2c_connection()

    return 0

if __name__ == "__main__":
    sys.exit(main())
