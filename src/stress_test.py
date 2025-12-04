import serial
import time
import sys
import threading
import queue

# --- CONFIGURATION ---
PORT = "/dev/ttyUSB0"
BAUD = 115200
FILENAME = "/home/afra/afra_0001.gcode" # Your large file

# --- STATE ---
lines_to_send = []
lines_processed = 0
start_time = 0
is_finished = False
command_queue = queue.Queue()
response_queue = queue.Queue()

def reader_thread(ser):
    """Reads responses from Arduino ('ok') to track progress."""
    global lines_processed, is_finished
    
    print("   [Reader] Listening for responses...")
    try:
        while not is_finished:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line == "ok":
                    with threading.Lock():
                        lines_processed += 1
                elif "error" in line.lower():
                    print(f"\n[ERROR] Arduino reported: {line}")
            else:
                time.sleep(0.001)
    except Exception as e:
        print(f"\n[Reader Error] {e}")

def sender_thread(ser):
    """Sends commands from the queue to the Arduino."""
    global is_finished
    
    print("   [Sender] Starting command stream...")
    try:
        while not is_finished:
            if not command_queue.empty():
                cmd = command_queue.get()
                ser.write(f"{cmd}\n".encode())
                command_queue.task_done()
            else:
                time.sleep(0.001)
    except Exception as e:
        print(f"\n[Sender Error] {e}")

def run_test():
    global is_finished, start_time, lines_processed
    
    # 1. Load G-code
    try:
        with open(FILENAME, 'r') as f:
            raw_lines = f.readlines()
    except FileNotFoundError:
        print(f"File {FILENAME} not found!")
        return

    # Cleanup G-code (remove comments, empty lines)
    print(f"1. Cleaning {len(raw_lines)} lines...")
    for line in raw_lines:
        l = line.strip()
        if not l: continue
        if l.startswith(";") or l.startswith("(") or l.startswith("%"): continue
        lines_to_send.append(l)
    
    total_lines = len(lines_to_send)
    print(f"   -> Ready to send {total_lines} active commands.")

    # 2. Connect
    try:
        s = serial.Serial(PORT, BAUD, timeout=1)
        print(f"2. Connecting to {PORT}...")
        s.write(b"\r\n\r\n")
        time.sleep(2)
        s.reset_input_buffer()
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    # 3. Start Threads
    reader = threading.Thread(target=reader_thread, args=(s,), daemon=True)
    sender = threading.Thread(target=sender_thread, args=(s,), daemon=True)
    
    reader.start()
    sender.start()

    # 4. Stream!
    print("3. Starting Stream...")
    start_time = time.time()
    
    # Buffer logic: We can dump data into the OS serial buffer, but we shouldn't
    # overflow the Arduino's RX buffer (64 bytes).
    # However, for a stress test, a simple "Wait for space" approach is best.
    # We track `lines_sent - lines_processed`. If difference > 15 (Buffer size), wait.
    
    lines_sent = 0
    
    while lines_sent < total_lines:
        # Flow Control: Don't let the difference exceed Arduino buffer size (16)
        if (lines_sent - lines_processed) < 15:
            cmd = lines_to_send[lines_sent]
            command_queue.put(cmd)
            lines_sent += 1
            
            # Progress Bar
            if lines_sent % 50 == 0:
                sys.stdout.write(f"\r   Sent: {lines_sent}/{total_lines} | Processed: {lines_processed} | {(lines_processed / (time.time()-start_time)):.1f} lines/sec")
                sys.stdout.flush()
        else:
            # Arduino buffer full, wait for it to process a move
            time.sleep(0.001)

    print("\n4. All commands sent! Waiting for completion...")
    
    # Wait for all OKs
    while lines_processed < total_lines:
        time.sleep(0.1)
        sys.stdout.write(f"\r   Waiting... {lines_processed}/{total_lines}")
        sys.stdout.flush()

    duration = time.time() - start_time
    is_finished = True
    
    print(f"\n\n--- TEST COMPLETE ---")
    print(f"Total Time: {duration:.2f} seconds")
    print(f"Average Speed: {total_lines/duration:.1f} lines/sec")
    
    s.close()

if __name__ == "__main__":
    run_test()