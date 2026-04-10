#include <Arduino.h>

#include "DHT.h"
#include <LiquidCrystal.h>
#include <WiFi.h>

int motor1pin1 = 13;
int motor2pin1 = 12;
int motor1pin2 = 14;
int motor2pin2 = 27;

#define DHT22_PIN 15
DHT dht(DHT22_PIN, DHT22);
LiquidCrystal lcd(4, 21, 18, 5, 23, 22);

const char *ssid = "SSID";
const char *password = "PASSWORD";
bool open1 = false;

unsigned long startTime;
unsigned long elapsedTime;

unsigned long startTime1;
unsigned long elapsedTime1;



bool autoMode = false;





WiFiServer server(2234);

void setup() {
    pinMode(motor1pin1, OUTPUT);
    pinMode(motor1pin2, OUTPUT);
    pinMode(motor2pin1, OUTPUT);
    pinMode(motor2pin2, OUTPUT);

    // pinMode(Fan, OUTPUT);
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    Serial.begin(115200);
    dht.begin();
    lcd.begin(16, 2);
    lcd.clear();
    Serial.println("Connecting to WiFi ..");

    while (WiFi.status() != WL_CONNECTED) {
        Serial.print('O');
        delay(1000);
    }
    Serial.println(WiFi.localIP());
    lcd.print(WiFi.localIP());
    // // Serial.print("RRSI: ");
    // // Serial.println(WiFi.RSSI());
    Serial.println(WiFi.status());
    int st = WiFi.scanNetworks();
    Serial.println(st);
    Serial.println(WiFi.SSID(1));
    server.begin();

    zapriOkno();
}


void zapriOkno() {
    Serial.println("Closing window command triggered.");
    open1 = false;
    
    // digitalWrite(Fan, 0);-----------------
    //  digitalWrite(Actuator, 0);
    digitalWrite(motor1pin1, LOW); // Fan izklop
    delay(100);
    digitalWrite(motor2pin1, HIGH);
    digitalWrite(motor2pin2, LOW); // ZAPIRANJE

    delay(10000);

    digitalWrite(motor2pin1, LOW); // stop actuator
}


void odpriOkno(){
    Serial.println("Opening window command triggered.");
    // digitalWrite(Fan, 1);-------------
    //  digitalWrite(Actuator, 1);

    digitalWrite(motor2pin1, LOW); // Odpiranje okna
    digitalWrite(motor2pin2, HIGH);

    open1 = true;
    delay(10000);
    digitalWrite(motor2pin1, LOW); // actuator stop
    delay(100);
    digitalWrite(motor1pin1, HIGH); // Fan prižgan
}


float hum;
float temp;
bool once = true;


void loop() {

    WiFiClient client = server.available(); // Listen for incoming clients
    if (client) {
        if (once) {
            once = false;
            delay(5000);
            lcd.clear();
            
            
            Serial.println("You can open it now");
            open1 = true;
            

            digitalWrite(motor1pin1, LOW); // Fan izklop
            delay(100);
            digitalWrite(motor2pin1, LOW); // Odpiranje okna
            digitalWrite(motor2pin2, HIGH);
            delay(10000);
            digitalWrite(motor2pin2, LOW);
                
        }
        Serial.print("New client");
        String niz = "";
        unsigned long lastSendTime = 0;
        unsigned long lastReadTime = 0;
        
        // Initial read
        hum = dht.readHumidity();
        temp = dht.readTemperature();

        while (client.connected()) {
            // Read sensors at most every 2 seconds to avoid blocking the loop
            if (millis() - lastReadTime >= 2000) {
                hum = dht.readHumidity();
                temp = dht.readTemperature();
                lastReadTime = millis();
            }
            
            niz = "";
            if (Serial.available()) {
                niz = Serial.readStringUntil('\n');
                niz.trim(); // Optional: trim whitespace
            }

            if (niz.length() > 0) {
                Serial.println("niz: " + niz);
                client.println("ESP_ECHO," + niz); // Send the command back to Python so you can see it!
                
                niz.toLowerCase(); // Convert to lowercase just in case
                if (niz.indexOf("auto") >= 0) {
                    client.println("ESP_EXEC,auto"); // Confirm execution to Python
                    autoMode = !autoMode;
                } else if (niz.indexOf("open") >= 0) {
                    client.println("ESP_EXEC,open"); // Confirm execution to Python
                    Serial.println("Opening the window...");
                    odpriOkno();
                } else if (niz.indexOf("close") >= 0) {
                    client.println("ESP_EXEC,close"); // Confirm execution to Python
                    Serial.println("Closing the window...");
                    zapriOkno();
                }
            }



            if (autoMode) {
                if (temp > 22 && !open1 || hum > 80 && !open1) {
                    odpriOkno();
                } else if (open1 && temp < 22 && hum < 80) {
                    zapriOkno();
                }
            } 
            
            

            lcd.setCursor(0, 0);
            lcd.print("Temp:");
            lcd.print(temp);
            lcd.setCursor(0, 1);
            lcd.print("Humidity:");
            lcd.print(hum);
            
            if (millis() - lastSendTime >= 5000) {
                Serial.println("Client available");
                client.println(String(temp) + "," + String(hum));
                lastSendTime = millis();
            }
            delay(10); // Check serial very fast
        }

        client.stop();
    }
    delay(50);
}

