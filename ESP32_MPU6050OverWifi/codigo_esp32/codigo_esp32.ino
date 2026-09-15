#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <OSCMessage.h>
#include <WiFiUdp.h>
#include <WiFi.h>
#include <MadgwickAHRS.h>

////////////////////////////////
// INIT VARIABLES
////////////////////////////////

unsigned long lastUdpRestart = 0;
const unsigned long udpRestartInterval = 15000;

const int mseg_delay = 20;

const char* oscAddress = "/tracker";

String macAddressStr = "";

////////////////////////////////
// FILTER
////////////////////////////////

Madgwick filter;

// OUTPUT QUATERNION
float qw, qx, qy, qz;

////////////////////////////////
// NETWORK SETUP
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
    IPAddress(10, 1, 101, 170),
    IPAddress(10, 1, 103, 254),
    IPAddress(255, 255, 252, 0),
    IPAddress(10, 1, 101, 205)
  }
};

IPAddress staticIP;
IPAddress gateway;
IPAddress subnet;
IPAddress outIp;

const int networkCount = sizeof(networks) / sizeof(networks[0]);

const unsigned int outPort = 9000;
const unsigned int localPort = 8000;

WiFiUDP Udp;
Adafruit_MPU6050 mpu;

////////////////////////////////
// WIFI CONNECTION
////////////////////////////////

bool connectToKnownWiFi() {

  for (int i = 0; i < networkCount; i++) {

    Serial.println();
    Serial.print("Intentando conectar a: ");
    Serial.println(networks[i].ssid);

    // Disconnect previous connection
    WiFi.disconnect(true);
    delay(500);

    // Configure static IP
    if (!WiFi.config(
          networks[i].staticIP,
          networks[i].gateway,
          networks[i].subnet
        )) {

      Serial.println("ERROR: No se pudo configurar la IP estatica.");
    }

    // Start WiFi connection
    WiFi.begin(networks[i].ssid, networks[i].pass);

    // Wait up to 10 seconds
    const unsigned long timeout = 10000;
    unsigned long startTime = millis();

    while (WiFi.status() != WL_CONNECTED &&
           millis() - startTime < timeout) {

      delay(250);
      Serial.print(".");
    }

    Serial.println();

    // Check connection
    if (WiFi.status() == WL_CONNECTED) {

      staticIP = networks[i].staticIP;
      gateway  = networks[i].gateway;
      subnet   = networks[i].subnet;
      outIp    = networks[i].outIp;

      Serial.println("WiFi conectado!");
      Serial.print("SSID: ");
      Serial.println(networks[i].ssid);

      Serial.print("IP: ");
      Serial.println(WiFi.localIP());

      Serial.print("Gateway: ");
      Serial.println(WiFi.gatewayIP());

      Serial.print("MAC: ");
      Serial.println(WiFi.macAddress());

      Serial.print("OSC destino: ");
      Serial.print(outIp);
      Serial.print(":");
      Serial.println(outPort);

      return true;
    }

    Serial.println("No se pudo conectar.");
  }

  return false;
}

////////////////////////////////
// SETUP
////////////////////////////////

void setup() {

  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("==============================");
  Serial.println("ESP32 MPU6050 OSC TRACKER");
  Serial.println("==============================");

  // WiFi
  WiFi.setSleep(false);
  WiFi.mode(WIFI_STA);

  while (!connectToKnownWiFi()) {

    Serial.println("Reintentando WiFi en 2 segundos...");
    delay(2000);
  }

  // UDP
  if (Udp.begin(localPort)) {
    Serial.print("UDP iniciado en puerto ");
    Serial.println(localPort);
  } else {
    Serial.println("ERROR: No se pudo iniciar UDP.");
  }

  macAddressStr = WiFi.macAddress();

  //////////////////////////////////
  // MPU6050
  //////////////////////////////////

  Serial.println("Inicializando MPU6050...");

  if (!mpu.begin()) {

    Serial.println("ERROR: MPU6050 no encontrado.");

    while (1) {
      delay(1000);
    }
  }

  Serial.println("MPU6050 OK.");

  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  //////////////////////////////////
  // MADGWICK
  //////////////////////////////////

  filter.begin(100);

  Serial.println("Tracker listo.");
  Serial.println("==============================");
}

////////////////////////////////
// LOOP
////////////////////////////////

void loop() {

  //////////////////////////////////
  // WIFI CHECK
  //////////////////////////////////

  if (WiFi.status() != WL_CONNECTED) {

    Serial.println("WiFi desconectado. Reconectando...");

    Udp.stop();

    while (!connectToKnownWiFi()) {
      delay(2000);
    }

    Udp.begin(localPort);
  }

  //////////////////////////////////
  // MPU6050 READ
  //////////////////////////////////

  sensors_event_t a, g, temp;

  mpu.getEvent(&a, &g, &temp);

  //////////////////////////////////
  // ANGULAR VELOCITY
  //////////////////////////////////

  float gx = g.gyro.x;
  float gy = g.gyro.y;
  float gz = g.gyro.z;

  //////////////////////////////////
  // ACCELERATION
  //////////////////////////////////

  float ax = a.acceleration.x;
  float ay = a.acceleration.y;
  float az = a.acceleration.z;

  //////////////////////////////////
  // TILT-BASED ORIENTATION
  //
  // This intentionally does NOT use
  // the Madgwick output.
  //////////////////////////////////

  float roll  = atan2(ay, az);

  float pitch = atan2(
    -ax,
    sqrt(ay * ay + az * az)
  );

  // Accelerometer cannot determine absolute yaw.
  float yaw = 0.0f;

  //////////////////////////////////
  // QUATERNION BUILD
  //////////////////////////////////

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

  //////////////////////////////////
  // QUATERNION NORMALIZATION
  //////////////////////////////////

  float norm = sqrt(
    qw * qw +
    qx * qx +
    qy * qy +
    qz * qz
  );

  if (norm > 0.0001f) {

    qw /= norm;
    qx /= norm;
    qy /= norm;
    qz /= norm;
  }

  //////////////////////////////////
  // OSC MESSAGE
  //
  // VVVV ORDER:
  // X Y Z W
  //////////////////////////////////

  OSCMessage msg(oscAddress);

  // Quaternion
  msg.add(qx);
  msg.add(qy);
  msg.add(qz);
  msg.add(qw);

  // Accelerometer
  msg.add(ax);
  msg.add(ay);
  msg.add(az);

  // Gyroscope
  msg.add(gx);
  msg.add(gy);
  msg.add(gz);

  //////////////////////////////////
  // SEND OSC
  //////////////////////////////////

  Udp.beginPacket(outIp, outPort);

  msg.send(Udp);

  Udp.endPacket();

  msg.empty();

  //////////////////////////////////
  // LOOP TIMING
  //////////////////////////////////

  delay(mseg_delay);
}