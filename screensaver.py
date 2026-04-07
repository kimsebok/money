import random
import sys
import time
from dataclasses import dataclass

import tkinter as tk

from display_config import DISPLAY_HEIGHT, DISPLAY_WIDTH, fs

_IS_LINUX = sys.platform.startswith("linux")


@dataclass
class ScreenSaverConfig:
    """스크린세이버 트리거·동작 설정."""

    saver_idle_ms: int = 5* 60 * 1000
    move_interval_ms: int = 3000
    move_padding_px: int = 20
    wake_on_motion: bool = False


class ScreenSaverController:
    def __init__(
        self,
        root,
        config: ScreenSaverConfig,
        show_screen,
        get_current_screen,
        label_text: str,
        font_family: str,
    ):
        self.root = root
        self.config = config
        self.show_screen = show_screen
        self.get_current_screen = get_current_screen
        self.label_text = label_text
        self.font_family = font_family
        self.last_activity_ts = time.time()
        self.stage = "active"
        self._frame = None
        self._label = None
        self._move_running = False
        self._enabled = True

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if not self._enabled and self.stage == "saver":
            self._wake()

    def get_enabled(self):
        return self._enabled

    def build_screen(self):
        frame = tk.Frame(self.root, bg="black")
        label = tk.Label(
            frame,
            text=self.label_text,
            font=(self.font_family, fs(32), "bold"),
            fg="#e5e7eb",
            bg="black",
        )
        label.place(x=40, y=40)
        self._frame = frame
        self._label = label
        return frame

    def start(self):
        self._bind_activity()
        self._tick()

    def on_show_screen(self, name):
        if name in ("idle", "screensaver"):
            return
        self._set_stage("active")

    def notify_activity(self):
        """외부에서 호출 (예: 지폐 투입 시). 시간 리셋 + 스크린세이버면 깨움."""
        self.last_activity_ts = time.time()
        if self.stage == "saver":
            self._wake()
        else:
            self._set_stage("active")

    def _bind_activity(self):
        def on_activity(_event=None):
            self.last_activity_ts = time.time()
            if self.stage == "saver":
                self._wake()
            else:
                self._set_stage("active")

        self.root.bind_all("<ButtonPress>", on_activity)
        self.root.bind_all("<ButtonRelease>", on_activity)
        self.root.bind_all("<Button-1>", on_activity)
        self.root.bind_all("<KeyPress>", on_activity)
        if self.config.wake_on_motion:
            self.root.bind_all("<Motion>", on_activity)

    def _tick(self):
        current = self.get_current_screen() or ""
        if current == "idle":
            if not self._enabled:
                self._set_stage("active")
            else:
                idle_ms = (time.time() - self.last_activity_ts) * 1000
                if idle_ms >= self.config.saver_idle_ms:
                    self._set_stage("saver")
                else:
                    self._set_stage("active")
        elif current == "screensaver":
            if self.stage != "saver":
                self._set_stage("saver")
        else:
            self._set_stage("active")
        self.root.after(300, self._tick)

    def _set_stage(self, stage):
        if stage == self.stage:
            return
        self.stage = stage
        if stage == "active":
            self._stop_move()
            self._set_label_visible(True)
        elif stage == "saver":
            self._set_label_visible(True)
            self.show_screen("screensaver")
            self._start_move()

    def _wake(self):
        self._stop_move()
        self._set_label_visible(True)
        self.show_screen("idle")
        self.stage = "active"

    def _start_move(self):
        if self._move_running:
            return
        self._move_running = True
        self._move_label()

    def _stop_move(self):
        self._move_running = False

    def _move_label(self):
        if not self._move_running or not self._label:
            return
        width = self.root.winfo_width() or DISPLAY_WIDTH
        height = self.root.winfo_height() or DISPLAY_HEIGHT
        label_w = self._label.winfo_reqwidth()
        label_h = self._label.winfo_reqheight()
        max_x = max(self.config.move_padding_px, width - label_w - self.config.move_padding_px)
        max_y = max(self.config.move_padding_px, height - label_h - self.config.move_padding_px)
        x = random.randint(self.config.move_padding_px, max_x)
        y = random.randint(self.config.move_padding_px, max_y)
        self._label.place(x=x, y=y)
        self.root.after(self.config.move_interval_ms, self._move_label)

    def _set_label_visible(self, visible):
        if not self._label:
            return
        self._label.config(text=self.label_text if visible else "")
