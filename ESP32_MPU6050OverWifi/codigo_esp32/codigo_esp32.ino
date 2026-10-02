#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <OSCMessage.h>
#include <WiFiUdp.h>
#include <WiFi.h>

// Preprocessor trick to access private variables of Madgwick library
// without needing to modify the standard installed library files.
#define private public
#include <MadgwickAHRS.h>
#undef private

////////////////////////////////
// INIT VARIABLES
////////////////////////////////

const int mseg_delay = 20;

const char* oscAddress = "/tracker";

String macAddressStr = "";

// Cathode LED is on pin 17. 
// Since Anode is on 3.3V, pulling pin 17 LOW turns the LED ON.
// Pulling pin 17 HIGH turns the LED OFF.
const int ledPin = 27;

////////////////////////////////
// MADGWICK FILTER
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
    IPAddress(255, 255, 255, 255) // Global Broadcast Address (Universal)
  },
    {
    "pablo_truck",
    "748159263",
    IPAddress(192, 168, 1, 170),
    IPAddress(192, 168, 1, 1),
    IPAddress(255, 255, 255, 0),
    IPAddress(255, 255, 255, 255) // Global Broadcast Address (Universal)
  }
};

IPAddress staticIP;
IPAddress gateway;
IPAddress subnet;
IPAddress outIp;

