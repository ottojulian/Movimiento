# MVP — OSC Motion Router with Web UI and MIDI CC

## 1. Objective

Build a small local application that:

1. Receives OSC messages from one motion sensor.
2. Reads accelerometer and gyroscope values.
3. Shows the live values and plots in a browser.
4. Applies simple transformations to the signals.
5. Sends the result to another OSC address or as MIDI CC.
6. Saves the configuration in a JSON file so everything returns after refresh or restart.
7. Later adds simple trajectory recording and recognition.

This is an MVP. Do not add databases, user accounts, cloud services, frontend frameworks, plugin systems, Docker requirements, or complex visual editors.

---

## 2. Fixed technology choices

Use only this stack.

### Backend

- Python 3.11+
- FastAPI
- Uvicorn
- python-osc
- mido
- python-rtmidi
- NumPy

### Frontend

- One `index.html`
- One `app.js`
- One `style.css`
- Plain JavaScript
- Plain HTML
- Plain CSS
- HTML Canvas for plots

Do not use React, Vue, Svelte, TypeScript, Node.js, npm, a bundler, or a frontend build step.

### Persistence

Use one JSON file:

```text
data/config.json
```

Use one folder for recordings:

```text
data/recordings/
```

Do not use SQL or an ORM.

### Packaging

Use PyInstaller after the application works.

The packaged application should contain:

- Python runtime
- Python dependencies
- HTML, JavaScript, and CSS files
- Default configuration

The final user should not need Python or Node.js installed.

---

## 3. Basic architecture

```text
Sensor
  |
  | OSC UDP
  v
Python OSC receiver
  |
  v
Latest raw values in memory
  |
  +------------------+
  |                  |
  v                  v
Web UI plots      Signal routes
                     |
                     v
             Simple processors
                     |
            +--------+--------+
            |                 |
            v                 v
        OSC output        MIDI CC output
```

The Python application owns all state.

The browser is only a control and visualization interface.

The application must keep receiving and forwarding signals when the browser is closed.

---

## 4. Project structure

Use exactly this simple structure:

```text
osc-motion-router/
├── main.py
├── config.py
├── osc_io.py
├── midi_io.py
├── processing.py
├── trajectories.py
├── requirements.txt
├── web/
│   ├── index.html
│   ├── app.js
│   └── style.css
└── data/
    ├── config.json
    └── recordings/
```

Responsibilities:

### `main.py`

- Starts FastAPI.
- Starts and stops the OSC receiver.
- Serves the web files.
- Defines the HTTP API.
- Opens the browser on startup.
- Coordinates shutdown.

### `config.py`

- Loads `data/config.json`.
- Validates missing fields with defaults.
- Saves the JSON file atomically.
- Keeps one in-memory configuration object.

### `osc_io.py`

- Receives OSC.
- Stores the latest observed OSC messages.
- Extracts accelerometer and gyroscope values.
- Sends outgoing OSC messages.

### `midi_io.py`

- Lists MIDI output ports.
- Opens the selected MIDI port.
- Sends MIDI CC.
- Handles missing or disconnected ports.

### `processing.py`

- Contains simple signal processors.
- Runs configured routes.
- Converts raw values into cooked values.

### `trajectories.py`

- Records selected channels.
- Saves examples.
- Performs simple template comparison later.

---

## 5. Configuration file

Use a readable JSON file.

Example:

```json
{
  "web_port": 8765,
  "osc_input": {
    "enabled": true,
    "bind_ip": "0.0.0.0",
    "port": 9000,
    "accel_address": "/sensor/accel",
    "gyro_address": "/sensor/gyro",
    "format": "grouped",
    "accel_indexes": [0, 1, 2],
    "gyro_indexes": [0, 1, 2]
  },
  "osc_outputs": [
    {
      "id": "osc-out-1",
      "name": "Local OSC",
      "host": "127.0.0.1",
      "port": 9001
    }
  ],
  "midi": {
    "port_name": "",
    "channel": 1
  },
  "routes": []
}
```

Save the file whenever the user changes configuration.

Use a short debounce, for example 300 ms, so repeated UI edits do not write constantly.

