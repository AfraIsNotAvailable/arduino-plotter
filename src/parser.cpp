#include "parser.h"
#include "stepper.h"
#include <stdlib.h>
#include <math.h>
#include <Arduino.h>

#define ARC_TOLERANCE 0.05
#define MIN_ARC_SEGMENTS 8
#define MAX_ARC_SEGMENTS 16

// --- SMOOTHING FIX ---
// If angle change > 30 degrees, force stop.
#define CORNER_ANGLE_THRESHOLD 30.0

float feed_rate = 1000.0;
int motion_mode = -1;
bool absolute_mode = true;
float offset_x = 0.0;
float offset_y = 0.0;

// Track previous move to calculate angle
float last_move_dx = 0.0;
float last_move_dy = 0.0;

#ifndef PI
#define PI 3.1415926535897932384626433832795
#endif

void parser_reset_offsets()
{
    offset_x = 0.0;
    offset_y = 0.0;
}

void check_realtime_commands()
{
    if (Serial.available())
    {
        char c = Serial.peek();
        if (c == '?' || c == '!' || c == '~')
        {
            c = Serial.read();
            if (c == '?')
                stepper_report_status();
            else if (c == '!')
            {
                stepper_hold();
                Serial.println("[MSG] Paused");
            }
            else if (c == '~')
            {
                stepper_resume();
                Serial.println("[MSG] Resumed");
            }
        }
    }
}

// Check for sharp corner and pause if needed
void check_corner(float new_dx, float new_dy)
{
    // Calculate angle between vectors
    // Dot Product: A . B = |A||B|cos(theta)
    float mag_last = sqrt(last_move_dx * last_move_dx + last_move_dy * last_move_dy);
    float mag_new = sqrt(new_dx * new_dx + new_dy * new_dy);

    if (mag_last > 0.1 && mag_new > 0.1)
    {
        float dot = last_move_dx * new_dx + last_move_dy * new_dy;
        float cos_theta = dot / (mag_last * mag_new);

        // Clamp for floating point errors
        if (cos_theta > 1.0)
            cos_theta = 1.0;
        if (cos_theta < -1.0)
            cos_theta = -1.0;

        float angle_rad = acos(cos_theta);
        float angle_deg = angle_rad * 180.0 / PI;

        if (angle_deg > CORNER_ANGLE_THRESHOLD)
        {
            // SHARP CORNER DETECTED!
            // Wait for buffer to empty (effectively stops motors)
            while (stepper_is_moving())
            {
                stepper_run();
                check_realtime_commands();
            }
        }
    }
    last_move_dx = new_dx;
    last_move_dy = new_dy;
}

void handle_arc(float target_x, float target_y, float offset_i, float offset_j, bool clockwise)
{
    float current_x, current_y;
    stepper_get_position(&current_x, &current_y);

    float radius = sqrt(offset_i * offset_i + offset_j * offset_j);
    float center_x = current_x + offset_i;
    float center_y = current_y + offset_j;

    if (radius < 0.1)
    {
        while (!stepper_plan_move(target_x, target_y, feed_rate))
        {
            stepper_run();
            check_realtime_commands();
        }
        return;
    }

    float angle_start = atan2(current_y - center_y, current_x - center_x);
    float angle_end = atan2(target_y - center_y, target_x - center_x);

    float angular_travel = angle_end - angle_start;
    if (clockwise)
    {
        if (angular_travel >= 0)
            angular_travel -= 2.0 * PI;
    }
    else
    {
        if (angular_travel <= 0)
            angular_travel += 2.0 * PI;
    }

    float mm_per_segment = 2.0 * sqrt(2.0 * radius * ARC_TOLERANCE);
    float arc_mm = abs(angular_travel * radius);
    int segments = floor(arc_mm / mm_per_segment);

    if (segments < MIN_ARC_SEGMENTS)
        segments = MIN_ARC_SEGMENTS;
    if (segments > 32)
        segments = 32;

    float theta_per_segment = angular_travel / segments;
    float cos_T = cos(theta_per_segment);
    float sin_T = sin(theta_per_segment);

    float r_ax = -offset_i;
    float r_ay = -offset_j;

    for (int i = 1; i < segments; i++)
    {
        float r_nx = r_ax * cos_T - r_ay * sin_T;
        float r_ny = r_ax * sin_T + r_ay * cos_T;
        r_ax = r_nx;
        r_ay = r_ny;
        float next_x = center_x + r_ax;
        float next_y = center_y + r_ay;

        // Note: Arcs are naturally smooth, no need to stop inside them.
        while (!stepper_plan_move(next_x, next_y, feed_rate))
        {
            stepper_run();
            check_realtime_commands();
        }
        // Update vector for corner check
        last_move_dx = next_x - current_x;
        last_move_dy = next_y - current_y;
    }

    while (!stepper_plan_move(target_x, target_y, feed_rate))
    {
        stepper_run();
        check_realtime_commands();
    }
}

void parse_line(char *line)
{
    char *ptr = line;
    bool has_x = false, has_y = false;
    float val_x = 0.0, val_y = 0.0;
    float val_i = 0.0, val_j = 0.0;

    while (*ptr)
    {
        char c = *ptr++;
        if (c <= ' ')
            continue;
        if (c == ';' || c == '(')
            break;
        if (c >= 'a' && c <= 'z')
            c -= 32;

        if (c == 'G')
        {
            int cmd = strtol(ptr, &ptr, 10);
            if (cmd == 0)
                motion_mode = 0;
            else if (cmd == 1)
                motion_mode = 1;
            else if (cmd == 2)
                motion_mode = 2;
            else if (cmd == 3)
                motion_mode = 3;
            else if (cmd == 90)
                absolute_mode = true;
            else if (cmd == 91)
                absolute_mode = false;
            else if (cmd == 92)
                motion_mode = 92;
        }
        else if (c == 'M')
        {
            int cmd = strtol(ptr, &ptr, 10);
            if (cmd == 3)
                pen_down();
            else if (cmd == 5)
                pen_up();
        }
        else if (c == 'X')
        {
            val_x = strtod(ptr, &ptr);
            has_x = true;
        }
        else if (c == 'Y')
        {
            val_y = strtod(ptr, &ptr);
            has_y = true;
        }
        else if (c == 'I')
        {
            val_i = strtod(ptr, &ptr);
        }
        else if (c == 'J')
        {
            val_j = strtod(ptr, &ptr);
        }
        else if (c == 'F')
        {
            feed_rate = strtod(ptr, &ptr);
        }
    }

    if (motion_mode == 92)
    {
        float cx, cy;
        stepper_get_position(&cx, &cy);
        if (has_x)
            offset_x = cx - val_x;
        if (has_y)
            offset_y = cy - val_y;
        motion_mode = -1;
        return;
    }

    float cx, cy;
    stepper_get_position(&cx, &cy);
    float tx = has_x ? (absolute_mode ? val_x + offset_x : cx + val_x) : cx;
    float ty = has_y ? (absolute_mode ? val_y + offset_y : cy + val_y) : cy;

    if (motion_mode == 0 || motion_mode == 1)
    {
        float speed = (motion_mode == 0) ? MAX_FEED_RATE : feed_rate;
        if (has_x || has_y)
        {

            // --- CORNER CHECK ---
            check_corner(tx - cx, ty - cy);
            // --------------------

            while (!stepper_plan_move(tx, ty, speed))
            {
                stepper_run();
                check_realtime_commands();
            }
        }
    }
    else if (motion_mode == 2 || motion_mode == 3)
    {
        handle_arc(tx, ty, val_i, val_j, (motion_mode == 2));
    }
}