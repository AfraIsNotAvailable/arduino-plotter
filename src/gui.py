import pygame
import serial
import time
import threading
import sys
import tkinter as tk
from tkinter import filedialog
import os
from svgpathtools import svg2paths, Line, CubicBezier, QuadraticBezier, Arc, Path
import numpy as np
import math
import re

# --- CONFIGURATION ---
PORT = "/dev/ttyUSB0"
BAUD = 115200
WINDOW_SIZE = (1000, 650)
OFFSET = [250, 550]
FIRMWARE_TIMEOUT = 3600.0
WATCHDOG_THRESHOLD = 1.0  # Check status every 1.0s if idle
ARC_RESOLUTION = 0.5

# --- COLORS ---
COLOR_BG = (20, 20, 30)
COLOR_PANEL = (40, 40, 50)
COLOR_GRID = (50, 50, 60)
COLOR_TEXT = (200, 200, 200)
COLOR_BUTTON = (60, 60, 80)
COLOR_BUTTON_HOVER = (80, 80, 100)
COLOR_PATH = (0, 255, 255)
COLOR_HEAD = (255, 50, 50)
COLOR_INPUT_BG = (30, 30, 40)
COLOR_PEN = (200, 200, 0)

# --- GLOBAL STATE ---
current_x = 0.0
current_y = 0.0
path_points = []
is_connected = False
serial_port = None
console_messages = []
scale = 5.0

upload_queue = []
is_uploading = False
upload_total = 0
upload_current = 0
upload_paused = False
last_cmd_time = 0.0
last_status_time = 0.0  # New tracker


# --- LINEARIZER ---
def parse_coords(line):
    coords = {}
    for char in ["X", "Y", "Z", "I", "J", "F"]:
        match = re.search(rf"{char}([-+]?[\d.]+)", line)
        if match:
            coords[char] = float(match.group(1))
    return coords


def linearize_arc(start_coords, cmd_coords, clockwise):
    segments = []
    x_start, y_start = start_coords.get("X", 0.0), start_coords.get("Y", 0.0)
    i, j = cmd_coords.get("I", 0.0), cmd_coords.get("J", 0.0)
    x_center, y_center = x_start + i, y_start + j
    radius = math.sqrt(i**2 + j**2)

    if radius < 0.001:
        return []

    angle_start = math.atan2(y_start - y_center, x_start - x_center)
    x_end = cmd_coords.get("X", x_start)
    y_end = cmd_coords.get("Y", y_start)
    angle_end = math.atan2(y_end - y_center, x_end - x_center)

    if clockwise:
        if angle_end >= angle_start:
            angle_end -= 2.0 * math.pi
    else:
        if angle_end <= angle_start:
            angle_end += 2.0 * math.pi

    arc_length = abs(angle_end - angle_start) * radius
    num_segments = int(math.ceil(arc_length / ARC_RESOLUTION))
    if num_segments < 1:
        num_segments = 1

    theta_step = (angle_end - angle_start) / num_segments

    for k in range(1, num_segments + 1):
        theta = angle_start + k * theta_step
        nx = x_center + radius * math.cos(theta)
        ny = y_center + radius * math.sin(theta)
        segments.append(f"G1 X{nx:.4f} Y{ny:.4f}")
    return segments


def run_linearization(input_file, output_file):
    log_message(f"Linearizing...")
    try:
        current_pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        with open(input_file, "r") as f_in, open(output_file, "w") as f_out:
            for line in f_in:
                line = line.strip()
                if (
                    not line
                    or line.startswith(";")
                    or line.startswith("(")
                    or line.startswith("%")
                ):
                    f_out.write(line + "\n")
                    continue
                g_match = re.search(r"G(\d+)", line)
                cmd_type = int(g_match.group(1)) if g_match else -1
                coords = parse_coords(line)
                if cmd_type == 2 or cmd_type == 3:
                    new_lines = linearize_arc(
                        current_pos, coords, clockwise=(cmd_type == 2)
                    )
                    for nl in new_lines:
                        f_out.write(nl + "\n")
                        seg_coords = parse_coords(nl)
                        if "X" in seg_coords:
                            current_pos["X"] = seg_coords["X"]
                        if "Y" in seg_coords:
                            current_pos["Y"] = seg_coords["Y"]
                else:
                    f_out.write(line + "\n")
                    if "X" in coords:
                        current_pos["X"] = coords["X"]
                    if "Y" in coords:
                        current_pos["Y"] = coords["Y"]
                    if "Z" in coords:
                        current_pos["Z"] = coords["Z"]
        log_message("Linearization Done.")
        return True
    except Exception as e:
        log_message(f"Linearize Error: {e}")
        return False


