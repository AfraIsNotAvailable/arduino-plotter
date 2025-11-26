#include "parser.h"
#include <stdlib.h>

// modal state
float target_x = 0.0;
float target_y = 0.0;
float feed_rate = 1000.0; // mm/min
float motion_mode = -1;

void parse_line(char *line)
{
    char *ptr = line;
    bool motion_changed = false;

    while (*ptr)
    {
        char c = *ptr;

        // skip spaces
        if (c == ' ')
        {
            ptr++;
            continue;
        }

        // upppercase
        if (c >= 'a' && c <= 'z')
        {
            c -= 32;
        }

        // parsing command
        if (c == 'G')
        {                                        // MOVEMENT
            int cmd = strtol(ptr + 1, &ptr, 10); // read int
            switch (cmd)
            {
            case 0:
                motion_mode = 0; // rapid
                break;

            case 1:
                motion_mode = 1; // linear
                break;
                // TODO: add G28 and G90/G91 (absolute/relative) here later
            }
        }
        else if (c == 'M')
        {
            int cmd = strtol(ptr + 1, &ptr, 10); // read int
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
        {                                     // POSITION X
            target_x = strtod(ptr + 1, &ptr); // read float
            motion_changed = true;
        }
        else if (c == 'Y')
        {                                     // POSITION Y
            target_y = strtod(ptr + 1, &ptr); // read float
            motion_changed = true;
        }
        else if (c == 'F')
        { // FEED RATE
            feed_rate = strtod(ptr + 1, &ptr);
        }
        else
        { // SKIP
            ptr++;
        }
    }

    if (motion_changed && motion_mode != -1) {
        stepper_move_to(target_x, target_y, feed_rate);
    }
}