Write atomically:

1. Save to `config.json.tmp`.
2. Replace `config.json`.

On startup:

1. Create `data/` if missing.
2. Create `data/recordings/` if missing.
3. Load `config.json`.
4. If missing, create it with defaults.

---

## 6. OSC input

Support one sensor.

The user must be able to configure:

- Bind IP.
- UDP port.
- Accelerometer OSC address.
- Gyroscope OSC address.
- Grouped or separated format.
- Argument indexes for X, Y, and Z.
- Start receiver.
- Stop receiver.

### Grouped format

Example:

```text
/sensor/accel 0.12 -0.03 0.98
/sensor/gyro 1.2 -4.8 0.5
```

Map them internally to:

```text
accel.x
accel.y
accel.z
gyro.x
gyro.y
gyro.z
```

### Separated format

Also support:

```text
/sensor/accel/x 0.12
/sensor/accel/y -0.03
/sensor/accel/z 0.98
```

For the first implementation, grouped format is the default.

---

## 7. OSC monitor

Add a simple OSC monitor in the UI.

Show the last messages received:

- Time.
- Source IP.
- OSC address.
- Arguments.
- Estimated messages per second.

Keep only the latest 100 messages in memory.

This monitor is also the learn mechanism.

### Learn OSC address

The user clicks:

```text
Learn accelerometer address
```

Then clicks one observed OSC message.

The selected address becomes the accelerometer address.

Repeat for gyroscope.

Do not try to automatically guess the meaning of OSC addresses.

---

## 8. Runtime signal state

Keep only the latest values in memory:

```python
latest_signals = {
    "accel.x": 0.0,
    "accel.y": 0.0,
    "accel.z": 0.0,
    "gyro.x": 0.0,
    "gyro.y": 0.0,
    "gyro.z": 0.0
}
```

Also keep:

```python
latest_timestamp
packet_count
packet_rate
last_error
```

Use a lock when the OSC receiver thread and FastAPI access the same state.

Do not create a complex event bus.

---

## 9. Web API

Use simple JSON HTTP endpoints.

### Status

```text
GET /api/status
```

Return:

- Server running.
- OSC receiver running.
- OSC input port.
- Last packet time.
- Packet rate.
- MIDI port state.
- Last error.

### Configuration

```text
GET /api/config
POST /api/config
```

`POST /api/config` replaces or updates the current configuration and saves it.

### Live values

```text
GET /api/live
```

Return the latest raw and cooked values.

The browser calls this endpoint every 50 ms.

This gives approximately 20 UI updates per second without WebSockets.

### OSC monitor

```text
GET /api/osc/messages
```

Return the latest observed OSC messages.

### OSC receiver control

```text
POST /api/osc/start
POST /api/osc/stop
```

### MIDI ports

```text
GET /api/midi/ports
```

### Test MIDI CC

```text
POST /api/midi/test
```

Body:

```json
{
  "port_name": "selected port",
  "channel": 1,
  "cc": 21,
  "value": 64
}
```

### Test OSC output

```text
POST /api/osc/test
```

---

## 10. Web UI

Use one page with sections.

Do not build routing between multiple pages.

### Section 1 — Server status

Show:

- OSC receiver running or stopped.
- Last packet time.
- Packet rate.
- MIDI status.
- Save status.
- Last error.

### Section 2 — OSC input

Controls:

- Bind IP.
- UDP port.
- Accelerometer address.
- Gyroscope address.
- Grouped or separated mode.
- Start.
- Stop.

### Section 3 — OSC monitor

Show a small table of recent messages.

Buttons:

- Use selected address as accelerometer.
- Use selected address as gyroscope.

### Section 4 — Live signals

Show six current values:

- Accel X.
- Accel Y.
- Accel Z.
- Gyro X.
- Gyro Y.
- Gyro Z.

Add two Canvas plots:

- Accelerometer plot with X, Y, Z.
- Gyroscope plot with X, Y, Z.

Keep the last 10 seconds of UI samples.

The plot does not need zooming, panning, or a chart library.

### Section 5 — Routes

Show a simple list of routes.

Each route has:

