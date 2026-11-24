import sys
import os
import random
import threading
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageSequence, ImageTk

# ===== Настройки (можно менять) =====
GIF_NAME = "bimbus-pig.gif"    # Имя GIF-файла рядом со скриптом
SOUND_NAME = "bimbus-pig.mp3"  # Имя звукового файла рядом со скриптом (.mp3 / .wav)
WINDOW_COUNT = 10              # Сколько окон открыть
WINDOW_OFFSET_X = 100          # Начальная позиция X первого окна
WINDOW_OFFSET_Y = 100          # Начальная позиция Y первого окна
WINDOW_STEP = 40               # Смещение каждого следующего окна
WANDER_SPEED_MIN = -3.0        # Минимальная скорость блуждания (px/кадр)
WANDER_SPEED_MAX = 3.0         # Максимальная скорость блуждания (px/кадр)
WANDER_FPS_DELAY = 16          # Задержка между шагами блуждания, мс (~60 FPS)
# ===================================


def resource_path(name: str) -> Path:
    """Путь к ресурсу: работает и в .py, и в собранном PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().with_name(name)


def load_frames(path: Path, master: tk.Misc):
    image = Image.open(path)
    frames = []
    durations = []
    for frame in ImageSequence.Iterator(image):
        frames.append(ImageTk.PhotoImage(frame.convert("RGBA"), master=master))
        durations.append(max(20, int(frame.info.get("duration", 100))))
    return frames, durations


def play_sound_once(sound_path: Path) -> None:
    """Однократно воспроизводит звук в фоне, кроссплатформенно (по возможности)."""
    if not sound_path.exists():
        print(f"Звук не найден: {sound_path}")
        return

    def _play() -> None:
        try:
            if sys.platform.startswith("win"):
                import ctypes
                mci = ctypes.windll.winmm.mciSendStringW
                alias = "bimbus_sound"
                mci(f'open "{sound_path}" type mpegvideo alias {alias}', None, 0, None)
                mci(f'play {alias} wait', None, 0, None)
                mci(f'close {alias}', None, 0, None)
            elif sys.platform == "darwin":
                os.system(f'afplay "{sound_path}" >/dev/null 2>&1')
            else:
                for player in ("ffplay -nodisp -autoexit -loglevel quiet",
                               "mpg123 -q", "aplay -q", "paplay"):
                    if os.system(f"{player} \"{sound_path}\" >/dev/null 2>&1") == 0:
                        break
        except Exception as e:
            print(f"Не удалось воспроизвести звук: {e}")

    threading.Thread(target=_play, daemon=True).start()


def random_speed() -> float:
    """Случайная скорость, гарантированно не близкая к нулю."""
    v = random.uniform(WANDER_SPEED_MIN, WANDER_SPEED_MAX)
    if abs(v) < 0.5:
        v = 0.5 if v >= 0 else -0.5
    return v


def create_window(index: int, frames, durations, master: tk.Tk, on_close) -> None:
    win = tk.Toplevel(master)
    win.title(f"Bimbus Pig #{index}")
    win.resizable(False, False)
    win.configure(bg="black")

    offset = WINDOW_STEP * (index - 1)
    start_x = WINDOW_OFFSET_X + offset
    start_y = WINDOW_OFFSET_Y + offset
    win.geometry(f"+{start_x}+{start_y}")

    label = tk.Label(win, bd=0, bg="black", cursor="fleur")
    label.pack()

    # --- Анимация GIF ---
    state = {"index": 0}
    alive = {"value": True}

    # --- Блуждание ---
    pos = {
        "x": float(start_x),
        "y": float(start_y),
        "dx": random_speed(),
        "dy": random_speed(),
    }
    dragging = {"active": False, "x": 0, "y": 0}

    def wander() -> None:
        if not alive["value"] or not win.winfo_exists():
            return
        if dragging["active"]:
            win.after(WANDER_FPS_DELAY, wander)
            return

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        win_w = win.winfo_width() or 100
        win_h = win.winfo_height() or 100

        pos["x"] += pos["dx"]
        pos["y"] += pos["dy"]

        # Отталкиваемся от краёв экрана
        if pos["x"] <= 0 or pos["x"] + win_w >= screen_w:
            pos["dx"] = -pos["dx"]
            pos["x"] = max(0, min(pos["x"], screen_w - win_w))
        if pos["y"] <= 0 or pos["y"] + win_h >= screen_h:
            pos["dy"] = -pos["dy"]
            pos["y"] = max(0, min(pos["y"], screen_h - win_h))

        win.geometry(f"+{int(pos['x'])}+{int(pos['y'])}")
        win.after(WANDER_FPS_DELAY, wander)

    # --- Перетаскивание ---
    def start_drag(event):
        dragging["active"] = True
        dragging["x"] = event.x_root - win.winfo_x()
        dragging["y"] = event.y_root - win.winfo_y()

    def do_drag(event):
        x = event.x_root - dragging["x"]
        y = event.y_root - dragging["y"]
        pos["x"] = float(x)
        pos["y"] = float(y)
        win.geometry(f"+{x}+{y}")

    def stop_drag(event):
        dragging["active"] = False
        # При отпускании — случайный новый толчок, чтобы окно «ожило»
        pos["dx"] = random_speed()
        pos["dy"] = random_speed()

    label.bind("<ButtonPress-1>", start_drag)
    label.bind("<B1-Motion>", do_drag)
    label.bind("<ButtonRelease-1>", stop_drag)

    # --- Анимация ---
    def animate() -> None:
        if not alive["value"] or not win.winfo_exists():
            return
        i = state["index"]
        label.configure(image=frames[i])
        state["index"] = (i + 1) % len(frames)
        win.after(durations[i], animate)

    def close_window() -> None:
        if not alive["value"]:
            return
        alive["value"] = False
        win.destroy()
        on_close()

    # Перехватываем закрытие крестиком, Esc и Ctrl+C — все ведут к close_window
    win.protocol("WM_DELETE_WINDOW", close_window)
    win.bind("<Escape>", lambda e: close_window())
    win.bind("<Control-c>", lambda e: close_window())
    win.bind("<Control-Cyrillic_es>", lambda e: close_window())  # Ctrl+С (рус.)

    win.focus_force()
    animate()
    win.after(100, wander)  # старт блуждания после первого отображения окна


def main() -> None:
    gif_path = resource_path(GIF_NAME)
    if not gif_path.exists():
        raise FileNotFoundError(f"GIF не найден: {gif_path}")

    root = tk.Tk()
    root.withdraw()

    frames, durations = load_frames(gif_path, root)

    # Однократное воспроизведение звука при запуске
    sound_path = resource_path(SOUND_NAME)
    play_sound_once(sound_path)

    state = {"alive": WINDOW_COUNT}

    def on_window_closed() -> None:
        state["alive"] -= 1
        if state["alive"] <= 0:
            # Последнее окно закрыто → выходим из mainloop и завершаем программу
            root.destroy()

    for i in range(1, WINDOW_COUNT + 1):
        create_window(i, frames, durations, root, on_window_closed)

    # Ctrl+C глобально тоже закрывает всё приложение
    root.bind_all("<Control-c>", lambda e: root.destroy())
    root.bind_all("<Control-Cyrillic_es>", lambda e: root.destroy())

    root.mainloop()


if __name__ == "__main__":
    main()