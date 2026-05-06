#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* serverApiUrl = "http://192.168.2.4:5000/api/light_status";

const int LIGHT_PIN = 2;

void setup() {
    Serial.begin(115200);
    pinMode(LIGHT_PIN, OUTPUT);
    digitalWrite(LIGHT_PIN, LOW);

    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nConnected to WiFi!");
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(serverApiUrl);
        
        int httpResponseCode = http.GET();
        
        if (httpResponseCode > 0) {
            String payload = http.getString();
            
            JsonDocument doc;
            DeserializationError error = deserializeJson(doc, payload);
            
            if (!error) {
                bool shouldBeOn = doc["light_on"];
                
                if (shouldBeOn) {
                    digitalWrite(LIGHT_PIN, HIGH);
                    Serial.println("Light turned ON");
                } else {
                    digitalWrite(LIGHT_PIN, LOW);
                    Serial.println("Light turned OFF");
                }
            } else {
                Serial.print("deserializeJson() failed: ");
                Serial.println(error.c_str());
            }
        } else {
            Serial.print("Error code: ");
            Serial.println(httpResponseCode);
        }
        http.end();
    }
    
    delay(2000); // Check every 2 seconds
}
