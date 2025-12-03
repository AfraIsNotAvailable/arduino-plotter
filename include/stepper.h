#ifndef STEPPER_H
#define STEPPER_H

#include <Arduino.h>
#include "config.h"

void stepper_init();

// Blocking move function
void stepper_move_to(float x_mm, float y_mm, float feed_rate);

// Non-blocking move function
bool stepper_plan_move(float x, float y, float feed_rate);

// musct be called as soo as possible
void stepper_run();

// rt commands
void stepper_report_status();
void stepper_hold();
void stepper_resume();
bool stepper_is_moving();
void stepper_get_position(float* x, float* y);

#endif // STEPPER_H