# --- SERIAL LOGIC ---
def send_next_command():
    global upload_current, is_uploading, last_cmd_time
    if upload_current < len(upload_queue):
        cmd = upload_queue[upload_current]
        if serial_port and is_connected:
            serial_port.write(f"{cmd}\n".encode())
            last_cmd_time = time.perf_counter()
            if upload_current % 10 == 0 or "G0" in cmd:
                log_message(f"[{upload_current}/{upload_total}] {cmd}")
            upload_current += 1
    else:
        is_uploading = False
        log_message("Upload Complete!")


def serial_worker():
    global current_x, current_y, is_connected, serial_port
    global is_uploading, upload_current, upload_queue, upload_paused
    global last_cmd_time, last_status_time

    try:
        s = serial.Serial(PORT, BAUD, timeout=0.1)
        s.write(b"\r\n\r\n")
        time.sleep(2)
        s.reset_input_buffer()
        is_connected = True
        serial_port = s
        print(f"Connected to {PORT}")

        while True:
            if s.isOpen():
                now = time.perf_counter()

                # --- HEARTBEAT ---
                # Check status periodically or if watchdog triggers
                if (now - last_status_time) > 0.5:
                    s.write(b"?")
                    last_status_time = now

                # --- WATCHDOG RECOVERY ---
                # If uploading but silence for too long, prod it
                if (
                    is_uploading
                    and not upload_paused
                    and (now - last_cmd_time > WATCHDOG_THRESHOLD)
                ):
                    # If we are stuck waiting for 'ok', the '?' above will trigger an 'Idle' or 'Run' response.
                    pass

                while s.in_waiting:
                    try:
                        line = s.readline().decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue

                        if line.startswith("<"):
                            if "MPos:" in line:
                                content = line.strip("<>").split("|")
                                for item in content:
                                    if item.startswith("MPos:"):
                                        coords = item.split(":")[1].split(",")
                                        current_x = float(coords[0])
                                        current_y = float(coords[1])
                                        if not path_points or (
                                            abs(path_points[-1][0] - current_x) > 0.1
                                            or abs(path_points[-1][1] - current_y) > 0.1
                                        ):
                                            path_points.append((current_x, current_y))

                            # RECOVERY: If firmware says "Idle" but we think we are uploading, we lost an 'ok'
                            if "Idle" in line and is_uploading and not upload_paused:
                                log_message("[WARN] Watchdog: Recovering lost 'ok'")
                                send_next_command()

                        elif "ok" in line:
                            if is_uploading and not upload_paused:
                                send_next_command()

                        elif line != "ok":
                            pass

                    except Exception as e:
                        pass

            time.sleep(0.005)

    except Exception as e:
        print(f"Serial Error: {e}")
        is_connected = False


def send_gcode(code):
    global last_cmd_time
    if serial_port and is_connected:
        serial_port.write(f"{code}\n".encode())
        last_cmd_time = time.perf_counter()


def log_message(msg):
    print(msg)
    console_messages.append(msg)
    if len(console_messages) > 28:
        console_messages.pop(0)


# --- BOILERPLATE GUI ---
def open_file_dialog():
    import subprocess

    cmd = [
        "python3",
        "-c",
        "import tkinter as tk; from tkinter import filedialog; root = tk.Tk(); root.withdraw(); print(filedialog.askopenfilename())",
    ]
    try:
        return subprocess.check_output(cmd).decode().strip()
    except:
        return None


