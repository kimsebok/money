import os
import tkinter as tk


class GifPlayer:
    """Lightweight GIF player for Tkinter labels."""

    def __init__(self, root, gif_path, interval_ms=100, bg="black"):
        self.root = root
        self.gif_path = gif_path
        self.interval_ms = interval_ms
        self.bg = bg
        self._frames = self._load_frames()
        self._label = None
        self._index = 0
        self._running = False
        self._after_id = None

    def _load_frames(self):
        frames = []
        if os.path.isfile(self.gif_path):
            try:
                idx = 0
                while True:
                    frame = tk.PhotoImage(
                        file=self.gif_path, format=f"gif -index {idx}"
                    )
                    frames.append(frame)
                    idx += 1
            except Exception:
                pass
            if not frames:
                try:
                    frames.append(tk.PhotoImage(file=self.gif_path))
                except Exception:
                    pass
        return frames

    def create_label(self, parent):
        """Create and return a label bound to this player."""
        label = tk.Label(parent, bg=self.bg)
        if self._frames:
            label.config(image=self._frames[0])
        self._label = label
        return label

    def start(self):
        """Start GIF animation."""
        if not self._frames or not self._label:
            return
        if self._running:
            return
        self._running = True
        self._step()

    def stop(self):
        """Stop GIF animation."""
        self._running = False
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _step(self):
        if not self._running or not self._frames or not self._label:
            return
        frame = self._frames[self._index % len(self._frames)]
        self._label.config(image=frame)
        self._label.image = frame
        self._index += 1
        self._after_id = self.root.after(self.interval_ms, self._step)
