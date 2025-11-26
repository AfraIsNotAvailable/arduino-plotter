#include "stepper.h"

// current position
float current_x = 0.0;
float current_y = 0.0;

void stepper_init() {
    pinMode(X_STEP_PIN, OUTPUT);
    pinMode(X_DIR_PIN, OUTPUT);
    pinMode(Y_STEP_PIN, OUTPUT);
    pinMode(Y_DIR_PIN, OUTPUT);

    // disabled initially
}

void stepper_move_to(float x, float y, float feed_rate) {
    // for now just a simulation
    Serial.print("[MOTION] Moving to X: ");
    Serial.print(x);
    Serial.print(" Y: ");
    Serial.print(y);
    Serial.print(" at F: ");
    Serial.println(feed_rate);

    //update internal pos
    current_x = x;
    current_y = y;

}