def clean_gcode_line(line):
    if ";" in line:
        line = line.split(";")[0]
    if "(" in line:
        line = line.split("(")[0]
    return line.strip()


def load_file_handler():
    global upload_queue, is_uploading, upload_total, upload_current, upload_paused, last_cmd_time
    file_path = open_file_dialog()
    if not file_path:
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "output.gcode")
    log_message(f"Processing: {os.path.basename(file_path)}")

    if not run_linearization(file_path, output_path):
        log_message("Conversion Failed!")
        return

    commands = []
    try:
        with open(output_path, "r") as f:
            for line in f.readlines():
                clean = clean_gcode_line(line)
                if clean:
                    commands.append(clean)
    except Exception as e:
        log_message(f"Load Error: {e}")
        return

    if commands:
        upload_queue = commands
        upload_total = len(commands)
        upload_current = 0
        is_uploading = True
        upload_paused = False
        log_message(f"Ready: {upload_total} lines (Linearized).")
        if serial_port and is_connected:
            send_next_command()
        else:
            log_message("[Error] Not Connected!")
            is_uploading = False
    else:
        log_message("File empty.")


class Button:
    def __init__(self, x, y, w, h, text, callback, transparent=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.hovered = False
        self.transparent = transparent

    def draw(self, screen, font):
        if not self.transparent:
            color = COLOR_BUTTON_HOVER if self.hovered else COLOR_BUTTON
            pygame.draw.rect(screen, color, self.rect)
            pygame.draw.rect(screen, (100, 100, 120), self.rect, 1)
        else:
            if self.hovered:
                s = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
                s.fill((255, 255, 255, 50))
                screen.blit(s, self.rect.topleft)
                pygame.draw.rect(screen, (200, 200, 200), self.rect, 1)
        text_color = COLOR_TEXT
        if self.transparent and self.hovered:
            text_color = (255, 255, 255)
        text_surf = font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.hovered and event.button == 1:
                self.callback()


def btn_load():
    threading.Thread(target=load_file_handler).start()


def btn_home():
    send_gcode("G90")
    send_gcode("G0 X0 Y0")


def btn_clear():
    path_points.clear()
    log_message("Path Cleared")


def btn_zero():
    send_gcode("G92 X0 Y0")
    path_points.clear()
    log_message("Zero Set")


def btn_pause():
    global upload_paused
    if is_uploading:
        upload_paused = not upload_paused
        send_gcode("!" if upload_paused else "~")
        log_message("Paused" if upload_paused else "Resumed")
    else:
        send_gcode("!")


def btn_resume():
    send_gcode("~")


def btn_pen_up():
    send_gcode("M5")


def btn_pen_down():
    send_gcode("M3")


def btn_zoom_in():
    global scale
    scale = min(20.0, scale + 1.0)


def btn_zoom_out():
    global scale
    scale = max(1.0, scale - 1.0)


def draw_pen(screen, x, y):
    pygame.draw.polygon(screen, COLOR_HEAD, [(x, y), (x - 5, y - 10), (x + 5, y - 10)])
    pygame.draw.rect(screen, COLOR_PEN, (x - 5, y - 35, 10, 25))
    pygame.draw.line(screen, (0, 0, 0), (x, y), (x - 5, y - 10), 1)
    pygame.draw.line(screen, (0, 0, 0), (x, y), (x + 5, y - 10), 1)
    pygame.draw.rect(screen, (0, 0, 0), (x - 5, y - 35, 10, 25), 1)


def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Grbl Plotter Viz")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 14)
    btn_font = pygame.font.SysFont("sans-serif", 16)
    zoom_font = pygame.font.SysFont("sans-serif", 24, bold=True)
    input_font = pygame.font.SysFont("monospace", 16)

    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()

    buttons = [
        Button(820, 50, 160, 40, "LOAD FILE", btn_load),
        Button(820, 110, 160, 40, "HOME (0,0)", btn_home),
        Button(820, 160, 160, 40, "SET ZERO", btn_zero),
        Button(820, 220, 160, 40, "CLEAR VIEW", btn_clear),
        Button(820, 280, 75, 40, "PAUSE", btn_pause),
        Button(905, 280, 75, 40, "RESUME", btn_resume),
        Button(820, 340, 75, 40, "PEN UP", btn_pen_up),
        Button(905, 340, 75, 40, "PEN DN", btn_pen_down),
    ]
    zoom_buttons = [
        Button(740, 20, 40, 40, "+", btn_zoom_in, True),
        Button(740, 70, 40, 40, "-", btn_zoom_out, True),
    ]

    user_text = ""
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            for btn in buttons:
                btn.handle_event(event)
            for btn in zoom_buttons:
                btn.handle_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if user_text:
                        if user_text.upper() == "LOAD":
                            threading.Thread(target=load_file_handler).start()
                        else:
                            send_gcode(user_text)
                            log_message(f"$ {user_text}")
                        user_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    user_text = user_text[:-1]
                else:
                    user_text += event.unicode

        screen.fill(COLOR_BG)
        pygame.draw.rect(screen, COLOR_PANEL, (10, 10, 220, 580))
        pygame.draw.rect(screen, (60, 60, 70), (10, 10, 220, 580), 1)
        for i, msg in enumerate(console_messages):
            text_surf = font.render(msg, True, COLOR_TEXT)
            screen.blit(text_surf, (15, 15 + i * 20))

        pygame.draw.rect(screen, COLOR_PANEL, (800, 10, 190, 580))
        pygame.draw.rect(screen, (60, 60, 70), (800, 10, 190, 580), 1)
        for btn in buttons:
            btn.draw(screen, btn_font)

        status = (0, 255, 0) if is_connected else (255, 0, 0)
        screen.blit(
            font.render(f"CONN: {'OK' if is_connected else 'NO'}", True, status),
            (820, 500),
        )
        screen.blit(font.render(f"X: {current_x:.2f}", True, COLOR_TEXT), (820, 530))
        screen.blit(font.render(f"Y: {current_y:.2f}", True, COLOR_TEXT), (820, 550))
        screen.blit(font.render(f"Zoom: {scale:.1f}x", True, COLOR_TEXT), (820, 570))

        viz_rect = pygame.Rect(240, 10, 550, 580)
        pygame.draw.rect(screen, (15, 15, 20), viz_rect)
        old_clip = screen.get_clip()
        screen.set_clip(viz_rect)

        for i in range(0, 200, 10):
            pygame.draw.line(
                screen,
                COLOR_GRID,
                (OFFSET[0] + i * scale, 0),
                (OFFSET[0] + i * scale, 600),
                1,
            )
            pygame.draw.line(
                screen,
                COLOR_GRID,
                (0, OFFSET[1] - i * scale),
                (1000, OFFSET[1] - i * scale),
                1,
            )

        if len(path_points) > 1:
            pp = [
                (OFFSET[0] + p[0] * scale, OFFSET[1] - p[1] * scale)
                for p in path_points
            ]
            pygame.draw.lines(screen, COLOR_PATH, False, pp, 2)
        draw_pen(
            screen,
            int(OFFSET[0] + current_x * scale),
            int(OFFSET[1] - current_y * scale),
        )
        for btn in zoom_buttons:
            btn.draw(screen, zoom_font)

        if is_uploading:
            p = upload_current / max(1, upload_total)
            pygame.draw.rect(screen, (0, 200, 0), (250, 20, 530 * p, 10))

        screen.set_clip(old_clip)
        pygame.draw.rect(screen, (60, 60, 70), viz_rect, 1)

        in_rect = pygame.Rect(10, 600, 980, 40)
        pygame.draw.rect(screen, COLOR_INPUT_BG, in_rect)
        screen.blit(
            input_font.render("> " + user_text, True, (255, 255, 255)), (20, 610)
        )

        pygame.display.flip()
        clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    main()
