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

# --- CONFIGURATION ---
PORT = "/dev/ttyUSB0"  # Check your port!
BAUD = 115200
WINDOW_SIZE = (1000, 650) # Increased height for input bar
OFFSET = [250, 550]    # Origin (0,0) location on screen (pixels) - Now a list to be mutable

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
COLOR_PEN = (200, 200, 0) # Gold color for the pen body

# --- GLOBAL STATE ---
current_x = 0.0
current_y = 0.0
path_points = []       
is_connected = False
serial_port = None
console_messages = [] 
scale = 5.0 # Pixels per Millimeter (Zoom) - Now global to change it

# Streaming State
upload_queue = []      
is_uploading = False
upload_total = 0
upload_current = 0
upload_paused = False

# --- SERIAL THREAD ---
def serial_worker():
    global current_x, current_y, is_connected, serial_port
    global is_uploading, upload_current, upload_queue, upload_paused
    
    try:
        s = serial.Serial(PORT, BAUD, timeout=1)
        s.write(b"\r\n\r\n")
        time.sleep(2)
        s.reset_input_buffer()
        is_connected = True
        serial_port = s
        print(f"Connected to {PORT}")

        while True:
            if s.isOpen():
                # Status Request
                s.write(b"?")
                
                while s.in_waiting:
                    try:
                        line = s.readline().decode('utf-8', errors='ignore').strip()
                        if not line: continue

                        if line.startswith("<") and "MPos:" in line:
                            content = line.strip("<>").split("|")
                            for item in content:
                                if item.startswith("MPos:"):
                                    coords = item.split(":")[1].split(",")
                                    current_x = float(coords[0])
                                    current_y = float(coords[1])
                                    
                                    if not path_points or (abs(path_points[-1][0] - current_x) > 0.1 or abs(path_points[-1][1] - current_y) > 0.1):
                                        path_points.append((current_x, current_y))
                        
                        elif line == "ok":
                            if is_uploading and not upload_paused:
                                if upload_current < len(upload_queue):
                                    cmd = upload_queue[upload_current]
                                    s.write(f"{cmd}\n".encode())
                                    
                                    if upload_current % 5 == 0:
                                        log_message(f"[{upload_current}/{upload_total}] {cmd}")
                                    
                                    upload_current += 1
                                else:
                                    is_uploading = False
                                    log_message("Upload Complete!")
                                    
                        elif line != "ok": 
                            log_message(f"> {line}")
                            
                    except Exception:
                        pass
            
            time.sleep(0.02)
            
    except Exception as e:
        print(f"Serial Error: {e}")
        is_connected = False

def send_gcode(code):
    if serial_port and is_connected:
        serial_port.write(f"{code}\n".encode())

def log_message(msg):
    console_messages.append(msg)
    if len(console_messages) > 28: # Keep only last N messages
        console_messages.pop(0)

# Run file dialog in a separate process to avoid Pygame/Tkinter conflicts on Linux
def open_file_dialog():
    import subprocess
    cmd = ['python3', '-c', 'import tkinter as tk; from tkinter import filedialog; root = tk.Tk(); root.withdraw(); print(filedialog.askopenfilename())']
    try:
        result = subprocess.check_output(cmd).decode().strip()
        return result
    except:
        return None

def convert_svg_to_gcode(svg_path):
    gcode = ["G90", "G21", "M5", "G0 Z5"] # Header: Absolute, MM, Pen Up
    try:
        paths, attributes = svg2paths(svg_path)
        
        # Determine SVG scaling (SVG units are often px, need conversion to mm)
        # Default: 1 px = 1 unit. You might need scaling based on DPI.
        # Assuming 96 DPI: 1 px = 0.264 mm
        px_to_mm = 0.264583 
        
        for path in paths:
            # Move to start of path
            start = path.start
            gcode.append(f"G0 X{start.real * px_to_mm:.3f} Y{start.imag * px_to_mm:.3f}")
            gcode.append("M3") # Pen Down
            
            # Linearize path segments
            num_segments = int(path.length() / 2) # Sample every ~2 units? Adjust resolution.
            if num_segments < 5: num_segments = 5
            
            for i in range(1, num_segments + 1):
                pt = path.point(i / num_segments)
                gcode.append(f"G1 X{pt.real * px_to_mm:.3f} Y{pt.imag * px_to_mm:.3f} F1000")
            
            gcode.append("M5") # Pen Up
            
        gcode.append("G0 X0 Y0")
        return gcode
    except Exception as e:
        log_message(f"SVG Error: {e}")
        return []

