import threading
import socket
import sqlite3
import time
from flask import Flask, render_template, jsonify


HOST = '192.168.2.4'
PORT = 2234

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('0.0.0.0', PORT))
s.listen(0)

app = Flask(__name__)

automode = False
open1 = False



temp = None
hum = None
global_client = None

# conn = sqlite3.connect('podatki.db')
# cursor=conn.cursor()
# cursor.execute("CREATE TABLE IF NOT EXISTS meritve (temperatura DECIMAL, vlaga DECIMAL)")



@app.route('/')
def index():
    return render_template("index.html", temp=temp, humidity=hum)

@app.route('/api/status')
def get_status():
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})

@app.route('/window_auto_mode')
def window_auto_mode():
    global automode, global_client
    #set auto mode to microcontroller
    print("Toggling auto mode over WiFi")
    if global_client:
        try:
            global_client.send(b'auto\n')
            automode = not automode
        except Exception as e:
            print(f"Error writing to WiFi socket: {e}")
    else:
        print("No ESP connected via WiFi to send command to.")
    
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})
    #return render_template("index.html", temp=temp, humidity=hum)




@app.route('/window_open')
def window_open():
    global open1, global_client
    #set auto mode to microcontroller
    print("Opening window over WiFi")
    if global_client:
        try:
            global_client.send(b'open\n')
            open1 = True
        except Exception as e:
            print(f"Error writing to WiFi socket: {e}")
    else:
        print("No ESP connected via WiFi to send command to.")
    
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})




@app.route('/window_close')
def window_close():
    global open1, global_client
    #set auto mode to microcontroller
    print("Closing window over WiFi")
    if global_client:
        try:
            global_client.send(b'close\n')
            open1 = False
        except Exception as e:
            print(f"Error writing to WiFi socket: {e}")
    else:
        print("No ESP connected via WiFi to send command to.")
    
    return jsonify({"temp": temp, "humidity": hum, "window": open1, "auto_mode": automode})



def get_socket_values():
    global temp, hum, global_client
    
    while True:
        try:
            print("Listening for incoming WiFi connection from ESP...")
            conn, addr = s.accept() # Accepts ONE continuous wifi connection
            conn.settimeout(60)
            global_client = conn 
            
            print(f"Connected to ESP via WiFi at {addr}!")
            sock_file = global_client.makefile('r')
            
            while True:
                line = sock_file.readline()
                if not line:
                    break # Connection lost naturally
                    
                # Parse the data
                try:
                    line = line.strip()
                    if not line:
                        continue
                        
                    t, h = line.split(",")
                    temp = float(t)
                    hum = float(h)
                    # cursor.execute("INSERT INTO meritve VALUES (?,?)",(temp,hum))
                    print(f"Received temperature: {temp}°C, humidity: {hum}%")
                except ValueError:
                    print("Received malformed data:", line)

        except Exception as e:
            print(f"WiFi connection error: {e}. Retrying connection in 5 seconds...")
            global_client = None
            time.sleep(5)


bg_thread = threading.Thread(target=get_socket_values, daemon=True)
bg_thread.start()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)



# conn.commit()
# conn.close()
        
        