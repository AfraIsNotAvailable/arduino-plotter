#ifndef STEPPER_H
#define STEPPER_H

#include <Arduino.h>
#include "config.h"

void stepper_init();

void stepper_move_to(float x, float y, float feed_rate);

#endif // STEPPER_H