def load_file_handler():
    global upload_queue, is_uploading, upload_total, upload_current, upload_paused
    
    file_path = open_file_dialog()
    
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        commands = []
        
        if ext == '.svg':
            log_message("Converting SVG...")
            commands = convert_svg_to_gcode(file_path)
        else:
            try:
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                for line in lines:
                    l = line.strip()
                    if not l: continue
                    if l.startswith(';') or l.startswith('('): continue 
                    commands.append(l)
            except Exception as e:
                log_message(f"Load Error: {e}")
                return

        if commands:
            upload_queue = commands
            upload_total = len(commands)
            upload_current = 0
            is_uploading = True
            upload_paused = False
            log_message(f"Loaded {upload_total} lines.")
            
            if upload_queue:
                cmd = upload_queue[0]
                serial_port.write(f"{cmd}\n".encode())
                log_message(f"[Start] {cmd}")
                upload_current += 1
        else:
            log_message("File empty or conversion failed.")

# --- UI CLASS ---
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
            # Transparent button style (just outline on hover or nothing)
            if self.hovered:
                s = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
                s.fill((255, 255, 255, 50)) # Semi-transparent white
                screen.blit(s, self.rect.topleft)
                pygame.draw.rect(screen, (200, 200, 200), self.rect, 1)
        
        text_color = COLOR_TEXT
        if self.transparent and self.hovered: text_color = (255, 255, 255)
        
        text_surf = font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.hovered and event.button == 1:
                self.callback()

# --- BUTTON CALLBACKS ---
def btn_load(): threading.Thread(target=load_file_handler).start()
def btn_home(): send_gcode("G90"); send_gcode("G0 X0 Y0")
def btn_clear(): path_points.clear(); log_message("Path Cleared")
def btn_zero(): send_gcode("G92 X0 Y0"); path_points.clear(); log_message("Zero Set")
def btn_pause(): 
    global upload_paused
    if is_uploading:
        upload_paused = not upload_paused
        send_gcode("!" if upload_paused else "~")
        log_message("Paused" if upload_paused else "Resumed")
    else:
        send_gcode("!")
def btn_resume(): send_gcode("~")
def btn_pen_up(): send_gcode("M5")
def btn_pen_down(): send_gcode("M3")
def btn_zoom_in(): 
    global scale
    scale = min(20.0, scale + 1.0)
def btn_zoom_out(): 
    global scale
    scale = max(1.0, scale - 1.0)

# --- DRAW PEN HELPER ---
def draw_pen(screen, x, y):
    # Tip of the pen is at (x, y)
    # Body is a triangle/rect pointing down
    # Coordinates relative to tip
    color = COLOR_HEAD
    body_color = COLOR_PEN
    
    # Pen Tip (Triangle)
    pygame.draw.polygon(screen, color, [(x, y), (x-5, y-10), (x+5, y-10)])
    
    # Pen Body (Rectangle)
    pygame.draw.rect(screen, body_color, (x-5, y-35, 10, 25))
    
    # Shadow/Outline
    pygame.draw.line(screen, (0,0,0), (x,y), (x-5,y-10), 1)
    pygame.draw.line(screen, (0,0,0), (x,y), (x+5,y-10), 1)
    pygame.draw.rect(screen, (0,0,0), (x-5, y-35, 10, 25), 1)

