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
    pen_init();
    stepper_init();
    Serial.println("\nGrbl-Plotter-Echo v0.6 Ready");
}

void loop()
{
    stepper_run();
    while (Serial.available())
    {
        char c = Serial.read();

        // --- DEBUG ECHO ---
        // Uncomment the next line if you need to verify every byte
        // Serial.print("[RX]"); Serial.print(c); Serial.print(" ");
        // ------------------

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
        {
            // End of line
            if (char_counter > 0)
            {
                line[char_counter] = 0;

                // Execute
                unsigned long t_start = millis();
                parse_line(line);
                unsigned long t_end = millis();

                Serial.print("ok T:");
                Serial.println(t_end - t_start);

                char_counter = 0;
                line[0] = 0;
            }
        }
        else
        {
            // Normal character
            if (char_counter < LINE_BUFFER_SIZE - 1)
            {
                line[char_counter] = c;
                char_counter++;
            }
            else
            {
                // Buffer Overflow Protection
                Serial.println("[ERR] Line Buffer Full!");
                char_counter = 0; // Reset to avoid deadlock
            }
        }
        stepper_run();
    }
}