- Name.
- Source signal.
- Processor type.
- Processor parameters.
- Output type.
- Output parameters.
- Enabled checkbox.
- Delete button.

Button:

```text
Add route
```

### Section 6 — MIDI test

Controls:

- MIDI output port.
- MIDI channel.
- CC number.
- Value slider.
- Send test.

### Section 7 — Recording

Controls:

- Start recording.
- Stop recording.
- Recording name.
- Replay.
- Delete.

### Section 8 — Trajectories

This can be hidden or marked experimental until the core works.

---

## 11. Signal routes

A route takes one source and sends one result.

Example route:

```json
{
  "id": "route-1",
  "name": "Accel X to MIDI",
  "enabled": true,
  "source": "accel.x",
  "processors": [
    {
      "type": "smooth",
      "alpha": 0.2
    },
    {
      "type": "remap",
      "input_min": -2.0,
      "input_max": 2.0,
      "output_min": 0.0,
      "output_max": 127.0,
      "clamp": true
    }
  ],
  "output": {
    "type": "midi_cc",
    "port_name": "",
    "channel": 1,
    "cc": 21
  }
}
```

Process routes when new relevant OSC values arrive.

Do not make a node graph.

Do not support route branching explicitly. Users can create two routes with the same source.

---

## 12. Processors to implement

Implement only these processors.

### Gain

```text
output = input * gain
```

### Offset

```text
output = input + offset
```

### Remap

```text
input_min..input_max
to
output_min..output_max
```

Optional clamp.

### Invert

```text
output = -input
```

### Smooth

Exponential smoothing:

```text
smoothed = alpha * input + (1 - alpha) * previous
```

### Dead zone

If the value is near zero, return zero.

### Magnitude

Allow sources:

```text
accel.magnitude
gyro.magnitude
```

Calculate:

```text
sqrt(x*x + y*y + z*z)
```

### Threshold event

Generate an event when a value crosses a threshold.

Parameters:

- Threshold.
- Rising or falling.
- Cooldown in milliseconds.

Keep processor state inside the route runtime.

Reset state when the route changes.

---

## 13. OSC output

An OSC route output needs:

- Host.
- Port.
- OSC address.

Example:

```json
{
  "type": "osc",
  "host": "127.0.0.1",
  "port": 9001,
  "address": "/motion/accel_x"
}
```

Send one float.

For the MVP, do not support OSC bundles.

Add simple rate limiting:

- Default maximum: 100 messages per second per route.
- Option: send only if the value changed.

---

## 14. MIDI CC output

Use Mido with python-rtmidi.

A MIDI route needs:

- MIDI output port name.
- Channel 1–16.
- CC number 0–127.

Before sending:

```text
value = round(value)
value = clamp(value, 0, 127)
```

Send only if the integer value changed.

Do not send more than 100 MIDI messages per second per route.

If the MIDI port disappears:

- Keep the application running.
- Mark the route as error.
- Retry when the user selects the port again.

Do not implement MIDI notes in the MVP.

---

## 15. Recording

Record the six raw channels.

For the MVP, record UI-independent backend samples whenever OSC data arrives.

Store each recording as:

```text
data/recordings/<timestamp>_<name>.npz
```

Arrays:

```text
timestamps
accel_x
accel_y
accel_z
gyro_x
gyro_y
gyro_z
```

Keep recording metadata in:

```text
data/recordings/index.json
```

Do not add recording tables to the main config file.

### Replay

Replay a recording through the same `latest_signals` and route-processing code.

Modes:

- Real time.
- Stop.
- Loop optional.

When replay is active, clearly show it in the UI.

---

## 16. Trajectory MVP

Implement only after OSC input, plots, OSC output, MIDI CC, and persistence work.

### First use case

Recognize one manually recorded movement, such as a circular arm movement lasting 1–3 seconds.

### Workflow

1. Create a label.
2. Select channels.
3. Click Record Example.
4. Countdown for 3 seconds.
5. Record for a fixed duration.
6. Save the example.
7. Record at least five examples.
8. Click Activate Recognition.
9. Manually start a test capture.
10. Compare the test with saved examples.
11. Trigger an OSC message or a fixed MIDI CC value.