# --- MAIN UI ---
def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Grbl Plotter Viz")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 14)
    btn_font = pygame.font.SysFont("sans-serif", 16)
    zoom_font = pygame.font.SysFont("sans-serif", 24, bold=True)
    input_font = pygame.font.SysFont("monospace", 16)

    # Start Serial Thread
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()

    # Define Buttons (Right Panel)
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
    
    # Floating Zoom Buttons (Top Right of Viz Area)
    zoom_buttons = [
        Button(740, 20, 40, 40, "+", btn_zoom_in, transparent=True),
        Button(740, 70, 40, 40, "-", btn_zoom_out, transparent=True)
    ]

    user_text = ''
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            # Button Events
            for btn in buttons:
                btn.handle_event(event)
            for btn in zoom_buttons:
                btn.handle_event(event)
            
            # Keyboard Input for Command Bar
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if user_text:
                        if user_text.upper() == "LOAD":
                            threading.Thread(target=load_file_handler).start()
                        else:
                            send_gcode(user_text)
                            log_message(f"$ {user_text}")
                        user_text = ''
                elif event.key == pygame.K_BACKSPACE:
                    user_text = user_text[:-1]
                else:
                    user_text += event.unicode

        # --- DRAWING ---
        screen.fill(COLOR_BG)

        # 1. Left Panel (Console)
        pygame.draw.rect(screen, COLOR_PANEL, (10, 10, 220, 580))
        pygame.draw.rect(screen, (60, 60, 70), (10, 10, 220, 580), 1)
        
        for i, msg in enumerate(console_messages):
            text_surf = font.render(msg, True, COLOR_TEXT)
            if text_surf.get_width() > 210:
                msg = msg[:25] + "..."
                text_surf = font.render(msg, True, COLOR_TEXT)
            screen.blit(text_surf, (15, 15 + i * 20))

        # 2. Right Panel (Controls)
        pygame.draw.rect(screen, COLOR_PANEL, (800, 10, 190, 580))
        pygame.draw.rect(screen, (60, 60, 70), (800, 10, 190, 580), 1)
        
        for btn in buttons:
            btn.draw(screen, btn_font)
            
        status_color = (0, 255, 0) if is_connected else (255, 0, 0)
        conn_text = font.render(f"CONN: {'OK' if is_connected else 'NO'}", True, status_color)
        pos_text = font.render(f"X: {current_x:.2f}", True, COLOR_TEXT)
        pos_text2 = font.render(f"Y: {current_y:.2f}", True, COLOR_TEXT)
        zoom_text = font.render(f"Zoom: {scale:.1f}x", True, COLOR_TEXT)
        
        screen.blit(conn_text, (820, 500))
        screen.blit(pos_text, (820, 530))
        screen.blit(pos_text2, (820, 550))
        screen.blit(zoom_text, (820, 570))

        # 3. Center Panel (Visualizer)
        viz_rect = pygame.Rect(240, 10, 550, 580)
        pygame.draw.rect(screen, (15, 15, 20), viz_rect)
        old_clip = screen.get_clip()
        screen.set_clip(viz_rect)

        # Grid Lines
        for i in range(0, 200, 10): 
            start = (OFFSET[0] + i*scale, 0)
            end   = (OFFSET[0] + i*scale, 600)
            pygame.draw.line(screen, COLOR_GRID, start, end, 1)
            
            start = (0, OFFSET[1] - i*scale)
            end   = (1000, OFFSET[1] - i*scale)
            pygame.draw.line(screen, COLOR_GRID, start, end, 1)

        # Path
        if len(path_points) > 1:
            pixel_points = []
            for pt in path_points:
                px = OFFSET[0] + (pt[0] * scale)
                py = OFFSET[1] - (pt[1] * scale)
                pixel_points.append((px, py))
            pygame.draw.lines(screen, COLOR_PATH, False, pixel_points, 2)

        # Draw Actual Pen Graphic
        head_x = int(OFFSET[0] + (current_x * scale))
        head_y = int(OFFSET[1] - (current_y * scale))
        draw_pen(screen, head_x, head_y)

        # Floating Zoom Buttons
        for btn in zoom_buttons:
            btn.draw(screen, zoom_font)

        # Upload Progress Bar
        if is_uploading:
            bar_width = 530
            progress = upload_current / max(1, upload_total)
            pygame.draw.rect(screen, (50, 50, 50), (250, 20, bar_width, 10))
            pygame.draw.rect(screen, (0, 200, 0), (250, 20, bar_width * progress, 10))

        screen.set_clip(old_clip)
        pygame.draw.rect(screen, (60, 60, 70), viz_rect, 1)

        # 4. Bottom Input Bar
        input_rect = pygame.Rect(10, 600, 980, 40)
        pygame.draw.rect(screen, COLOR_INPUT_BG, input_rect)
        pygame.draw.rect(screen, (60, 60, 70), input_rect, 1)
        
        input_surface = input_font.render("> " + user_text, True, (255, 255, 255))
        screen.blit(input_surface, (input_rect.x + 10, input_rect.y + 10))

        if time.time() % 1 > 0.5:
            cursor_x = input_rect.x + 10 + input_surface.get_width()
            pygame.draw.line(screen, (255, 255, 255), (cursor_x, input_rect.y + 5), (cursor_x, input_rect.y + 35), 2)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()