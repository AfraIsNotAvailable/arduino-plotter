#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// Monitor rate
#define BAUD_RATE 115200

// Pen servo
#define PEN_SERVO_PIN 11
#define PEN_UP_ANGLE 90
#define PEN_DOWN_ANGLE 10

// Stepper motors (CNC Sield mappings)
// X Axis
#define X_STEP_PIN 2
#define X_DIR_PIN 5

// Y Axis
#define Y_STEP_PIN 3
#define Y_DIR_PIN 6

// Limit switches
#define LIMIT_X_PIN 9
#define LIMIT_Y_PIN 10

// Buffer sizes
#define LINE_BUFFER_SIZE 128

#endif // CONFIG_H