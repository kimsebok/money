import time
import board
import busio
import adafruit_vl6180x

i2c = board.I2C()
sensor = adafruit_vl6180x.VL6180X(i2c)

while True:
    d = sensor.range
    print(f"Distance: {d} mm")

    time.sleep(0.2)