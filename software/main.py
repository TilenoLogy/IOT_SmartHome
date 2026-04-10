import threading
import socket
import matplotlib.pyplot as plt
import sqlite3
import time
from flask import Flask, render_template, jsonify
import serial

HOST = '192.168.2.4'
PORT = 2234

app = Flask(__name__)

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
    #return render_template("index.html", temp=temp, humidity=hum)




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
    #return render_template("index.html", temp=temp, humidity=hum)




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
    #return render_template("index.html", temp=temp, humidity=hum)



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

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)



# plt.ion()

# x1 = [0, 1]
# y1 = [0, 0]

# x2 = [0, 1]
# y2 = [0, 0]

# fig, (ax,ax2)= plt.subplots(1,2)
# fig.canvas.manager.set_window_title('Temperature and Humidity')
# lineplt, = ax.plot(x1,y1)
# ax.set_title('Temperature')
# ax.set_xlabel('Time')
# ax.set_ylabel('Temp')

# lineplt2, = ax2.plot(x2,y2) #myb je x1,y1
# ax2.set_title('Humidity')
# ax2.set_xlabel('Time')
# ax2.set_ylabel('Hum')

    


        
       

        # hum=math.ceil(hum) 
        # x = [val + 1 for val in x1]
        
        # x1.append(x1[-1] + 1)
        # y1.append(temp)
        # x2.append(x2[-1] + 1)
        # y2.append(hum)
        
#         lineplt.set_xdata(x1)
#         lineplt.set_ydata(y1)
#         lineplt2.set_xdata(x2)
#         lineplt2.set_ydata(y2)
        

#         ax.set_xlim(0, len(x1))
#         ax.set_ylim(min(y1) - 1, max(y1) + 1)
#         ax2.set_xlim(0, len(x2))
#         ax2.set_ylim(min(y2) - 1, max(y2) + 1)

#         fig.canvas.draw()
#         fig.canvas.flush_events()
        
        # time.sleep(0.5)
        # if not line:
        #     break
        # print(f"Received {line.strip()}")
# conn.commit()
# conn.close()
        
        