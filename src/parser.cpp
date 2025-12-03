#include "parser.h"
#include <stdlib.h>

float feed_rate = 1000.0;
int motion_mode = -1;
bool absolute_mode = true;

float offset_x = 0.0;
float offset_y = 0.0;

void parser_reset_offsets()
{
    offset_x = 0.0;
    offset_y = 0.0;
}

void parse_line(char *line)
{
    char *ptr = line;

    bool has_x = false;
    bool has_y = false;
    float val_x = 0.0;
    float val_y = 0.0;

    while (*ptr)
    {
        char c = *ptr;

        if (c == ' ')
        {
            ptr++;
            continue;
        }

        if (c >= 'a' && c <= 'z')
            c -= 32;

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
            case 90:
                absolute_mode = true;
                break;
            case 91:
                absolute_mode = false;
                break;
            case 92:
                motion_mode = 92;
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
        else if (c == 'F')
        {
            feed_rate = strtod(ptr + 1, &ptr);
        }
        else
        {
            ptr++;
        }
    }

    float current_machine_x, current_machine_y;
    stepper_get_position(&current_machine_x, &current_machine_y);

    if (motion_mode == 92)
    {
        if (has_x)
            offset_x = current_machine_x - val_x;
        if (has_y)
            offset_y = current_machine_y - val_y;

        motion_mode = -1;
        return;
    }

    if (motion_mode == 0 || motion_mode == 1)
    {
        float target_machine_x = current_machine_x;
        float target_machine_y = current_machine_y;

        if (has_x)
        {
            if (absolute_mode)
            {
                target_machine_x = val_x + offset_x;
            }
            else
            {
                target_machine_x = current_machine_x + val_x;
            }
        }
        if (has_y)
        {
            if (absolute_mode)
            {
                target_machine_y = val_y + offset_y;
            }
            else
            {
                target_machine_y = current_machine_y + val_y;
            }
        }

        float move_speed = (motion_mode == 0) ? MAX_FEED_RATE : feed_rate;

        if (has_x || has_y)
        {
            while (!stepper_plan_move(target_machine_x, target_machine_y, move_speed))
            {
                stepper_run();
            }
        }
    }
}