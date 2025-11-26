#ifndef PEN_H
#define PEN_H

#include <Arduino.h>
#include <Servo.h>
#include "config.h"

void pen_init();
void pen_down();
void pen_up();

#endif // PEN_H