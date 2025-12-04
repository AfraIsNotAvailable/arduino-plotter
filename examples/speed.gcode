G90
G0 X0 Y0
M5           ; Pen Up (Safety)

; Slow Move (Draw)
G1 X50 F300  ; Move to X50 slowly (takes ~10 seconds)

; Fast Return (Rapid)
G0 X0        ; Zip back to X0 at MAX_FEED_RATE (2000 mm/min)