#include "pen.h"

Servo penServo;

void pen_init() {
    penServo.attach(PEN_SERVO_PIN);
    pen_up();
}

void pen_up() {
    penServo.write(PEN_UP_ANGLE);
    Serial.println("[DEBUG] PEN UP");
}

void pen_down() {
    penServo.write(PEN_DOWN_ANGLE);
    Serial.println("[DEBUG] PEN DOWN");
}