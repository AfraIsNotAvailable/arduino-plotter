import serial
import time
import sys

# --- Configuration ---
PORT = "/dev/ttyUSB0"  # Check your port!
BAUD = 115200

# Helper to read a line but skip empty ones (robust against stray \r\n)
def read_clean_line(s):
    while True:
        line = s.readline().decode('utf-8', errors='ignore').strip()
        if line:  # If not empty, return it
            return line
        # If empty, loop and try again (unless timeout handling is needed)
        # In a test script, blocking slightly is fine.

def run_tests():
    print(f"Connecting to {PORT} at {BAUD}...")
    try:
        s = serial.Serial(PORT, BAUD, timeout=2)
    except serial.SerialException:
        print(f"ERROR: Could not open {PORT}. Is the Arduino plugged in?")
        sys.exit(1)

    print("Waiting for firmware boot...")
    time.sleep(2) 
    s.reset_input_buffer()
    s.write(b"\n")
    s.readline() 

    print("------------------------------------------------")
    print("Starting Automated Tests")
    print("------------------------------------------------")

    # --- TEST 1: Pen Control ---
    print("\n[TEST 1] Pen Control (M3/M5)... ", end="")
    s.write(b"M3\n")
    response = s.read_until(b"ok\r\n").decode('utf-8', errors='ignore')
    
    if "[DEBUG] Pen DOWN" in response or "[DEBUG] PEN DOWN" in response:
        print("PASS")
    else:
        print(f"FAIL\n  Received: {repr(response)}")

    # --- TEST 2: Non-Blocking Queue ---
    print("[TEST 2] Buffer Queueing... ", end="")
    s.write(b"G1 X10 F100\n")
    s.write(b"G1 X0 F500\n")
    
    start_time = time.time()
    r1 = s.readline().decode().strip() 
    r2 = s.readline().decode().strip() 
    duration = time.time() - start_time
    
    if r1 == "ok" and r2 == "ok" and duration < 0.5:
        print(f"PASS (Response time: {duration*1000:.1f}ms)")
    else:
        print(f"FAIL\n  Time: {duration:.2f}s\n  Responses: {r1}, {r2}")

    time.sleep(5) 
    s.reset_input_buffer()

    # --- TEST 3: Real-Time Reporting ---
    print("[TEST 3] Status Reporting (?) ... ", end="")
    s.write(b"G1 X100 F200\n")
    s.readline() # Consume 'ok'
    time.sleep(0.2)
    
    s.write(b"?")
    # Read until '>' then consume the trailing newline to keep buffer clean
    status = s.read_until(b">").decode().strip()
    s.readline() # Consume the \r\n after the >
    
    if "<Run" in status:
        print(f"PASS\n  Got: {status}")
    else:
        print(f"FAIL\n  Received: {status}")

    # --- TEST 4: Pause & Resume ---
    print("\n[TEST 4] Pause (!) and Resume (~)... ", end="")
    
    # Send Pause
    s.write(b"!")
    
    # Use helper to skip any stray newlines and find the message
    pause_msg = read_clean_line(s)
    
    # Check Status (Should be Hold)
    s.write(b"?")
    status_hold = s.read_until(b">").decode().strip()
    s.readline() # Consume trailing newline
    
    if "Paused" in pause_msg and "Hold" in status_hold:
        # Now Resume
        s.write(b"~")
        resume_msg = read_clean_line(s)
        
        if "Resumed" in resume_msg:
            print("PASS")
        else:
            print(f"FAIL (Resume failed)\n  Msg: {resume_msg}")
    else:
        print(f"FAIL (Pause failed)\n  Pause Msg: {repr(pause_msg)}\n  Status: {status_hold}")

    s.close()
    print("\n------------------------------------------------")
    print("Tests Complete.")

if __name__ == "__main__":
    run_tests()