const int networkCount =
  sizeof(networks) / sizeof(networks[0]);

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

      Serial.println(
        "ERROR: No se pudo configurar la IP estatica."
      );
    }

    // Start WiFi connection
    WiFi.begin(
      networks[i].ssid,
      networks[i].pass
    );

    // Wait up to 10 seconds
    const unsigned long timeout = 10000;
    unsigned long startTime = millis();
    unsigned long lastBlinkTime = 0;
    bool ledState = false;

    while (
      WiFi.status() != WL_CONNECTED &&
      millis() - startTime < timeout
    ) {
      // Blink while connecting: toggle every 250ms
      unsigned long currentMillis = millis();
      if (currentMillis - lastBlinkTime >= 250) {
        lastBlinkTime = currentMillis;
        ledState = !ledState;
        digitalWrite(ledPin, ledState ? LOW : HIGH); // LOW is ON, HIGH is OFF
      }

      delay(50);
      Serial.print(".");
    }

    Serial.println();

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

      digitalWrite(ledPin, LOW);
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
  // Configure LED pin as output
  pinMode(ledPin, OUTPUT);
  // Turn LED OFF on boot (HIGH because it is a active-low/cathode-controlled LED)
  digitalWrite(ledPin, HIGH);

  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("==============================");
  Serial.println("ESP32 MPU6050 OSC TRACKER");
  Serial.println("==============================");

  //////////////////////////////////
  // WIFI
  //////////////////////////////////

  WiFi.setSleep(false);
  WiFi.mode(WIFI_STA);

  while (!connectToKnownWiFi()) {

    Serial.println(
      "Reintentando WiFi en 2 segundos..."
    );

    delay(2000);
  }

  //////////////////////////////////
  // UDP
  //////////////////////////////////

  if (Udp.begin(localPort)) {

    Serial.print("UDP iniciado en puerto ");
    Serial.println(localPort);

  } else {

    Serial.println(
      "ERROR: No se pudo iniciar UDP."
    );
  }

  macAddressStr = WiFi.macAddress();

  //////////////////////////////////
  // MPU6050
  //////////////////////////////////

  Serial.println(
    "Inicializando MPU6050..."
  );

  if (!mpu.begin()) {

    Serial.println(
      "ERROR: MPU6050 no encontrado."
    );

    // Blink twice repeatedly if MPU is disconnected
    while (1) {
      // Blink 1
      digitalWrite(ledPin, LOW); // ON
      delay(150);
      digitalWrite(ledPin, HIGH); // OFF
      delay(150);
      
      // Blink 2
      digitalWrite(ledPin, LOW); // ON
      delay(150);
      digitalWrite(ledPin, HIGH); // OFF
      
      delay(1000); // Wait before repeating double-blink pattern
    }
  }

  Serial.println("MPU6050 OK.");
  // Turn LED fully ON (LOW because of cathode control) to show device is ON & ready
  digitalWrite(ledPin, LOW);

  //////////////////////////////////
  // MPU6050 CONFIGURATION
  //////////////////////////////////

  mpu.setAccelerometerRange(
    MPU6050_RANGE_8_G
  );

  mpu.setGyroRange(
    MPU6050_RANGE_500_DEG
  );

  mpu.setFilterBandwidth(
    MPU6050_BAND_21_HZ
  );

  //////////////////////////////////
  // MADGWICK
  //////////////////////////////////

  // 20 ms = nominal 50 Hz
  float sampleFreq =
    1000.0f / float(mseg_delay);

  filter.begin(sampleFreq);

  Serial.print(
    "Madgwick sample frequency: "
  );
  Serial.print(sampleFreq);
  Serial.println(" Hz");

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

    Serial.println(
      "WiFi desconectado. Reconectando..."
    );

    Udp.stop();

    while (!connectToKnownWiFi()) {
      delay(2000);
    }

    Udp.begin(localPort);
  }

  //////////////////////////////////
  // MPU6050 READ
  //////////////////////////////////

  sensors_event_t a;
  sensors_event_t g;
  sensors_event_t temp;

  mpu.getEvent(
    &a,
    &g,
    &temp
  );

  //////////////////////////////////
  // ACTUAL SENSOR DATA
  //////////////////////////////////
  //
  // These variables contain the
  // REAL MPU6050 measurements.
  //
  // Accelerometer:
  // m/s^2
  //
  // Gyroscope:
  // rad/s
  //

  float ax = a.acceleration.x;
  float ay = a.acceleration.y;
  float az = a.acceleration.z;

  float gx = g.gyro.x;
  float gy = g.gyro.y;
  float gz = g.gyro.z;

  //////////////////////////////////
  // MADGWICK SENSOR FUSION
  //////////////////////////////////
  //
  // Fuse the REAL accelerometer and
  // gyroscope measurements.
  //

  filter.updateIMU(
    gx,
    gy,
    gz,
    ax,
    ay,
    az
  );

  //////////////////////////////////
  // GET MADGWICK QUATERNION
  //////////////////////////////////
  //
  // q0 = W
  // q1 = X
  // q2 = Y
  // q3 = Z
  //

  qw = filter.q0;
  qx = filter.q1;
  qy = filter.q2;
  qz = filter.q3;

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
  //
  // 0 = QX
  // 1 = QY
  // 2 = QZ
  // 3 = QW
  //
  // 4 = AX
  // 5 = AY
  // 6 = AZ
  //
  // 7 = GX
  // 8 = GY
  // 9 = GZ
  //////////////////////////////////

  OSCMessage msg(oscAddress);

  //////////////////////////////////
  // MADGWICK QUATERNION
  //////////////////////////////////

  msg.add(qx);
  msg.add(qy);
  msg.add(qz);
  msg.add(qw);

  //////////////////////////////////
  // ACTUAL ACCELEROMETER DATA
  //////////////////////////////////

  msg.add(ax);
  msg.add(ay);
  msg.add(az);

  //////////////////////////////////
  // ACTUAL GYROSCOPE DATA
  //////////////////////////////////

  msg.add(gx);
  msg.add(gy);
  msg.add(gz);

  //////////////////////////////////
  // SEND OSC
  //////////////////////////////////

  Udp.beginPacket(
    outIp,
    outPort
  );

  msg.send(Udp);

  Udp.endPacket();

  msg.empty();

  //////////////////////////////////
  // LOOP TIMING
  //////////////////////////////////

  delay(mseg_delay);
}
