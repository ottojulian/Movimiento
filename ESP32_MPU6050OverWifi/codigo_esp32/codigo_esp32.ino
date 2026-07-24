#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <OSCMessage.h>
#include <WiFiUdp.h>
#include <WiFi.h>
#include <MadgwickAHRS.h>

////////////////////////////////
//////// INIT VARIABLES ////////
////////////////////////////////

unsigned long lastUdpRestart = 0;
const unsigned long udpRestartInterval = 15000;

int mseg_delay = 20;

const char* oscAddress = "/tracker";

const int boton1Pin = 33;
const int boton2Pin = 32;

const int ledR = 27;
const int ledG = 26;
const int ledB = 25;

String macAddressStr = "";

// -------------------------
// FILTER
// -------------------------

Madgwick filter;

// OUTPUT QUATERNION
float qw, qx, qy, qz;

////////////////////////////////
//////// NETWORK SETUP /////////
////////////////////////////////

struct WifiNetwork {
  const char* ssid;
  const char* pass;
  IPAddress staticIP;
  IPAddress gateway;
  IPAddress subnet;
  IPAddress outIp;
};

WifiNetwork networks[] = {
  {
    "LAB1507",
    "7051BAL!",
    IPAddress(10,1,101,170),
    IPAddress(10,1,103,254),
    IPAddress(255,255,252,0),
    IPAddress(10,1,103,255)
  }
};

const int networkCount = sizeof(networks) / sizeof(networks[0]);

IPAddress outIp;
const unsigned int outPort = 9000;
const unsigned int localPort = 8000;

WiFiUDP Udp;
Adafruit_MPU6050 mpu;

////////////////////////////////
//////// LED UTILS /////////////
////////////////////////////////

void setLed(bool r, bool g, bool b) {
  digitalWrite(ledR, r ? LOW : HIGH);
  digitalWrite(ledG, g ? LOW : HIGH);
  digitalWrite(ledB, b ? LOW : HIGH);
}

////////////////////////////////
//////// WIFI /////////////////
////////////////////////////////

bool connectToKnownWiFi() {

  for (int i = 0; i < networkCount; i++) {

    WiFi.disconnect(true);
    delay(200);

    WiFi.config(
      networks[i].staticIP,
      networks[i].gateway,
      networks[i].subnet
    );

    WiFi.begin(networks[i].ssid, networks[i].pass);

    int timeout = 20;

    while (WiFi.status() != WL_CONNECTED && timeout--) {
      setLed(false, true, true);
      delay(200);
      setLed(false, false, false);
      delay(200);
    }

    if (WiFi.status() == WL_CONNECTED) {
      outIp = networks[i].outIp;
      return true;
    }
  }

  return false;
}

////////////////////////////////
//////////// SETUP /////////////
////////////////////////////////

void setup() {

  Serial.begin(9600);

  pinMode(ledR, OUTPUT);
  pinMode(ledG, OUTPUT);
  pinMode(ledB, OUTPUT);

  WiFi.setSleep(false);
  WiFi.mode(WIFI_STA);

  while (!connectToKnownWiFi()) {
    delay(2000);
  }

  Udp.begin(localPort);

  macAddressStr = WiFi.macAddress();

  pinMode(boton1Pin, INPUT_PULLUP);
  pinMode(boton2Pin, INPUT_PULLUP);

  if (!mpu.begin()) {
    while (1);
  }

  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  filter.begin(100);
}

////////////////////////////////
//////////// LOOP //////////////
////////////////////////////////

void loop() {

  // IMPORTANT: we are NOT using Madgwick output here (pure stable IMU tilt model)

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);


  // -------------------------
  // Angular vel
  // -------------------------

  float gx = g.gyro.x;
  float gy = g.gyro.y;   // FIXED SIGN
  float gz = g.gyro.z;

  // -------------------------
  // AXIS CORRECTION
  // -------------------------

  float ax = a.acceleration.x;
  float ay = a.acceleration.y;   
  float az = a.acceleration.z;

  // -------------------------
  // TILT-BASED ORIENTATION
  // -------------------------

  float roll  = atan2(ay, az);
  float pitch = atan2(-ax, sqrt(ay * ay + az * az));
  float yaw   = 0.0f;

  // -------------------------
  // QUATERNION BUILD
  // -------------------------

  float cy = cos(yaw * 0.5f);
  float sy = sin(yaw * 0.5f);
  float cp = cos(pitch * 0.5f);
  float sp = sin(pitch * 0.5f);
  float cr = cos(roll * 0.5f);
  float sr = sin(roll * 0.5f);

  qw = cr * cp * cy + sr * sp * sy;
  qx = sr * cp * cy - cr * sp * sy;
  qy = cr * sp * cy + sr * cp * sy;
  qz = cr * cp * sy - sr * sp * cy;

  // -------------------------
  // NORMALIZATION (IMPORTANT)
  // -------------------------

  float norm = sqrt(qw*qw + qx*qx + qy*qy + qz*qz);

  if (norm > 0.0001f) {
    qw /= norm;
    qx /= norm;
    qy /= norm;
    qz /= norm;
  }

  // -------------------------
  // BUTTONS
  // -------------------------

  int b1 = !digitalRead(boton1Pin);
  int b2 = !digitalRead(boton2Pin);

  // -------------------------
  // OSC (VVVV ORDER: X Y Z W)
  // -------------------------

  OSCMessage msg(oscAddress);

  msg.add(qx);
  msg.add(qy);
  msg.add(qz);
  msg.add(qw);

  // Giroscopio (raw, for visualization / debugging / physics)
  msg.add(ax);
  msg.add(ay);
  msg.add(az);

  msg.add(gx);
  msg.add(gy);
  msg.add(gz);

  msg.add((int32_t)b1);
  msg.add((int32_t)b2);

  Udp.beginPacket(outIp, outPort);
  msg.send(Udp);
  Udp.endPacket();
  msg.empty();

  delay(mseg_delay);
}