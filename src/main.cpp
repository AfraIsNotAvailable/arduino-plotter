#include <Arduino.h>
#include "config.h"
#include "pen.h"
#include "stepper.h"
#include "parser.h"

char line[LINE_BUFFER_SIZE];
uint8_t char_counter = 0;

void setup()
{
    Serial.begin(BAUD_RATE);

    // init pen
    pen_init();

    // init steppers
    stepper_init();

    Serial.println("\nGrbl-Plotter-Dummy (PIO) v0.3 Ready (Buffered)");
}

void loop()
{
    stepper_run();
    while (Serial.available())
    {
        char c = Serial.read();
        if (c == '?')
        {
            stepper_report_status();
        }
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
        else if (c == '\n' || c == '\r')
        { // end of command line
            if (char_counter > 0)
            {
                line[char_counter] = 0; // null terminated string

                parse_line(line); // parse gcode

                Serial.println("ok");
                char_counter = 0; // reset variables
                line[0] = 0;      // clear buffer
            }
        }
        else
        {
            if (char_counter < LINE_BUFFER_SIZE - 1)
            {
                line[char_counter] = c; // build the line one character at a time
                char_counter++;         // increment counter
            }
        }
        stepper_run();
    }
}