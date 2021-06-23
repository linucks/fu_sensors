#include <SPI.h>
#include <WiFiNINA.h>

#include <ArduinoJson.h>

// Sensors
#include "DHTesp.h"
#include <OneWire.h>
#include "DFRobot_EC.h"
#include "DFRobot_PH.h"

char ssid[] = "HAL8000";        // your network SSID (name)
char pass[] = "ziLEUTWLj4x";    // your network password (use for WPA, or use as key for WEP)
int wifiStatus = WL_IDLE_STATUS;     // the Wifi radio's status


// Time in milliseconds
#define SAMPLE_WINDOW 5000
char sbuff[150];

// Analog Inputs
int co2Pin = A0;
int ecPin = A1;
int phPin = A2;

// Digital Inputs
int dhtPin = 2; // Temp and Humidity
int DS18S20_Pin = 3; // Wet temperature
int SEN0217_Pin = 4; // Flow sensor

// Data collecting strucutures
DHTesp dht; // Temperature and Humidity
OneWire ds(DS18S20_Pin); // Wet temperature chip i/o
DFRobot_EC ecProbe; // EC probe
DFRobot_PH phProbe; // pH probe
volatile int pulseCount; // Flow Sensor

#define JSON_DOC_SIZE 200;
const int jsize=JSON_DOC_SIZE;
StaticJsonDocument<jsize> doc;


// InfluxDB v2 server url, e.g. https://eu-central-1-1.aws.cloud2.influxdata.com (Use: InfluxDB UI -> Load Data -> Client Libraries)
#define INFLUXDB_SERVER "westeurope-1.azure.cloud2.influxdata.com"
// InfluxDB v2 server or cloud API authentication token (Use: InfluxDB UI -> Data -> Tokens -> <select token>)
#define INFLUXDB_TOKEN "SibMj38WbdjAWgrjZMRF2aBCeiE3vK44drLuG-Ioee9C-cTPJydc9KoBFu1-A9vEa4vAzwjX-WjKBulAOrkcXA=="
// InfluxDB v2 organization id (Use: InfluxDB UI -> User -> About -> Common Ids )
#define INFLUXDB_ORG "accounts@farmurban.co.uk"
// InfluxDB v2 bucket name (Use: InfluxDB UI ->  Data -> Buckets)
#define INFLUXDB_BUCKET "Loz_test"

#define INFLUXDB_MEASUREMENT "LozExpt"
#define INFLUXDB_STATION_ID "ardwifi1"

WiFiClient client;

float getPH(int phPin, float temperature){
   float voltage = analogRead(phPin)/1024.0*5000;
   return phProbe.readPH(voltage,temperature);
}


float getEC(int ecPin, float temperature){
   float voltage = analogRead(ecPin)/1024.0*5000;
   return ecProbe.readEC(voltage,temperature);
}


int getCO2(int analogPin){
    // Calculate CO2 concentration in ppm
    int sensorValue = analogRead(analogPin);
/*
    sprintf(sbuff, "sensorValue1 is %d",sensorValue);
    Serial.println(sbuff);
*/
    float voltage = sensorValue*(5000/1024.0);
    if(voltage == 0)
    {
      // Error
      return -1.0;
    }
    else if(voltage < 400)
    {
      // Preheating
      return -2.0;
    }
    else
    {
      int voltage_difference=voltage-400;
      return (int) (voltage_difference*50.0/16.0);
    }
}

