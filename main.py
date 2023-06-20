"""Application to monitor environmental sensors and publish to an MQTT Broker"""
import json
import io
import network
import os
import time
import uasyncio

from machine import Pin, I2C, PWM
from umqtt.simple import MQTTClient
from ht16k33segment import HT16K33Segment
import sht31
 
class log_to_file(io.IOBase):
    def __init__(self):
        pass
 
    def write(self, data):
        with open("logfile.txt", mode="a") as f:
            f.write(data)
        return len(data)
 

def connect_to_wifi():
    """Connect to the available Wifi"""
    while True:
        wait = 2
        wlan.connect(config["WIFI_SSID"], config["WIFI_PASSWORD"])
        while wait < 12:
            status = wlan.status()
            if status >= 3:
                break
            wait += 1
            time.sleep(1)
        if wlan.status() != 3:
            print(f'network connection failed, retrying {wlan.status()}')
        else:
            print('WiFi connected')
            status = wlan.ifconfig()
            print('ip = ' + status[0] )
            break


def mqtt_connect():
    """Connect to the MQTT broker service"""
    print(f"Connecting to MQTT Broker {config['MQTT_SERVER']}...")
    client = MQTTClient(client_id="repeater_pico",
                        server=config["MQTT_SERVER"],
                        port=8883,
                        user=config["MQTT_CLIENT_ID"],
                        password=config["MQTT_PASSWORD"],
                        keepalive=7200,
                        ssl=True,
                        ssl_params={'server_hostname':config["MQTT_SERVER"]}
                        )
    client.connect()
    print(f"Connected to MQTT Broker {config['MQTT_SERVER']}")
    return client


def reboot():
    """Reset the machine""" 
    time.sleep(20)
    machine.reset()
   
   
def display_value(index, value):
    """Display a current value"""
    try:
        display.set_number(int(index), 0)
        display.set_character("-", 1)
        
        bcd = int(str(int(value)), 16)

        display.set_number((bcd & 0xF0) >> 4, 2)
        display.set_number((bcd & 0x0F), 3)
        display.draw()
    except:
        pass


def report_sensor(last, sensor, name):
    """Retrieve and publish sensor value"""
    reading = sensor.get_temp_humi()
    temperature = float(reading[0]) * 9.0 / 5.0 + 32.0
    humidity = reading[1]
    if abs(last[0] -  temperature) >= 1.0:
        last[0] = temperature
        client.publish(f"TEMPERATURE_{name}", str(int(temperature)))
    if abs(last[1] - humidity) >= 1.0:
        last[1] = humidity
        client.publish(f"HUMIDITY_{name}", str(int(humidity)))


def check_fan():
    """Check to see if we need the fan"""
    if int(data["REPEATER"][0]) > int(data["OUTSIDE"][0]):
        if not data["FAN"]:
            pwm.duty_u16(65535) # 100% duty
            data["FAN"] = True
            client.publish("FAN_STATE", "1")
    elif data["FAN"]:        
        pwm.duty_u16(0)
        data["FAN"] = False
        client.publish("FAN_STATE", "0")


try:
    #os.dupterm(log_to_file())

    with open("config.json") as f:
        config = json.load(f)
        
    data = {
        "INSIDE": [0.0, 0.0],
        "REPEATER": [0.0, 0.0],
        "OUTSIDE": [0.0, 0.0],
        "FAN": False
    }
    led = machine.Pin("LED", machine.Pin.OUT)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    display_value(0, 0)
    connect_to_wifi()
    client = mqtt_connect()
    client.publish("FAN_STATE", "0")
except Exception as e:
    print(f"Exception during initializeion: {e}")
    reboot()


try:
    pwm = PWM(Pin(22))
    pwm.freq(25000)
    pwm.duty_u16(0)

    i2c0 = I2C(0, scl=Pin(17), sda=Pin(16))
    print("0 17, 16")
    devices = i2c0.scan()
    if devices:
        for d in devices:
            print(hex(d))
    i2c1 = I2C(1, scl=Pin(19), sda=Pin(18))
    print("1 19, 18")
    devices = i2c1.scan()
    if devices:
        for d in devices:
            print(hex(d))
            
    sensor_inside = sht31.SHT31(i2c0, addr=0x45)
    sensor_outside = sht31.SHT31(i2c0, addr=0x44)
    sensor_repeater = sht31.SHT31(i2c1, addr=0x44)
    print("sensors found")

    display = HT16K33Segment(i2c1)
    display.set_brightness(10)
    print("display found")    
except:
    pass
    

async def loop():
    try:
        check_fan()
    except Exception as e:
        print(f"Exception during fan check: {e}")
        reboot()
    try:
        report_sensor(data["INSIDE"], sensor_inside, "INSIDE")
        report_sensor(data["OUTSIDE"], sensor_outside, "OUTSIDE")
        report_sensor(data["REPEATER"], sensor_repeater, "REPEATER")
    except Exception as e:
        print(f"Exception during reporting: {e}")
        reboot()
    try:
        i = 1
        for key in ["INSIDE", "OUTSIDE", "REPEATER"]:
            display_value(i, data[key][0])
            led.toggle()
            time.sleep(2)
            i += 1
            display_value(i, data[key][1])
            led.toggle()
            time.sleep(2)
            i += 1
    except Exception as e:
        print(f"Exception during display: {e}")
        reboot()
            
            
async def main():
    print("Starting main loop...")

    MAX_TIMEOUT = 90
    while True:
        try:
            task = uasyncio.create_task(loop())
            await uasyncio.wait_for(task, timeout=MAX_TIMEOUT)
        except uasyncio.TimeoutError:
            print("The task was cancelled due to a timeout")
            reboot()

uasyncio.run(main())
