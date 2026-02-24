import os
import sys
import threading

import pygame

# 라즈비안/리눅스: ALSA 사용, 버퍼 크기로 지연/깨짐 완화
_IS_LINUX = sys.platform.startswith("linux")


class SoundManager:
    """Centralized sound loading and playback."""

    def __init__(self, root, volume_var):
        self.root = root
        self.volume_var = volume_var
        self.sound_files = {}
        self.sound_objs = {}
        self.sound_channels = {}

    def load_sounds(self):
        """Load all sound assets and initialize mixer."""
        sound_dir = os.path.join(os.path.dirname(__file__), "resource", "raw")
        self.sound_files = {
            "in_1000won": os.path.join(sound_dir, "in_1000won.mp3"),
            "in_5000won": os.path.join(sound_dir, "in_5000won.mp3"),
            "in_10000won": os.path.join(sound_dir, "in_10000won.mp3"),
            "out_money": os.path.join(sound_dir, "out_money.mp3"),
            "thanks": os.path.join(sound_dir, "thanks.mp3"),
            "hello": os.path.join(sound_dir, "hello.mp3"),
            "volume_test": os.path.join(sound_dir, "volume_test.mp3"),
            "button": os.path.join(sound_dir, "button.mp3"),
            "confirm": os.path.join(sound_dir, "confirm.mp3"),
        }
        try:
            if _IS_LINUX:
                # 라즈비안: 버퍼 크게 해서 찢어짐/찌그러짐 방지 (2048~4096), 22kHz로 CPU 부담 완화
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=2048)
            else:
                pygame.mixer.init()
        except Exception:
            return

        self.sound_objs = {}
        for key, path in self.sound_files.items():
            if os.path.isfile(path):
                try:
                    self.sound_objs[key] = pygame.mixer.Sound(path)
                except Exception:
                    pass
        self.apply_volume()

    def apply_volume(self):
        """Apply the current volume to all sounds."""
        volume = max(0.0, min(float(self.volume_var.get()) / 100.0, 1.0))
        for sound in self.sound_objs.values():
            try:
                sound.set_volume(volume)
            except Exception:
                pass

    def play_sound(self, key, wait=True):
        """Play a sound by key, optionally tracking completion."""
        sound = self.sound_objs.get(key)
        if not sound:
            return
        channel = None
        try:
            channel = pygame.mixer.find_channel(True)
            if channel:
                channel.play(sound)
        except Exception:
            channel = None

        if channel:
            self.sound_channels[key] = channel
            if wait:
                threading.Thread(
                    target=self._wait_channel, args=(channel,), daemon=True
                ).start()

    def stop_sound(self, key):
        """Stop a currently playing sound channel by key."""
        channel = self.sound_channels.pop(key, None)
        if channel:
            channel.stop()

    def stop_input_sounds(self):
        """Stop bill input guidance sounds."""
        self.stop_sound("in_5000won")
        self.stop_sound("in_10000won")

    def stop_all_sounds(self):
        """Stop all currently playing sounds."""
        for key in list(self.sound_channels.keys()):
            self.stop_sound(key)
        try:
            pygame.mixer.stop()
        except Exception:
            pass

    def get_sound_duration_ms(self, key, fallback_ms=0):
        """Return sound duration in ms with fallback."""
        sound = self.sound_objs.get(key)
        if not sound:
            return fallback_ms
        try:
            length_sec = sound.get_length()
        except Exception:
            return fallback_ms
        if not length_sec or length_sec <= 0:
            return fallback_ms
        return int(length_sec * 1000)

    def wait_for_sound_then(self, key, callback, fallback_ms=1800):
        """소리 끝나면 callback 호출. fallback_ms 지나면 무조건 호출(라즈비안 등 get_busy 꼬임 방지)."""
        channel = self.sound_channels.get(key)
        done = [False]

        def once():
            if done[0]:
                return
            done[0] = True
            callback()

        if not channel:
            self.root.after(fallback_ms, once)
            return

        # 안전 타임아웃: 소리 끝 감지 실패 시에도 fallback_ms 후 진행
        self.root.after(fallback_ms, once)

        def _check():
            if done[0]:
                return
            try:
                if channel.get_busy():
                    self.root.after(100, _check)
                    return
            except Exception:
                pass
            once()

        self.root.after(100, _check)

    def _wait_channel(self, channel):
        try:
            while channel.get_busy():
                pygame.time.wait(50)
        except Exception:
            pass
