# OSC Motion Router & Tracker

A real-time motion tracking, signal routing, and gesture recognition toolkit that bridges physical sensors with MIDI and OSC receivers.

## Overview & Purpose

This tool is designed to capture motion data from an ESP32 wearable/tracker and route it dynamically into music production software (DAWs), synthesizers, visualizers, or other creative applications. 

---

## How It Works

1. **Hardware (ESP32 Tracker)**: An ESP32 microcontroller with an IMU sensor (accelerometer/gyroscope) reads continuous movement data. It packages this raw data into Open Sound Control (OSC) messages and transmits them wirelessly over WiFi.
2. **Backend (OSC Motion Router)**: A Python-based FastAPI server acts as the central hub. It listens to the incoming OSC sensor stream, applies real-time filters and processors (gain, offset, smoothing, dead-zone, remapping), and routes the processed signals.
3. **Frontend (Web Dashboard)**: An interactive browser-based control panel allows you to monitor incoming signals in real-time, customize routing rules, select MIDI ports, and train custom gesture/trajectory templates.

---

## General Instructions

### 1. Hardware Setup
* Configure the ESP32 firmware with your local network settings and the target computer's IP address.
* Upload the firmware to the ESP32 and power it on.

### 2. Start the Router
* Ensure Python and the required dependencies are installed.
* Run the backend server application.
* Open the web interface in your browser (a window will open automatically, or navigate to the local address displayed in the terminal).

### 3. Signal Monitoring & Routing
* Select your connected MIDI port from the dropdown menu in the header.
* Confirm that the OSC receiver status shows "Running" and matches the port configured on your ESP32.
* Watch the live signal plots to verify that accelerometer and gyroscope data are transmitting.
* Add a **New Route** to direct a specific signal axis to a MIDI Channel/CC or an OSC Address. You can insert real-time modifiers like smoothing, dead-zone, or scaling.

### 4. Gesture & Trajectory Recognition
* Under the Gesture section, specify a label and select the channels you want to record.
* Perform the movement and trigger the template recording.
* Save the gesture and map it to a specific MIDI CC, MIDI Note, or OSC command.
* Start continuous recognition to detect trained movements in real time and trigger mapped signals.
