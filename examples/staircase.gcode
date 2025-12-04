G90          ; Start in Absolute
G0 X0 Y0     ; Go Home
M3           ; Pen Down
G91          ; Switch to Relative (all moves are "add this much")
G1 X10 F500  ; Right 10mm
G1 Y10       ; Up 10mm
G1 X10       ; Right 10mm
G1 Y10       ; Up 10mm
G1 X10       ; Right 10mm
G1 Y10       ; Up 10mm
M5           ; Pen Up
G90          ; Back to Absolute
G0 X0 Y0     ; Go all the way back home (should hit 0,0 exactly)