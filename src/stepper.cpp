#include "stepper.h"
#include <math.h>
#include <Arduino.h>

typedef struct
{
    long total_steps;
    long dx;
    long dy;
    bool dir_x;
    bool dir_y;
    unsigned long step_delay;
} segment_t;

// Increase buffer if memory allows (Atmega328p has 2KB RAM)
// 16 is standard, 32 gives smoother arcs but uses more RAM.
segment_t buffer[PLANNER_BUFFER_SIZE];

volatile uint8_t head = 0;
volatile uint8_t tail = 0;
volatile bool is_running = false;
volatile bool is_paused = false;

long planner_pos_x = 0;
long planner_pos_y = 0;

volatile long live_steps_x = 0;
volatile long live_steps_y = 0;

long current_step_index = 0;
long acc_x = 0;
long acc_y = 0;
unsigned long last_step_time = 0;

void stepper_init()
{
    pinMode(X_STEP_PIN, OUTPUT);
    pinMode(X_DIR_PIN, OUTPUT);
    pinMode(Y_STEP_PIN, OUTPUT);
    pinMode(Y_DIR_PIN, OUTPUT);
    digitalWrite(X_STEP_PIN, LOW);
    digitalWrite(Y_STEP_PIN, LOW);
}

void set_direction(uint8_t dir_pin, bool positive, bool invert)
{
    digitalWrite(dir_pin, (positive ^ invert) ? HIGH : LOW);
}

bool stepper_plan_move(float x_mm, float y_mm, float feed_rate)
{
    uint8_t next_head = (head + 1) % PLANNER_BUFFER_SIZE;

    // Buffer Full?
    if (next_head == tail)
        return false;

    long target_steps_x = lround(x_mm * STEPS_PER_MM_X);
    long target_steps_y = lround(y_mm * STEPS_PER_MM_Y);
    long dx = target_steps_x - planner_pos_x;
    long dy = target_steps_y - planner_pos_y;

    // Ignore Zero moves
    if (dx == 0 && dy == 0)
        return true;

    segment_t *segment = &buffer[head];
    segment->dx = abs(dx);
    segment->dy = abs(dy);
    segment->dir_x = (dx > 0);
    segment->dir_y = (dy > 0);
    segment->total_steps = (segment->dx > segment->dy) ? segment->dx : segment->dy;

    if (feed_rate < 1.0)
        feed_rate = 100.0;

    // Calculate Speed
    float distance_mm = sqrt(pow(dx / STEPS_PER_MM_X, 2) + pow(dy / STEPS_PER_MM_Y, 2));
    if (distance_mm < 0.001)
        distance_mm = 0.001; // Avoid div/0

    segment->step_delay = (unsigned long)((distance_mm / feed_rate) * 60000000.0 / segment->total_steps);
    if (segment->step_delay < 50)
        segment->step_delay = 50; // Cap max speed (min delay)

    planner_pos_x = target_steps_x;
    planner_pos_y = target_steps_y;

    head = next_head;

    // Auto-start if not running
    if (!is_running)
        stepper_run();

    return true;
}

void stepper_run()
{
    if (is_paused)
        return;

    if (!is_running)
    {
        if (head == tail)
            return; // Buffer Empty

        current_step_index = 0;
        acc_x = 0;
        acc_y = 0;

        // Setup Direction
        set_direction(X_DIR_PIN, buffer[tail].dir_x, INVERT_X_DIR);
        set_direction(Y_DIR_PIN, buffer[tail].dir_y, INVERT_Y_DIR);

        is_running = true;
        last_step_time = micros();
    }

    // Check if it's time to step
    unsigned long now = micros();
    if ((now - last_step_time) >= buffer[tail].step_delay)
    {
        last_step_time = now;

        segment_t *seg = &buffer[tail];

        // Bresenham Algorithm
        acc_x += seg->dx;
        acc_y += seg->dy;

        if (acc_x >= seg->total_steps)
        {
            digitalWrite(X_STEP_PIN, HIGH);
            acc_x -= seg->total_steps;
            live_steps_x += (seg->dir_x ? 1 : -1);
        }
        if (acc_y >= seg->total_steps)
        {
            digitalWrite(Y_STEP_PIN, HIGH);
            acc_y -= seg->total_steps;
            live_steps_y += (seg->dir_y ? 1 : -1);
        }

        delayMicroseconds(STEP_PULSE_DELAY);
        digitalWrite(X_STEP_PIN, LOW);
        digitalWrite(Y_STEP_PIN, LOW);

        current_step_index++;

        // Segment Complete?
        if (current_step_index >= seg->total_steps)
        {
            is_running = false;
            tail = (tail + 1) % PLANNER_BUFFER_SIZE;

            // Optimization: Immediately check next segment to avoid delays
            if (head != tail)
                stepper_run();
        }
    }
}

void stepper_report_status()
{
    Serial.print("<");
    if (is_paused)
        Serial.print("Hold");
    else if (is_running)
        Serial.print("Run");
    else
        Serial.print("Idle");

    Serial.print("|MPos:");
    Serial.print((float)live_steps_x / STEPS_PER_MM_X);
    Serial.print(",");
    Serial.print((float)live_steps_y / STEPS_PER_MM_Y);
    Serial.println(">");
}

void stepper_hold() { is_paused = true; }
void stepper_resume() { is_paused = false; }
bool stepper_is_moving() { return is_running; }

void stepper_get_position(float *x, float *y)
{
    *x = (float)planner_pos_x / STEPS_PER_MM_X;
    *y = (float)planner_pos_y / STEPS_PER_MM_Y;
}