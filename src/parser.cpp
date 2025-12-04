#include "parser.h"
#include <stdlib.h>
#include <math.h>

float feed_rate = 1000.0;
int motion_mode = -1; // 0=G0, 1=G1, 2=G2, 3=G3
bool absolute_mode = true;

float offset_x = 0.0;
float offset_y = 0.0;

// REMOVED: #define PI ... (Already defined in Arduino.h)

void parser_reset_offsets()
{
    offset_x = 0.0;
    offset_y = 0.0;
}

// Helper to handle Arc Interpolation
void handle_arc(float target_x, float target_y, float offset_i, float offset_j, bool clockwise)
{
    float current_x, current_y;
    stepper_get_position(&current_x, &current_y);

    // 1. Calculate Center
    float center_x = current_x + offset_i;
    float center_y = current_y + offset_j;

    // 2. Calculate Radius
    float radius = sqrt(offset_i * offset_i + offset_j * offset_j);

    // 3. Calculate Angles (in radians)
    float angle_start = atan2(current_y - center_y, current_x - center_x);
    float angle_end = atan2(target_y - center_y, target_x - center_x);

    // 4. Normalize Angles
    if (clockwise)
    {
        if (angle_end >= angle_start)
            angle_end -= 2.0 * PI;
    }
    else
    {
        if (angle_end <= angle_start)
            angle_end += 2.0 * PI;
    }

    // 5. Determine Segment Count (Resolution)
    float arc_length = abs(angle_end - angle_start) * radius;
    int segments = ceil(arc_length * 2.0); // ~0.5mm resolution

    // Safety Clamps
    if (segments < 1)
        segments = 1;
    if (segments > 100)
        segments = 100; // PREVENT FREEZE: Cap segments per arc

    // 6. Interpolate
    float angle_step = (angle_end - angle_start) / segments;

    for (int i = 1; i <= segments; i++)
    {
        float angle = angle_start + i * angle_step;
        float next_x = center_x + cos(angle) * radius;
        float next_y = center_y + sin(angle) * radius;

        // Send linear move for this segment
        while (!stepper_plan_move(next_x, next_y, feed_rate))
        {
            stepper_run();
        }
    }
}

void parse_line(char *line)
{
    char *ptr = line;

    bool has_x = false;
    bool has_y = false;
    // REMOVED: has_i / has_j variables (unused)

    float val_x = 0.0;
    float val_y = 0.0;
    float val_i = 0.0;
    float val_j = 0.0;

    while (*ptr)
    {
        char c = *ptr;

        // 1. ROBUSTNESS: Skip Whitespace
        if (c == ' ' || c == '\t' || c == '\r')
        {
            ptr++;
            continue;
        }

        // 2. OPTIMIZATION: Handle Comments Immediately
        if (c == ';' || c == '(')
        {
            break;
        }

        // 3. Normalize Case
        if (c >= 'a' && c <= 'z')
            c -= 32;

        // 4. Parse Commands
        if (c == 'G')
        {
            int cmd = strtol(ptr + 1, &ptr, 10);
            switch (cmd)
            {
            case 0:
                motion_mode = 0;
                break;
            case 1:
                motion_mode = 1;
                break;
            case 2:
                motion_mode = 2;
                break; // CW Arc
            case 3:
                motion_mode = 3;
                break; // CCW Arc
            case 90:
                absolute_mode = true;
                break;
            case 91:
                absolute_mode = false;
                break;
            case 92:
                motion_mode = 92;
                break; // Set Position
            case 21:
                break; // Units=mm (Default)
            default:
                break;
            }
        }
        else if (c == 'M')
        {
            int cmd = strtol(ptr + 1, &ptr, 10);
            switch (cmd)
            {
            case 3:
                pen_down();
                break;
            case 5:
                pen_up();
                break;
            }
        }
        else if (c == 'X')
        {
            val_x = strtod(ptr + 1, &ptr);
            has_x = true;
        }
        else if (c == 'Y')
        {
            val_y = strtod(ptr + 1, &ptr);
            has_y = true;
        }
        else if (c == 'I')
        {
            val_i = strtod(ptr + 1, &ptr);
        } // Removed has_i assignment
        else if (c == 'J')
        {
            val_j = strtod(ptr + 1, &ptr);
        } // Removed has_j assignment
        else if (c == 'F')
        {
            feed_rate = strtod(ptr + 1, &ptr);
        }
        else
        {
            ptr++;
        }
    }

    // --- Execution ---

    // G92: Set Coordinate System Offset
    if (motion_mode == 92)
    {
        float current_x, current_y;
        stepper_get_position(&current_x, &current_y);

        if (has_x)
            offset_x = current_x - val_x;
        if (has_y)
            offset_y = current_y - val_y;

        motion_mode = -1;
        return;
    }

    // Move Execution
    float current_x, current_y;
    stepper_get_position(&current_x, &current_y);
    float target_x = current_x;
    float target_y = current_y;

    if (has_x)
        target_x = absolute_mode ? val_x + offset_x : current_x + val_x;
    if (has_y)
        target_y = absolute_mode ? val_y + offset_y : current_y + val_y;

    if (motion_mode == 0 || motion_mode == 1)
    {
        // Linear Move
        float move_speed = (motion_mode == 0) ? MAX_FEED_RATE : feed_rate;

        if (has_x || has_y)
        {
            while (!stepper_plan_move(target_x, target_y, move_speed))
            {
                stepper_run();
            }
        }
    }
    else if (motion_mode == 2 || motion_mode == 3)
    {
        // Arc Move (G2 / G3)
        handle_arc(target_x, target_y, val_i, val_j, (motion_mode == 2));
    }
}