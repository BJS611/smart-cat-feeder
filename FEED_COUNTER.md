# TM1637 completed-feed counter

Seven-segment TM1637 CLK D10 / DIO D11 now displays the cumulative number of completed servo feeding cycles instead of the remaining cooldown.

- Startup: read the counter from Arduino Uno EEPROM and display it (0 if no valid stored value is present).
- Automatic FEED and D2 manual feed use the same completion path. Increment the counter **once** after the OPENING and CLOSING stages finish, not when the FEED command is merely acknowledged.
- Emergency or reset while the servo is running aborts the cycle, so it is not counted.
- Cooldown remains enforced (60 seconds normal firmware, 5 seconds bench firmware), and `COOLDOWN_STATUS` remains available on USB serial.
- New command `FEED_COUNT` returns `FEED_COUNT <number>`. Every completed cycle also emits this status.
- TM1637 has four digits, so it shows the last four digits after 9999; serial returns the full stored count.
- EEPROM is updated only when a feeding cycle finishes, reducing unnecessary writes compared with periodic updates.

The counter tracks **completed servo cycles**, not independently verified food discharge, weight, volume or the number of individual food pellets. This distinction is important if the hopper is empty or the auger jams.

## Upload normal firmware

Stop `live_cam.py` before uploading, so the USB serial port is available.

```bash
git fetch origin
git switch --track origin/feature/tm1637-feed-cycle-counter
arduino-cli compile --fqbn arduino:avr:uno arduino/smart_cat_feeder_servo
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:uno arduino/smart_cat_feeder_servo
```

To upload bench firmware instead, substitute `arduino/smart_cat_feeder_servo_bench_5s` in the compile and upload commands. Physical tests and compiler verification are required on the Raspberry Pi/Uno hardware.
