import math
import re
import sys

# --- CONFIGURATION ---
INPUT_FILE = "/home/afra/utcn/anul3/ssc/dummy-plotter/dummy-plotter/examples/afra_0001.gcode"
OUTPUT_FILE = "/home/afra/utcn/anul3/ssc/dummy-plotter/dummy-plotter/src/output.gcode"
ARC_RESOLUTION = 0.5  # mm per segment (Lower = Smoother, Higher = Smaller file)


def parse_coords(line):
    """Extracts X, Y, Z, I, J, F from a G-code line."""
    coords = {}
    for char in ["X", "Y", "Z", "I", "J", "F"]:
        match = re.search(f"{char}([-+]?[\d.]+)", line)
        if match:
            coords[char] = float(match.group(1))
    return coords


def linearize_arc(start_coords, cmd_coords, clockwise):
    """Generates a list of G1 commands to approximate an arc."""
    segments = []

    # Current Position
    x_start, y_start = start_coords["X"], start_coords["Y"]

    # Target Position (default to start if not present)
    x_end = cmd_coords.get("X", x_start)
    y_end = cmd_coords.get("Y", y_start)

    # Offsets
    i = cmd_coords.get("I", 0.0)
    j = cmd_coords.get("J", 0.0)

    # Center
    x_center = x_start + i
    y_center = y_start + j

    # Radius
    radius = math.sqrt(i**2 + j**2)
    if radius < 0.001:
        return []  # Safety skip

    # Angles
    angle_start = math.atan2(y_start - y_center, x_start - x_center)
    angle_end = math.atan2(y_end - y_center, x_end - x_center)

    # Normalize Angles
    if clockwise:  # G2
        if angle_end >= angle_start:
            angle_end -= 2.0 * math.pi
    else:  # G3
        if angle_end <= angle_start:
            angle_end += 2.0 * math.pi

    # Calculate Segments
    arc_length = abs(angle_end - angle_start) * radius
    num_segments = int(math.ceil(arc_length / ARC_RESOLUTION))
    if num_segments < 1:
        num_segments = 1

    theta_step = (angle_end - angle_start) / num_segments

    # Generate Points
    for k in range(1, num_segments + 1):
        theta = angle_start + k * theta_step
        nx = x_center + radius * math.cos(theta)
        ny = y_center + radius * math.sin(theta)
        segments.append(f"G1 X{nx:.4f} Y{ny:.4f}")

    return segments


def process_file():
    print(f"Converting {INPUT_FILE} -> {OUTPUT_FILE}...")

    with open(INPUT_FILE, "r") as f_in, open(OUTPUT_FILE, "w") as f_out:
        # State tracking
        current_pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}

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

            # Parse command
            g_match = re.search(r"G(\d+)", line)
            cmd_type = int(g_match.group(1)) if g_match else -1
            coords = parse_coords(line)

            # Handle Arcs
            if cmd_type == 2 or cmd_type == 3:
                new_lines = linearize_arc(
                    current_pos, coords, clockwise=(cmd_type == 2)
                )
                for nl in new_lines:
                    f_out.write(nl + "\n")
                    # Update X/Y for the next segment
                    seg_coords = parse_coords(nl)
                    if "X" in seg_coords:
                        current_pos["X"] = seg_coords["X"]
                    if "Y" in seg_coords:
                        current_pos["Y"] = seg_coords["Y"]

            # Handle Linear Moves (Pass through but track position)
            else:
                f_out.write(line + "\n")
                if "X" in coords:
                    current_pos["X"] = coords["X"]
                if "Y" in coords:
                    current_pos["Y"] = coords["Y"]
                if "Z" in coords:
                    current_pos["Z"] = coords["Z"]

    print("Done! Load the new file in the GUI.")


if __name__ == "__main__":
    process_file()
