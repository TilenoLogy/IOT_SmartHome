import os
import threading
import socket
import matplotlib.pyplot as plt
import sqlite3
import time
from flask import Flask, render_template, jsonify
import serial
from vision_tracker import start_tracker, occupants

HOST = '192.168.2.4'
PORT = 2234

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, 
            template_folder=os.path.join(base_dir, 'templates'), 
            static_folder=os.path.join(base_dir, 'static'))

automode = False
open1 = False


try:
    ser = serial.Serial()
    ser.baudrate = 115200
    ser.port = 'COM10'
    ser.open()
except Exception as e:
    print(f"Error opening serial port: {e}")
    ser = None

temp = None
hum = None


# conn = sqlite3.connect('podatki.db')
# cursor=conn.cursor()
# cursor.execute("CREATE TABLE IF NOT EXISTS meritve (temperatura DECIMAL, vlaga DECIMAL)")


@app.route('/')
def index():
    return render_template("index.html", temp=temp, humidity=hum)

@app.route('/api/status')
def get_status():
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})

@app.route('/api/occupants')
def get_occupants():
    # Pass along camera connection state
    camera_connected = tracker_instance.camera_connected if tracker_instance else False
    return jsonify({
        "occupants": list(occupants.keys()), 
        "count": len(occupants),
        "camera_connected": camera_connected
    })

@app.route('/window_auto_mode')
def window_auto_mode():
    global automode
    #set auto mode to microcontroller
    print("Toggling auto mode")
    try:
        ser.write(b'auto\n')
        ser.flush()
        automode = not automode
    except Exception as e:
        print(f"Error writing to serial port: {e}")
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})


@app.route('/window_open')
def window_open():
    global open1
    #set auto mode to microcontroller
    try:
        ser.write(b'open\n')
        ser.flush()
        open1=True
    except Exception as e:
        print(f"Error writing to serial port: {e}")
    print("Opening window")
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})


@app.route('/window_close')
def window_close():
    global open1
    #set auto mode to microcontroller
    try:
        ser.write(b'close\n')
        ser.flush()
        open1=False
    except Exception as e:
        print(f"Error writing to serial port: {e}")
    print("Closing window")
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})


def get_socket_values():
    global temp, hum
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                sock_file = s.makefile('r')
                print("Connected to ESP!")
                while True:
                    line = sock_file.readline()
                    if not line:
                        break # Connection lost naturally
                        
                    # Parse the data
                    try:
                        line = line.strip()
                        if line.startswith("ESP_ECHO,"):
                            print(f"\nPysical string received by ESP: '{line.split(',')[1]}'")
                            continue
                        elif line.startswith("ESP_EXEC,"):
                            print(f"ESP IS NOW EXECUTING THE MOTOR PINS FOR: {line.split(',')[1]}\n")
                            continue
                            
                        t, h = line.split(",")
                        temp = float(t)
                        hum = float(h)
                        # cursor.execute("INSERT INTO meritve VALUES (?,?)",(temp,hum))
                        print(f"Received temperature: {temp}°C, humidity: {hum}%")
                    except ValueError:
                        print("Received malformed data:", line)
        except Exception as e:
            print(f"Socket connection error: {e}. Retrying in 5 seconds...")
        time.sleep(60)


bg_thread = threading.Thread(target=get_socket_values, daemon=True)
bg_thread.start()

# Start the vision tracker
tracker_instance = start_tracker()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)


# conn.commit()
# conn.close()