### Recognition method

Use the simplest method first:

1. Resample every example to 100 time points.
2. Normalize each selected channel by subtracting its mean.
3. Flatten the channels into one vector.
4. Compute Euclidean distance to every stored example.
5. Use the closest example.
6. Trigger only if distance is below a configurable threshold.

Do not implement continuous recognition, neural networks, HMMs, automatic segmentation, or cross-user validation in the MVP.

Keep the recognition code in `trajectories.py` so it can later be replaced with Dynamic Time Warping or another model.

---

## 17. Threading

Use a simple model:

- FastAPI and Uvicorn run normally.
- `python-osc` UDP server runs in one background thread.
- A lock protects shared live values.
- Route processing runs inside the OSC message callback.
- File recording writes buffered chunks, not one disk write per sample.

Do not create multiprocessing.

Do not create Celery workers.

Do not add Redis or queues unless real performance measurements require them.

---

## 18. Startup

When the user launches the program:

1. Create data folders.
2. Load `config.json`.
3. Start FastAPI.
4. Start OSC receiver if enabled.
5. Open the default browser at:

```text
http://127.0.0.1:<web_port>
```

Use Python's standard `webbrowser` module.

If the configured web port is busy, try the next available port and display it in the console.

---

## 19. Shutdown

On shutdown:

1. Stop OSC receiver.
2. Stop recording or replay.
3. Save configuration.
4. Close MIDI port.
5. Stop the web server.

The application should close cleanly after Ctrl+C or a UI shutdown button.

---

## 20. Cross-platform packaging

Only package after development mode works.

Use PyInstaller.

Create one build per operating system.

Do not attempt to cross-compile all systems from one machine.

Build on:

- Windows for Windows.
- macOS for macOS.
- Linux for Linux.

The executable must serve the included `web/` files.

Store writable files in a per-user data directory:

### Windows

```text
%APPDATA%/OscMotionRouter/
```

### macOS

```text
~/Library/Application Support/OscMotionRouter/
```

### Linux

```text
~/.local/share/osc-motion-router/
```

During development, local `data/` is acceptable.

---

## 21. Requirements file

Start with:

```text
fastapi
uvicorn
python-osc
mido
python-rtmidi
numpy
```

Add PyInstaller only to the development packaging requirements.

Do not add SciPy unless a processor genuinely requires it.

---

## 22. Development order

### Step 1

Create FastAPI server and serve `index.html`.

### Step 2

Create JSON configuration load and save.

### Step 3

Receive arbitrary OSC messages and show them in the OSC monitor.

### Step 4

Map accelerometer and gyroscope addresses.

### Step 5

Show six live values and two Canvas plots.

### Step 6

Add route model and basic processors.

### Step 7

Add OSC output.

### Step 8

Add MIDI port listing, test CC, and MIDI routes.

### Step 9

Add recording and replay.

### Step 10

Add the simple trajectory experiment.

### Step 11

Package separately on Windows, macOS, and Linux.

Do not start the next step until the current end-to-end behavior works.

---

## 23. Core MVP acceptance test

The MVP core is ready when a non-developer can:

1. Launch the application.
2. See the browser UI.
3. Change the incoming OSC port.
4. See arbitrary OSC messages arriving.
5. Select the accelerometer and gyroscope OSC addresses.
6. See the six live channels.
7. See accelerometer and gyroscope plots.
8. Create a route from `accel.x`.
9. Smooth and remap it.
10. Send it to a new OSC address.
11. Send it as MIDI CC.
12. Refresh the browser without losing configuration.
13. Restart the program without losing configuration.
14. Record and replay a session.

Trajectory recognition is the next feature after this core test passes.

---

## 24. Information needed from the real sensor

Development should start with a synthetic OSC sender.

To integrate the physical sensor, provide:

- Actual accelerometer OSC address.
- Actual gyroscope OSC address.
- Example messages.
- Whether values are grouped or separated.
- Accelerometer units.
- Gyroscope units.
- Approximate message rate.
- Typical sensor orientation.

No other design decision is required before starting the MVP.