float getTempWet(){
  //returns the temperature from one DS18S20 in DEG Celsius
  byte data[12];
  byte addr[8];

  if ( !ds.search(addr)) {
      //no more sensors on chain, reset search
      ds.reset_search();
      return -1000;
  }

  if ( OneWire::crc8( addr, 7) != addr[7]) {
      //Serial.println("CRC is not valid!");
      return -1001;
  }

  if ( addr[0] != 0x10 && addr[0] != 0x28) {
      //Serial.print("Device is not recognized");
      return -1002;
  }

  ds.reset();
  ds.select(addr);
  ds.write(0x44,1); // start conversion, with parasite power on at the end

  byte present = ds.reset();
  ds.select(addr);    
  ds.write(0xBE); // Read Scratchpad
  
  for (int i = 0; i < 9; i++) { // we need 9 bytes
    data[i] = ds.read();
  }
  
  ds.reset_search();
  
  byte MSB = data[1];
  byte LSB = data[0];

  float tempRead = ((MSB << 8) | LSB); //using two's compliment
  float TemperatureSum = tempRead / 16;
  
  return TemperatureSum;
}

void flowPulse()
{
  pulseCount += 1;
}


double getFlow()
/* From YF-S201 manual:
    Pluse Characteristic:F=7Q(L/MIN).
    2L/MIN=16HZ 4L/MIN=32.5HZ 6L/MIN=49.3HZ 8L/MIN=65.5HZ 10L/MIN=82HZ
    sample_window is in milli seconds, so hz is pulseCount * 1000 / SAMPLE_WINDOW
 */
{
  double hertz = (double) (pulseCount * 1000.0 ) / SAMPLE_WINDOW;
  pulseCount = 0; // reset flow counter
  return hertz / 7.0;
}


void printWifiData() {
  // print your board's IP address:
  IPAddress ip = WiFi.localIP();
  Serial.print("IP Address: ");
  Serial.println(ip);
  Serial.println(ip);
  // print your MAC address:
  byte mac[6];
  WiFi.macAddress(mac);
  Serial.print("MAC address: ");
  printMacAddress(mac);
}

void printCurrentNet() {
  // print the SSID of the network you're attached to:
  Serial.print("SSID: ");
  Serial.println(WiFi.SSID());
  // print the MAC address of the router you're attached to:
  byte bssid[6];
  WiFi.BSSID(bssid);
  Serial.print("BSSID: ");
  printMacAddress(bssid);
  // print the received signal strength:
  long rssi = WiFi.RSSI();
  Serial.print("signal strength (RSSI):");
  Serial.println(rssi);
  // print the encryption type:
  byte encryption = WiFi.encryptionType();
  Serial.print("Encryption Type:");
  Serial.println(encryption, HEX);
  Serial.println();
}

void printMacAddress(byte mac[]) {
  for (int i = 5; i >= 0; i--) {
    if (mac[i] < 16) {
      Serial.print("0");
    }
    Serial.print(mac[i], HEX);
    if (i > 0) {
      Serial.print(":");
    }
  }
  Serial.println();
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    Serial.begin(9600);
    dht.setup(dhtPin, DHTesp::DHT22);
    analogReference(DEFAULT); // Set the default voltage of the reference voltage
    attachInterrupt(digitalPinToInterrupt(SEN0217_Pin), flowPulse, RISING);
    pulseCount = 0;
    ecProbe.begin();
    phProbe.begin();


   // check for the WiFi module:
  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("Communication with WiFi module failed!");
    while (true); // don't continue
  }

  String fv = WiFi.firmwareVersion();
  if (fv < WIFI_FIRMWARE_LATEST_VERSION) {
    Serial.println("Please upgrade the firmware");
  }
 
  // attempt to connect to Wifi network:
  while (wifiStatus != WL_CONNECTED) {
    Serial.print("Attempting to connect to WPA SSID: ");
    Serial.println(ssid);
    // Connect to WPA/WPA2 network:
    wifiStatus = WiFi.begin(ssid, pass);
    // wait 10 seconds for connection:
    delay(10000);
  }
  // you're connected now, so print out the data:
  Serial.print("You're connected to the network");
  printCurrentNet();
  printWifiData();

}

static char invalidChars[] = "$&+,/:;=?@ <>#%{}|\\^~[]`";

static char hex_digit(char c) {
    return "0123456789ABCDEF"[c & 0x0F];
}

