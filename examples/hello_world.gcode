G90          ; Set Absolute Positioning
G0 X0 Y0     ; Rapid move to home
M3           ; Pen Down (Start drawing)
G1 X20 F500  ; Draw bottom line
G1 Y20       ; Draw right line
G1 X0        ; Draw top line
G1 Y0        ; Draw left line (close the square)
M5           ; Pen Up (Stop drawing)