G90
M5
G0 X50 Y50   ; Move to the middle of the bed
G92 X0 Y0    ; Tell Arduino: "This physical spot is now Logical (0,0)"

; Now draw a small square relative to this new center
M3
G1 X10 F500
G1 Y10
G1 X0
G1 Y0
M5