String urlEncode(const char* src) {
    int n=0;
    char c,*s = (char *)src;
    while ((c = *s++)) {
        if(strchr(invalidChars, c)) {
            n++;
        }
    }
    String ret;
    ret.reserve(strlen(src)+2*n+1);
    s = (char *)src;
    while ((c = *s++)) {
       if (strchr(invalidChars,c)) {
           ret += '%';
           ret += hex_digit(c >> 4);
           ret += hex_digit(c);
      }
      else ret += c;
   }
   return ret;
}


void loop() {
    //Serial.println("Starting main loop");
    //digitalWrite(LED_BUILTIN, HIGH);
    TempAndHumidity th = dht.getTempAndHumidity();
    float t = th.temperature;
    float h = th.humidity;
    int co2 = getCO2(co2Pin);
    float twet = getTempWet();
    float ec = getEC(ecPin, twet);
    float ph = getPH(phPin, twet);
//
//    // json
//    doc["tempair"] = t;
//    doc["humidity"] = h;
//    doc["tempwet"] = twet;
//    doc["co2"] = co2;
//    doc["cond"] = ec; // For unfathomable reasons influxdb won't accept ec as a name. WTF?!?!?!@@
//    doc["ph"] = ph;
//    doc["flow"] = getFlow();
//    serializeJson(doc, Serial);

    // Clear fields for reusing the point. Tags will remain untouched
//    influxPt.clearFields();
//    influxPt.addField("tempair", t);
//    influxPt.addField("humidity", th);
//    influxPt.addField("tempwet", twet);
//    influxPt.addField("co2", co2);
//    influxPt.addField("cond", ec);
//    influxPt.addField("ph", ph);
//    influxPt.addField("flow", getFlow());
//    String lineProtocol = INFLUXDB_MEASUREMENT + ",stationid=";

    String lineProtocol = INFLUXDB_MEASUREMENT;
    // Tags
    lineProtocol += ",stationid=";
    lineProtocol += INFLUXDB_STATION_ID;
    //fields
    lineProtocol += " tempair=";
    lineProtocol += String(t, 2);
    lineProtocol += ",tempwet=";
    lineProtocol += String(h, 2);
    lineProtocol += ",co2=";
    lineProtocol += co2;
    lineProtocol += ",cond=";
    lineProtocol += String(ec, 2);
    lineProtocol += ",ph=";
    lineProtocol += String(ph, 2);
    lineProtocol += ",flow=";
    lineProtocol += String(getFlow(), 1);

    String url = "/api/v2/write?org=" + urlEncode(INFLUXDB_ORG);
    url += "&bucket=";
    url += urlEncode(INFLUXDB_BUCKET);


     // if you get a connection, report back via serial:
    if (client.connectSSL(INFLUXDB_SERVER, 443)) {
//    if (client.connect(INFLUXDB_SERVER, 80)) {
      Serial.println("connected");
      client.println("POST " + url + " HTTP/1.1");
      Serial.println("POST " + url + " HTTP/1.1");
      client.println("Host: " + String(INFLUXDB_SERVER));
      client.println("Content-Type: text/plain");
      client.println("Authorization: Token " + String(INFLUXDB_TOKEN));
      client.println("Connection: close");
      client.print("Content-Length: ");
      client.println(lineProtocol.length());
//      client.println("Connection: close");
      client.println(); // end HTTP header
      client.print(lineProtocol);  // send HTTP body
      Serial.println(lineProtocol);

//      while(client.connected()) {
//        if(client.available()){
//          // read an incoming byte from the server and print it to serial monitor:
//          char c = client.read();
//          Serial.print(c);
//        }
//      }
    if (client.connected()) {
      client.stop();
    }
    Serial.println();
    Serial.println("disconnected");
    } else {// if not connected:
      Serial.println("connection failed");
    }
 
//   // If no Wifi signal, try to reconnect it
//  if ((WiFi.RSSI() == 0) && (wifiMulti.run() != WL_CONNECTED)) {
//    Serial.println("Wifi connection lost");
//  }

    delay(SAMPLE_WINDOW);
}