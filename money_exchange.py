import json
import os
import subprocess
import sys
import threading

# 플랫폼: 라즈비안/리눅스 자동 감지 (Windows는 "nt")
_IS_LINUX = sys.platform.startswith("linux")

# Linux: fontconfig에 resource/fonts 등록 (Tk 로드 전에 실행)
if _IS_LINUX:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _font_dir = os.path.join(_script_dir, "resource", "fonts")
    if os.path.isdir(_font_dir):
        _conf_path = os.path.join(_font_dir, "fonts.conf")
        _dir_escaped = _font_dir.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        try:
            with open(_conf_path, "w") as _f:
                _f.write(
                    '<?xml version="1.0"?>\n'
                    '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
                    "<fontconfig>\n  <dir>"
                    + _dir_escaped
                    + "</dir>\n</fontconfig>\n"
                )
            os.environ["FONTCONFIG_FILE"] = _conf_path
            subprocess.run(
                ["fc-cache", "-f", _font_dir],
                capture_output=True,
                timeout=15,
                cwd=_script_dir,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

import tkinter as tk
import tkinter.font as tkfont

from screensaver import ScreenSaverConfig, ScreenSaverController
from gif_player import GifPlayer
from sound_manager import SoundManager
from serial_manager import BillSerialManager
from sensor import DistanceSensorController, load_sensor_config

CUSTOM_FONT_FAMILY = ""
PREFERRED_FONT_FAMILIES = [
    "KyoboHandwriting2024psw",
    "Kyobo Handwriting 2024",
    "Kyobo Handwriting 2024 psw",
]
# 시리얼 포트: 라즈베리 파이(라즈비안) 전용. Windows(COM3)는 개발용으로만 참고.
SERIAL_PORTS = ["/dev/bill", "/dev/serial0", "/dev/ttyAMA0", "/dev/ttyS0", "/dev/ttyUSB0"]
# 라즈비안 키오스크: True 시 전체화면 + 마우스 커서 숨김 (터치 전용)
RASPBERRY_PI_KIOSK = True


class MoneyExchanger:
    def __init__(self, root):
        """Initialize UI, state, and hardware interfaces."""
        self.root = root
        self.root.title("지폐 교환기")
        self.root.geometry("1024x600+0+0")
        self.root.resizable(False, False)
        self._kiosk_active = False
        if _IS_LINUX and RASPBERRY_PI_KIOSK:
            self._kiosk_active = True
            self.root.bind("<Escape>", self._exit_kiosk)
            self.root.after(400, self._apply_kiosk)

        # 상태 변수
        self.total_money = 0
        self.total_1000 = 0
        self.total_5000 = 0
        self.total_10000 = 0
        self.last_bill_amount = 0
        self.selected_1000 = 0
        self.is_processing = False
        self.admin_clicks = 0
        self.admin_password = "2857"
        self.is_acceptor_disabled = False
        # Linux 기본 폰트(라즈비안 포함), Windows는 맑은고딕
        self.font_family = "DejaVu Sans" if _IS_LINUX else "Malgun Gothic"
        self.custom_font_family = self.font_family
        self.volume_var = tk.DoubleVar(value=80)
        self.load_custom_fonts()
        self.sound = SoundManager(self.root, self.volume_var)
        self.sound.load_sounds()
        screensaver_config = ScreenSaverConfig()
        self.screensaver = ScreenSaverController(
            self.root,
            screensaver_config,
            self.show_screen,
            lambda: getattr(self, "current_screen", ""),
            "화면을 터치해 주세요",
            self.font_family,
        )
        self.screensaver.set_enabled(self._load_screensaver_enabled())

        # 거리 센서 (TOF050C): 50cm 이내 시 대기 타이머 리셋. Linux 전용.
        self.distance_sensor = DistanceSensorController(
            on_near=self.screensaver.notify_activity,
            schedule_main=lambda fn: self.root.after(0, fn),
        )

        # UI 구성
        self.screens = {}
        self.build_screens()
        self.show_screen("idle")
        # 라즈비안: 창이 먼저 그려진 뒤 스크린세이버 시작 (화면 안 나오는 현상 방지)
        if _IS_LINUX:
            self.root.after(500, self.screensaver.start)
        else:
            self.screensaver.start()
        if _IS_LINUX:
            self.root.after(600, self.distance_sensor.start)

        # 시리얼 시작 (GUI 뜬 뒤 잠깐 지연 후 열기 — 라즈비안에서 /dev/bill 준비 대기)
        self.serial = BillSerialManager(
            self.root, SERIAL_PORTS, self.on_bill_detected, self.show_error_screen
        )
        self.root.after(800, self._start_serial)

    def _start_serial(self):
        """시리얼 포트 열기 (지연 후 실행). 실패 시 한 번 더 재시도."""
        self.serial.start()
        if self.serial.ser is None:
            self.root.after(2000, self._retry_serial)

    def _retry_serial(self):
        """시리얼 열기 재시도 (부팅 직후 /dev/bill 미준비 대응)."""
        self.serial.start()

    def _apply_kiosk(self):
        """창이 뜬 뒤 키오스크(전체화면·커서숨김) 적용. 라즈비안에서 초기 적용이 무시되는 경우 대비."""
        if not getattr(self, "_kiosk_active", False):
            return
        try:
            self.root.attributes("-fullscreen", True)
            self.root.config(cursor="none")
        except Exception:
            pass

    def _exit_kiosk(self, event=None):
        """키오스크 모드에서 ESC로 전체화면 해제·커서 복원."""
        if not getattr(self, "_kiosk_active", False):
            return
        self._kiosk_active = False
        try:
            self.root.attributes("-fullscreen", False)
            self.root.config(cursor="")
        except Exception:
            pass
        self.root.unbind("<Escape>")

    # =====================================================
    # Screen 관리
    # =====================================================
    def show_thanks(self):
        """Switch to thanks screen and play audio."""
        self.show_screen("thanks")
        self.sound.play_sound("thanks")

    def load_custom_fonts(self):
        """Load custom fonts from the resource folder."""
        font_dir = os.path.join(os.path.dirname(__file__), "resource", "fonts")
        if not os.path.isdir(font_dir):
            return

        font_files = [
            f for f in os.listdir(font_dir)
            if f.lower().endswith((".ttf", ".otf"))
        ]
        if not font_files:
            return

        try:
            before = set(tkfont.families(self.root))
        except Exception:
            before = set()

        # Windows에서만 GDI로 폰트 등록; Linux는 상단 fontconfig 처리로 이미 등록됨
        for filename in font_files:
            font_path = os.path.join(font_dir, filename)
            try:
                if not _IS_LINUX and sys.platform == "win32":
                    import ctypes
                    ctypes.windll.gdi32.AddFontResourceExW(font_path, 0x10, 0)
            except Exception:
                continue

        try:
            after = set(tkfont.families(self.root))
        except Exception:
            after = set()

        candidates = sorted(after - before)
        if not candidates:
            candidates = sorted(after)
        non_vertical = [fam for fam in candidates if not fam.startswith("@")]
        if non_vertical:
            candidates = non_vertical
        preferred = []
        if CUSTOM_FONT_FAMILY:
            preferred.append(CUSTOM_FONT_FAMILY)
        preferred.extend(PREFERRED_FONT_FAMILIES)
        preferred.extend(os.path.splitext(f)[0] for f in font_files)

        for pref in preferred:
            for fam in candidates:
                if fam.lower() == pref.lower() or pref.lower() in fam.lower():
                    self.font_family = fam
                    self.custom_font_family = fam
                    return

        if candidates:
            self.font_family = candidates[0]
            self.custom_font_family = candidates[0]

    def show_screen(self, name, play_hello=None):
        """Show a named screen and synchronize animations. idle일 때 play_hello=False면 hello.mp3 미재생(배출 후 복귀용)."""
        for f in self.screens.values():
            f.pack_forget()
        self.screens[name].pack(fill=tk.BOTH, expand=True)
        self.current_screen = name
        if name != "idle":
            self.admin_clicks = 0
            if hasattr(self, "stop_idle_corner_animation"):
                self.stop_idle_corner_animation()
        else:
            self.update_idle_status()
            if self.current_screen != "idle":
                return
            if hasattr(self, "start_idle_corner_animation"):
                self.start_idle_corner_animation()
            if play_hello is not False:
                self.sound.stop_sound("hello")
                self.sound.play_sound("hello", wait=False)
        if name == "thanks":
            self.start_thanks_animation()
            self.root.update_idletasks()
            self.root.update()
        else:
            self.stop_thanks_animation()
        if hasattr(self, "screensaver"):
            self.screensaver.on_show_screen(name)
        if name == "error":
            self.start_error_no_animation()
        else:
            self.stop_error_no_animation()

    def build_screens(self):
        """Create and register all screens."""
        self.screens["idle"] = self.build_idle_screen()
        self.screens["select"] = self.build_select_screen()
        self.screens["processing"] = self.build_processing_screen()
        self.screens["thanks"] = self.build_thanks_screen()
        self.screens["admin"] = self.build_admin_screen()
        self.screens["error"] = self.build_error_screen()
        self.screens["screensaver"] = self.screensaver.build_screen()

    # =====================================================
    # Idle Screen
    # =====================================================
    def build_idle_screen(self):
        """Build the idle screen layout."""
        f = tk.Frame(self.root, bg="#000231")

        tk.Label(
            f, text="♪천원 OK! ♪오천원 OK! ♪만원 OK!",
            font=(self.font_family, 36, "bold"),
            fg="#facc15", bg="#000231"
        ).pack(pady=(60, 10))

        self.idle_title_label = tk.Label(
            f, text="동전 교환기",
            font=(self.custom_font_family, 150, "bold"),
            fg="white", bg="#000231"
        )
        self.idle_title_label.pack(pady=40)

        gif_dir = os.path.join(os.path.dirname(__file__), "resource", "gif")

        idle_gif_path = os.path.join(gif_dir, "gif_hello3.gif")
        idle_gif_path_left = os.path.join(gif_dir, "gif_hello4.gif")
        self.idle_corner_player = GifPlayer(self.root, idle_gif_path, bg=f["bg"])
        self.idle_corner_left_player = GifPlayer(
            self.root, idle_gif_path_left, bg=f["bg"]
        )
        self.idle_corner_label = self.idle_corner_player.create_label(f)
        self.idle_corner_left_label = self.idle_corner_left_player.create_label(f)
        # 우하 / 좌하 배치
        self.idle_corner_label.place(relx=1.0, rely=1.0, x=-40, y=-40, anchor="se")
        self.idle_corner_left_label.place(x=40, rely=1.0, y=-40, anchor="sw")

        self.idle_status_font_normal = (self.font_family, 38)
        self.idle_status_font_disabled = (self.font_family, 80, "bold")
        self.idle_status_label = tk.Label(
            f, text="지폐를 넣어주세요",
            font=self.idle_status_font_normal,
            fg="#e5e7eb", bg="#000231"
        )
        self.idle_status_label.pack(pady=10)

        self.idle_info_label = tk.Label(
            f, text="김세복 대추밀냉면",
            font=(self.font_family, 28),
            fg="#9ca3af", bg="#000231"
        )
        self.idle_info_label.pack(pady=10)

        admin_btn = tk.Button(
            f,
            text="",
            bg="#000231",
            activebackground="#000231",
            borderwidth=0,
            highlightthickness=0,
            command=self.on_admin_click
        )
        admin_btn.place(relx=1.0, x=-10, y=10, anchor="ne", width=100, height=100)

        return f

    # =====================================================
    # Select Screen
    # =====================================================
    def build_select_screen(self):
        """Build the change selection screen layout."""
        f = tk.Frame(self.root, bg="#111827")

        # 상단 영역 (늘어나는 영역)
        top = tk.Frame(f, bg="#111827")
        top.pack(fill=tk.BOTH, expand=True)

        self.ui_amount = tk.Label(
            top, text="0원",
            font=(self.font_family, 68, "bold"),
            fg="#facc15", bg="#111827"
        )
        self.ui_amount.pack(pady=(30, 10))

        tk.Label(
            top, text="반환 받으실 1000원권 장수를 선택해 주세요",
            font=(self.font_family, 24),
            fg="white", bg="#111827"
        ).pack(pady=(0, 10))

        mid = tk.Frame(top, bg="#111827")
        mid.pack(pady=10)

        self.btn_minus = tk.Button(
            mid, text="-",
            font=(self.font_family, 52, "bold"),
            width=4, height=2,
            bg="#2563eb", fg="white",
            command=self.decrease_1000
        )
        self.btn_minus.pack(side=tk.LEFT, padx=20)

        self.ui_1000 = tk.Label(
            mid, text="0 장",
            font=(self.font_family, 72, "bold"),
            fg="white", bg="#111827"
        )
        self.ui_1000.pack(side=tk.LEFT)

        self.btn_plus = tk.Button(
            mid, text="+",
            font=(self.font_family, 52, "bold"),
            width=4, height=2,
            bg="#2563eb", fg="white",
            command=self.increase_1000
        )
        self.btn_plus.pack(side=tk.LEFT, padx=20)

        self.ui_500 = tk.Label(
            top, text="500원 x 0",
            font=(self.font_family, 26),
            fg="#9ca3af", bg="#111827"
        )
        self.ui_500.pack(pady=10)

        # 하단 고정 영역 (버튼 절대 안 잘림)
        bottom = tk.Frame(f, bg="#111827", height=120)
        bottom.pack(fill=tk.X)
        bottom.pack_propagate(False)

        self.btn_confirm = tk.Button(
            bottom, text="확인",
            font=(self.font_family, 44, "bold"),
            bg="#16a34a", fg="white",
            height=2, width=12,
            command=self.confirm_change
        )
        self.btn_confirm.pack(pady=20)

        return f

    # =====================================================
    # Processing Screen
    # =====================================================
    def build_processing_screen(self):
        """Build the processing screen layout."""
        f = tk.Frame(self.root, bg="#fcf0e4")

        tk.Label(
            f, text="교환 중입니다…",
            font=(self.font_family, 60, "bold"),
            fg="black", bg="#fcf0e4"
        ).pack(pady=40)

        tk.Label(
            f, text="잠시만 기다려 주세요",
            font=(self.font_family, 35),
            fg="#515151", bg="#fcf0e4"
        ).pack(pady=10)

        gif_dir = os.path.join(os.path.dirname(__file__), "resource", "gif")
        gif_path = os.path.join(gif_dir, "gif_loading.gif")
        # if not os.path.isfile(gif_path) and os.path.isdir(gif_dir):
        #     for fname in os.listdir(gif_dir):
        #         lower_name = fname.lower()
        #         if "loading" in lower_name and lower_name.endswith(".gif"):
        #             gif_path = os.path.join(gif_dir, fname)
        #             break

        self.processing_player = GifPlayer(self.root, gif_path, bg="#fcf0e4")
        self.processing_gif_label = self.processing_player.create_label(f)
        self.processing_gif_label.pack(pady=20)

        return f

    def start_processing_anim(self):
        """Start the processing animation."""
        self.processing_player.start()

    def stop_processing_anim(self):
        """Stop the processing animation."""
        self.processing_player.stop()

    # =====================================================
    # Thanks / Error
    # =====================================================
    def build_thanks_screen(self):
        """Build the thanks screen layout."""
        f = tk.Frame(self.root, bg="#fcf0e3")

        gif_dir = os.path.join(os.path.dirname(__file__), "resource", "gif")
        gif_path = os.path.join(gif_dir, "gif_Thanks2.gif")
        # if not os.path.isfile(gif_path) and os.path.isdir(gif_dir):
        #     for fname in os.listdir(gif_dir):
        #         lower_name = fname.lower()
        #         if "thanks" in lower_name and lower_name.endswith(".gif"):
        #             gif_path = os.path.join(gif_dir, fname)
        #             break
        self.thanks_player = GifPlayer(self.root, gif_path, bg="#fcf0e3")
        self.thanks_gif_label = self.thanks_player.create_label(f)
        self.thanks_gif_label.pack(pady=(100, 40))

        return f

    def start_thanks_animation(self):
        """Start the thanks animation if frames exist."""
        self.thanks_player.start()

    def stop_thanks_animation(self):
        """Stop the thanks animation."""
        self.thanks_player.stop()

    def build_admin_screen(self):
        """Build the admin screen layout: 가로 2등분 + 나가기 하단 중앙."""
        f = tk.Frame(self.root, bg="#0b1020")

        content = tk.Frame(f, bg="#0b1020")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 왼쪽 절반
        left = tk.Frame(content, bg="#0b1020")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.btn_admin_reset = tk.Button(
            left, text="올 리셋 (투입기/배출기)",
            font=(self.font_family, 20, "bold"),
            bg="#1d4ed8", fg="white",
            width=22, height=2,
            command=self._admin_reset_with_sound
        )
        self.btn_admin_reset.pack(pady=15)

        self.btn_admin_toggle = tk.Button(
            left, text="사용중지: OFF",
            font=(self.font_family, 20, "bold"),
            bg="#334155", fg="white",
            width=22, height=2,
            command=self._admin_toggle_with_sound
        )
        self.btn_admin_toggle.pack(pady=15)

        volume_frame = tk.Frame(left, bg="#0b1020")
        volume_frame.pack(pady=10)

        tk.Label(
            volume_frame, text="볼륨",
            font=(self.font_family, 18, "bold"),
            fg="white", bg="#0b1020"
        ).pack(pady=(0, 8))

        tk.Scale(
            volume_frame,
            from_=0, to=100,
            orient=tk.HORIZONTAL,
            length=350,
            width=50,
            showvalue=True,
            variable=self.volume_var,
            command=lambda _val: self.sound.apply_volume(),
            bg="#0b1020",
            fg="white",
            troughcolor="#334155",
            highlightthickness=0
        ).pack()

        tk.Button(
            volume_frame, text="테스트",
            font=(self.font_family, 16, "bold"),
            bg="#22c55e", fg="white",
            width=10, height=1,
            command=self._admin_volume_test_with_sound
        ).pack(pady=15)

        # 스크린세이버 on/off
        self.btn_admin_screensaver = tk.Button(
            left, text="스크린세이버: ON",
            font=(self.font_family, 18, "bold"),
            bg="#6366f1", fg="white",
            width=22, height=1,
            command=self._admin_screensaver_toggle
        )
        self.btn_admin_screensaver.pack(pady=10)
        self._update_screensaver_button_state()

        # 오른쪽 절반
        right = tk.Frame(content, bg="#0b1020")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        if _IS_LINUX:
            rf_frame = tk.Frame(right, bg="#0b1020")
            rf_frame.pack(pady=10)
            tk.Label(
                rf_frame, text="WiFi / Bluetooth",
                font=(self.font_family, 18, "bold"),
                fg="white", bg="#0b1020"
            ).pack(pady=(0, 8))
            rf_btn_f = tk.Frame(rf_frame, bg="#0b1020")
            rf_btn_f.pack()
            self.btn_admin_wifi = tk.Button(
                rf_btn_f, text="WiFi",
                font=(self.font_family, 16, "bold"),
                bg="#6366f1", fg="white",
                width=12, height=1,
                command=self._admin_wifi_toggle
            )
            self.btn_admin_wifi.pack(side=tk.LEFT, padx=8)
            self.btn_admin_bluetooth = tk.Button(
                rf_btn_f, text="Bluetooth",
                font=(self.font_family, 16, "bold"),
                bg="#6366f1", fg="white",
                width=14, height=1,
                command=self._admin_bluetooth_toggle
            )
            self.btn_admin_bluetooth.pack(side=tk.LEFT, padx=8)
            self._update_rf_button_states()

            # 거리 센서 (TOF050C): on/off, 거리(10~50cm) 조절
            sensor_frame = tk.Frame(right, bg="#0b1020")
            sensor_frame.pack(pady=10)
            tk.Label(
                sensor_frame, text="거리 센서 (대기 타이머 리셋)",
                font=(self.font_family, 18, "bold"),
                fg="white", bg="#0b1020"
            ).pack(pady=(0, 8))
            self.btn_admin_sensor = tk.Button(
                sensor_frame, text="센서: ON",
                font=(self.font_family, 16, "bold"),
                bg="#6366f1", fg="white",
                width=14, height=1,
                command=self._admin_sensor_toggle
            )
            self.btn_admin_sensor.pack(pady=(0, 6))
            tk.Label(
                sensor_frame, text="감지 거리 (cm)",
                font=(self.font_family, 14),
                fg="white", bg="#0b1020"
            ).pack(pady=(0, 4))
            self.sensor_threshold_var = tk.IntVar(
                value=self.distance_sensor.get_threshold_cm()
            )
            tk.Scale(
                sensor_frame,
                from_=10, to=50,
                orient=tk.HORIZONTAL,
                length=280,
                showvalue=True,
                variable=self.sensor_threshold_var,
                command=self._admin_sensor_threshold_changed,
                bg="#0b1020", fg="white",
                troughcolor="#334155",
                highlightthickness=0
            ).pack()
            self._update_sensor_button_state()

            tk.Button(
                right, text="전원 끄기",
                font=(self.font_family, 20, "bold"),
                bg="#b91c1c", fg="white",
                width=22, height=2,
                command=self._admin_shutdown_with_sound
            ).pack(pady=15)

        # 하단 중앙: 나가기
        bottom = tk.Frame(f, bg="#0b1020")
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=15)
        tk.Frame(bottom, bg="#0b1020").pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Button(
            bottom, text="나가기",
            font=(self.font_family, 20, "bold"),
            bg="#0f172a", fg="white",
            width=22, height=2,
            command=self._admin_exit_with_sound
        ).pack(side=tk.LEFT)
        tk.Frame(bottom, bg="#0b1020").pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        return f

    def _admin_reset_with_sound(self):
        self.sound.play_sound("button", wait=False)
        self.reset_all_devices()

    def _admin_toggle_with_sound(self):
        self.sound.play_sound("button", wait=False)
        self.toggle_acceptor()

    def _admin_volume_test_with_sound(self):
        self.sound.play_sound("button", wait=False)
        self.sound.play_sound("volume_test", wait=False)

    def _admin_exit_with_sound(self):
        self.sound.play_sound("button", wait=False)
        self.show_screen("idle")

    def _screensaver_config_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "screensaver_config.json")

    def _load_screensaver_enabled(self):
        try:
            with open(self._screensaver_config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("enabled", True))
        except Exception:
            return True

    def _save_screensaver_enabled(self, enabled):
        try:
            with open(self._screensaver_config_path(), "w", encoding="utf-8") as f:
                json.dump({"enabled": enabled}, f, indent=2)
        except Exception:
            pass

    def _admin_screensaver_toggle(self):
        self.sound.play_sound("button", wait=False)
        self.screensaver.set_enabled(not self.screensaver.get_enabled())
        self._save_screensaver_enabled(self.screensaver.get_enabled())
        self._update_screensaver_button_state()

    def _update_screensaver_button_state(self):
        if not hasattr(self, "btn_admin_screensaver") or not self.btn_admin_screensaver.winfo_exists():
            return
        if self.screensaver.get_enabled():
            self.btn_admin_screensaver.config(bg="#6366f1", text="스크린세이버: ON")
        else:
            self.btn_admin_screensaver.config(bg="#b91c1c", text="스크린세이버: OFF")

    def _admin_sensor_toggle(self):
        self.sound.play_sound("button", wait=False)
        self.distance_sensor.set_enabled(not self.distance_sensor.get_enabled())
        self._update_sensor_button_state()

    def _admin_sensor_threshold_changed(self, value):
        try:
            cm = int(round(float(value)))
            self.distance_sensor.set_threshold_cm(cm)
        except (ValueError, TypeError):
            pass

    def _update_sensor_button_state(self):
        if not _IS_LINUX or not hasattr(self, "btn_admin_sensor"):
            return
        if not self.btn_admin_sensor.winfo_exists():
            return
        en = self.distance_sensor.get_enabled()
        if en:
            self.btn_admin_sensor.config(bg="#6366f1", text="센서: ON")
        else:
            self.btn_admin_sensor.config(bg="#b91c1c", text="센서: OFF")

    def _rfkill_soft_blocked(self, device):
        """rfkill으로 device(wifi/bluetooth)의 Soft blocked 여부. True=OFF, False=ON, None=알 수 없음."""
        try:
            out = subprocess.run(
                ["rfkill", "list", device],
                timeout=3,
                capture_output=True,
                text=True,
            )
            if out.returncode != 0 or not out.stdout:
                return None
            if "Soft blocked: yes" in out.stdout:
                return True
            if "Soft blocked: no" in out.stdout:
                return False
        except Exception:
            pass
        return None

    def _update_rf_button_states(self):
        """WiFi/Bluetooth 버튼을 상태에 따라 ON=파란색, OFF=빨간색으로 갱신. 메인 스레드에서만 호출."""
        if not _IS_LINUX:
            return
        blue, red = "#6366f1", "#b91c1c"
        if hasattr(self, "btn_admin_wifi") and self.btn_admin_wifi.winfo_exists():
            blocked = self._rfkill_soft_blocked("wifi")
            if blocked is False:
                self.btn_admin_wifi.config(bg=blue, text="WiFi: ON")
            elif blocked is True:
                self.btn_admin_wifi.config(bg=red, text="WiFi: OFF")
            else:
                self.btn_admin_wifi.config(bg="#64748b", text="WiFi")
        if hasattr(self, "btn_admin_bluetooth") and self.btn_admin_bluetooth.winfo_exists():
            blocked = self._rfkill_soft_blocked("bluetooth")
            if blocked is False:
                self.btn_admin_bluetooth.config(bg=blue, text="Bluetooth: ON")
            elif blocked is True:
                self.btn_admin_bluetooth.config(bg=red, text="Bluetooth: OFF")
            else:
                self.btn_admin_bluetooth.config(bg="#64748b", text="Bluetooth")

    def _admin_wifi_toggle(self):
        """라즈비안: WiFi on/off 토글 (rfkill)."""
        self.sound.play_sound("button", wait=False)

        def _run():
            try:
                subprocess.run(
                    ["sudo", "rfkill", "toggle", "wifi"],
                    timeout=5,
                    capture_output=True,
                )
            except Exception:
                try:
                    subprocess.run(
                        ["rfkill", "toggle", "wifi"],
                        timeout=5,
                        capture_output=True,
                    )
                except Exception:
                    pass
            self.root.after(0, self._update_rf_button_states)

        threading.Thread(target=_run, daemon=True).start()

    def _admin_bluetooth_toggle(self):
        """라즈비안: Bluetooth on/off 토글 (rfkill)."""
        self.sound.play_sound("button", wait=False)

        def _run():
            try:
                subprocess.run(
                    ["sudo", "rfkill", "toggle", "bluetooth"],
                    timeout=5,
                    capture_output=True,
                )
            except Exception:
                try:
                    subprocess.run(
                        ["rfkill", "toggle", "bluetooth"],
                        timeout=5,
                        capture_output=True,
                    )
                except Exception:
                    pass
            self.root.after(0, self._update_rf_button_states)

        threading.Thread(target=_run, daemon=True).start()

    def _admin_shutdown_with_sound(self):
        self.sound.play_sound("button", wait=False)
        self._confirm_shutdown_pi()

    def _confirm_shutdown_pi(self):
        """라즈베리 파이 전원 끄기 확인 후 실행."""
        dlg = tk.Toplevel(self.root)
        dlg.title("전원 끄기")
        dlg.geometry("320x140")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(
            dlg, text="라즈베리 파이 전원을 끄시겠습니까?",
            font=(self.font_family, 14), wraplength=280
        ).pack(pady=(20, 15))
        btn_f = tk.Frame(dlg)
        btn_f.pack(pady=10)

        def do_shutdown():
            dlg.destroy()
            if _IS_LINUX:
                try:
                    subprocess.run(
                        ["sudo", "shutdown", "-h", "now"],
                        timeout=5,
                        capture_output=True,
                    )
                except Exception:
                    try:
                        subprocess.run(
                            ["shutdown", "-h", "now"],
                            timeout=5,
                            capture_output=True,
                        )
                    except Exception:
                        pass

        tk.Button(
            btn_f, text="예, 전원 끄기",
            font=(self.font_family, 12), bg="#b91c1c", fg="white",
            width=14, command=do_shutdown
        ).pack(side=tk.LEFT, padx=8)
        tk.Button(
            btn_f, text="취소",
            font=(self.font_family, 12), width=10, command=dlg.destroy
        ).pack(side=tk.LEFT, padx=8)

    def build_error_screen(self):
        """Build the error screen layout."""
        f = tk.Frame(self.root, bg="#7f1d1d")

        gif_dir = os.path.join(os.path.dirname(__file__), "resource", "gif")
        gif_path = os.path.join(gif_dir, "gif_no.gif")
        if not os.path.isfile(gif_path) and os.path.isdir(gif_dir):
            for fname in os.listdir(gif_dir):
                lower_name = fname.lower()
                if "no" in lower_name and lower_name.endswith(".gif"):
                    gif_path = os.path.join(gif_dir, fname)
                    break

        self.error_no_player = GifPlayer(self.root, gif_path, bg="#7f1d1d")
        self.error_no_label = self.error_no_player.create_label(f)
        self.error_no_label.pack(pady=(80, 20))

        tk.Label(
            f, text="현재 사용 중지",
            font=(self.font_family, 80, "bold"),
            fg="white", bg="#7f1d1d"
        ).pack(pady=(10, 20))

        tk.Label(
            f,
            text="죄송합니다. 빠른 조치 하겠습니다.\n-김세복대추밀냉면",
            font=(self.font_family, 22),
            fg="white", bg="#7f1d1d",
            justify="center"
        ).pack(pady=30)

        admin_btn = tk.Button(
            f,
            text="",
            bg="#7f1d1d",
            activebackground="#7f1d1d",
            borderwidth=0,
            highlightthickness=0,
            command=self.on_admin_click
        )
        admin_btn.place(relx=1.0, x=-10, y=10, anchor="ne", width=100, height=100)

        return f

    def show_error_screen(self):
        """Show the error screen if not processing."""
        if self.is_processing:
            return
        self.show_screen("error")
        self.start_error_no_animation()

    def start_error_no_animation(self):
        """Start the error animation if available."""
        self.error_no_player.start()

    def stop_error_no_animation(self):
        """Stop the error animation."""
        self.error_no_player.stop()

    def start_idle_corner_animation(self):
        """Start idle corner GIF animation."""
        self.idle_corner_player.start()
        self.idle_corner_left_player.start()

    def stop_idle_corner_animation(self):
        """Stop idle corner animation."""
        self.idle_corner_player.stop()
        self.idle_corner_left_player.stop()

    def update_idle_status(self):
        """Refresh idle screen status labels."""
        if not hasattr(self, "idle_status_label"):
            return
        if self.is_acceptor_disabled:
            self.show_error_screen()
            return
        else:
            self.idle_status_label.config(
                text="지폐를 넣어주세요",
                fg="#e5e7eb",
                font=self.idle_status_font_normal
            )
            if hasattr(self, "idle_info_label"):
                self.idle_info_label.config(
                    text="김세복 대추밀냉면",
                    fg="#9ca3af"
                )
            if hasattr(self, "idle_title_label"):
                self.idle_title_label.pack_forget()
                self.idle_title_label.pack(pady=40, before=self.idle_status_label)

    def on_admin_click(self):
        """Handle hidden admin entry clicks."""
        self.admin_clicks += 1
        if self.admin_clicks >= 5:
            self.admin_clicks = 0
            self.show_password_dialog()

    def show_password_dialog(self):
        """Display admin password keypad dialog. 세로 600px 이내."""
        dlg = tk.Toplevel(self.root)
        dlg.geometry("420x560")
        dlg.resizable(False, False)
        dlg.overrideredirect(True)
        dlg.grab_set()

        tk.Label(
            dlg, text="비밀번호를 입력하세요",
            font=(self.font_family, 20)
        ).pack(pady=(16, 10))

        pw_var = tk.StringVar()
        entry = tk.Entry(dlg, textvariable=pw_var, show="*", font=(self.font_family, 20), width=10)
        entry.pack(pady=8)
        entry.focus_set()

        def submit():
            if pw_var.get() == self.admin_password:
                dlg.destroy()
                self.show_screen("admin")
            else:
                pw_var.set("")
                entry.focus_set()

        keypad = tk.Frame(dlg)
        keypad.pack(pady=8)

        def add_digit(d):
            pw_var.set(pw_var.get() + str(d))
            entry.focus_set()

        def backspace():
            pw_var.set(pw_var.get()[:-1])
            entry.focus_set()

        def clear_all():
            pw_var.set("")
            entry.focus_set()

        buttons = [
            ("1", lambda: add_digit(1)),
            ("2", lambda: add_digit(2)),
            ("3", lambda: add_digit(3)),
            ("4", lambda: add_digit(4)),
            ("5", lambda: add_digit(5)),
            ("6", lambda: add_digit(6)),
            ("7", lambda: add_digit(7)),
            ("8", lambda: add_digit(8)),
            ("9", lambda: add_digit(9)),
            ("지움", backspace),
            ("0", lambda: add_digit(0)),
            ("전체삭제", clear_all),
        ]

        for idx, (label, cmd) in enumerate(buttons):
            r, c = divmod(idx, 3)
            tk.Button(
                keypad, text=label,
                font=(self.font_family, 18),
                width=5, height=2,
                command=cmd
            ).grid(row=r, column=c, padx=5, pady=5)

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=8)

        tk.Button(
            btn_frame, text="확인",
            font=(self.font_family, 26),
            width=7, height=2, command=submit
        ).pack(side=tk.LEFT, padx=6)

        tk.Button(
            btn_frame, text="취소",
            font=(self.font_family, 26),
            width=7, height=2, command=dlg.destroy
        ).pack(side=tk.LEFT, padx=6)

    # =====================================================
    # 버튼 로직
    # =====================================================
    def increase_1000(self):
        """Increase selected 1000-won bill count."""
        self.sound.play_sound("button", wait=False)
        self.selected_1000 += 1
        self.update_change_controls()

    def decrease_1000(self):
        """Decrease selected 1000-won bill count."""
        self.sound.play_sound("button", wait=False)
        self.selected_1000 -= 1
        self.update_change_controls()

    def update_change_controls(self):
        """Update change selection labels based on amount."""
        amount = self.last_bill_amount
        max_1000 = (amount - 1000) // 1000 if amount else 0
        if max_1000 < 0:
            max_1000 = 0
        self.selected_1000 = max(0, min(self.selected_1000, max_1000))
        remaining = amount - self.selected_1000 * 1000
        count_500 = max(0, remaining // 500)

        self.ui_1000.config(text=f"{self.selected_1000} 장")
        self.ui_500.config(text=f"500원 x {count_500}")

    def confirm_change(self):
        """Confirm change selection and trigger payout. confirm 사운드가 시작된 뒤 나머지 진행."""
        self.sound.play_sound("confirm", wait=False)
        self.root.after(120, self._confirm_change_continue)

    def _confirm_change_continue(self):
        """confirm_change에서 confirm 재생 후 실제 처리."""
        amount = self.last_bill_amount
        remaining = amount - self.selected_1000 * 1000
        count_500 = max(0, remaining // 500)

        self.sound.stop_input_sounds()
        self.sound.stop_sound("in_1000won")
        self.is_processing = True
        self.show_screen("processing")
        self.start_processing_anim()

        self.root.after(
            300,
            lambda: (self.sound.play_sound("out_money"),
                     self.send_combined_payout(count_500, self.selected_1000))
        )

        if amount == 5000:
            extra_delay = 3000
        elif amount == 10000:
            extra_delay = 5000
        else:
            extra_delay = 0
        base_delay = 1800 + extra_delay
        self.root.after(base_delay, self.stop_processing_anim)
        self.root.after(base_delay, self.show_thanks)
        self.root.after(base_delay + 3000, self.finish_processing)

    # =====================================================
    # 시리얼 / 패킷
    # =====================================================
    def enable_bill_acceptor(self):
        """Enable bill acceptor."""
        self.serial.enable_bill_acceptor()

    def clear_bill_acceptor(self):
        """Clear bill acceptor state."""
        self.serial.clear_bill_acceptor()

    def disable_bill_acceptor(self):
        """Disable bill acceptor."""
        self.serial.disable_bill_acceptor()

    def reset_coin_hopper(self):
        """Reset coin hopper."""
        self.serial.reset_coin_hopper()

    def reset_bill_dispenser(self):
        """Reset bill dispenser."""
        self.serial.reset_bill_dispenser()

    def on_bill_detected(self, amount):
        """Handle bill detection and UI flow."""
        self.screensaver.notify_activity()
        self.last_bill_amount = amount
        if amount == 1000:
            self.sound.play_sound("in_1000won")
        elif amount == 5000:
            self.sound.play_sound("in_5000won", wait=False)
        elif amount == 10000:
            self.sound.play_sound("in_10000won", wait=False)

        if amount == 1000:
            self.is_processing = True
            self.show_screen("processing")
            self.start_processing_anim()
            self.root.after(300, lambda: self.payout_coins(2))

            def finish_1000_flow():
                self.stop_processing_anim()
                self.show_thanks()
                self.root.after(3000, self.finish_processing)

            # 소리 종료 감지 없이 고정 시간 후 진행 (라즈비안에서 wait_for_sound_then 미동작 대응)
            self.root.after(2500, finish_1000_flow)
            return

        self.selected_1000 = amount // 1000 - 1 if amount > 1000 else 0
        self.ui_amount.config(text=f"{amount:,}원")
        self.update_change_controls()
        self.show_screen("select")

    # =====================================================
    # 배출 명령
    # =====================================================
    def payout_coins(self, count):
        """Dispense coins by count."""
        self.serial.payout_coins(count)

    def reset_all_devices(self):
        """Reset all payout devices."""
        self.clear_bill_acceptor()
        self.reset_coin_hopper()
        self.reset_bill_dispenser()
        self.root.after(300, self.enable_bill_acceptor)

    def toggle_acceptor(self):
        """Toggle bill acceptor enable/disable."""
        if self.is_acceptor_disabled:
            self.enable_bill_acceptor()
            self.is_acceptor_disabled = False
            self.btn_admin_toggle.config(text="사용중지: OFF", bg="#334155")
        else:
            self.disable_bill_acceptor()
            self.is_acceptor_disabled = True
            self.btn_admin_toggle.config(text="사용중지: ON", bg="#b91c1c")
        if getattr(self, "current_screen", "") == "idle":
            self.update_idle_status()

    def send_combined_payout(self, coin_count, bill_count):
        """Send combined coin/bill payout command."""
        self.serial.send_combined_payout(coin_count, bill_count)

    def reset_totals(self):
        """Reset accumulated totals."""
        self.total_money = 0
        self.total_1000 = 0
        self.total_5000 = 0
        self.total_10000 = 0

    def finish_processing(self):
        """Finalize transaction and return to idle."""
        self.is_processing = False
        self.show_screen("idle", play_hello=False)


if __name__ == "__main__":
    root = tk.Tk()
    app = MoneyExchanger(root)
    # 라즈비안/리눅스: 창이 반드시 앞에 보이도록 강제 (화면 안 나오는 현상 방지)
    if _IS_LINUX:
        root.deiconify()
        root.lift()
        root.update_idletasks()
        root.update()
        if RASPBERRY_PI_KIOSK:
            root.attributes("-fullscreen", True)
            root.config(cursor="none")
    root.mainloop()
