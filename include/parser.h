#ifndef PARSER_H
#define PARSER_H

#include <Arduino.h>
#include "stepper.h"
#include "pen.h"

// #define MAX_FEED_RATE 2000.0f

// parse null terminate line and executes it
void parse_line(char* line);

#endif // PARSER_H