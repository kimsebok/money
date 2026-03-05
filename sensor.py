# -*- coding: utf-8 -*-
"""
거리 센서 (estarDyn TOF050C / VL6180X) 제어.
50cm 이내 감지 시 대기 모드 진입(타이머 리셋) 콜백 호출.

방식: Adafruit CircuitPython VL6180X (board + busio + adafruit_vl6180x)
설치: pip install adafruit-blinka adafruit-circuitpython-vl6180x  (venv 권장)

=== 라즈베리 파이 연결 (TOF050C) ===
  VIN → 3.3V (Pin 1)   GND → GND (Pin 6 등)
  SDA → GPIO2 (Pin 3)   SCL → GPIO3 (Pin 5)
  I2C 활성화: sudo raspi-config → Interface Options → I2C → Enable
  확인: sudo i2cdetect -y 1  (0x29 보이면 정상)
"""

import atexit
import json
import os
import sys
import threading
import time

_IS_LINUX = sys.platform.startswith("linux")
_adafruit_sensor = None
_i2c_lock = threading.Lock()

try:
    import board
    import busio
    import adafruit_vl6180x
    _ADAFRUIT_AVAILABLE = True
except ImportError:
    _ADAFRUIT_AVAILABLE = False


def _get_sensor():
    """VL6180X 센서 인스턴스 (board.I2C() + adafruit_vl6180x.VL6180X). 한 번만 생성."""
    global _adafruit_sensor
    if not _ADAFRUIT_AVAILABLE:
        return None
    with _i2c_lock:
        if _adafruit_sensor is None:
            try:
                i2c = board.I2C()
                _adafruit_sensor = adafruit_vl6180x.VL6180X(i2c)
            except Exception:
                return None
        return _adafruit_sensor


def reset_i2c_connection():
    """연결 해제. 다음 측정 시 새로 생성."""
    global _adafruit_sensor
    with _i2c_lock:
        _adafruit_sensor = None


def _atexit_release():
    """프로세스 종료 시 센서 참조 해제."""
    reset_i2c_connection()


if _IS_LINUX:
    atexit.register(_atexit_release)


def _read_distance_mm():
    """거리 1회 측정 (mm). 실패 시 None."""
    try:
        s = _get_sensor()
        if s is not None:
            with _i2c_lock:
                return s.range
    except Exception:
        pass
    return None


def _script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _config_path():
    return os.path.join(_script_dir(), "sensor_config.json")


def load_sensor_config():
    """sensor_config.json에서 enabled, threshold_cm 로드."""
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "enabled": bool(data.get("enabled", False)),
                "threshold_cm": max(10, min(50, int(data.get("threshold_cm", 50)))),
            }
    except Exception:
        return {"enabled": False, "threshold_cm": 50}


def save_sensor_config(enabled, threshold_cm):
    """sensor_config.json에 저장."""
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled, "threshold_cm": threshold_cm}, f, indent=2)
    except Exception:
        pass


class DistanceSensorController:
    """
    TOF050C 거리 센서: 주기적으로 거리 측정,
    threshold_cm 이내이고 enabled이면 on_near 콜백 호출(대기 타이머 리셋용).
    """

    def __init__(self, on_near, schedule_main):
        self.on_near = on_near
        self.schedule_main = schedule_main
        cfg = load_sensor_config()
        self._enabled = cfg["enabled"]
        self._threshold_cm = cfg["threshold_cm"]
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._poll_interval = 0.35
        self._MAX_FAILURES_BEFORE_RESET = 10

    def start(self):
        if not _IS_LINUX or not _ADAFRUIT_AVAILABLE:
            return
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _poll_loop(self):
        consecutive = 0
        while True:
            with self._lock:
                if not self._running:
                    break
                enabled = self._enabled
                threshold_mm = self._threshold_cm * 10
            if not enabled:
                time.sleep(self._poll_interval)
                continue
            d = _read_distance_mm()
            if d is not None:
                consecutive = 0
                if 0 <= d <= threshold_mm:
                    try:
                        self.schedule_main(self.on_near)
                    except Exception:
                        pass
            else:
                consecutive += 1
                if consecutive >= self._MAX_FAILURES_BEFORE_RESET:
                    reset_i2c_connection()
                    consecutive = 0
                    time.sleep(0.5)
            time.sleep(self._poll_interval)

    def set_enabled(self, enabled):
        with self._lock:
            self._enabled = bool(enabled)
        save_sensor_config(self._enabled, self._threshold_cm)

    def set_threshold_cm(self, cm):
        cm = max(10, min(50, int(cm)))
        with self._lock:
            self._threshold_cm = cm
        save_sensor_config(self._enabled, self._threshold_cm)

    def get_enabled(self):
        with self._lock:
            return self._enabled

    def get_threshold_cm(self):
        with self._lock:
            return self._threshold_cm

    def read_once_mm(self):
        """현재 거리 1회 측정 (mm). None이면 측정 불가."""
        return _read_distance_mm()
