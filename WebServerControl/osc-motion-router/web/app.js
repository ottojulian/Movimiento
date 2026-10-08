// State Variables
let currentConfig = {
    web_port: 8765,
    osc_input: {
        enabled: true,
        bind_ip: "0.0.0.0",
        port: 9000,
        accel_address: "/sensor/accel",
        gyro_address: "/sensor/gyro",
        format: "grouped"
    },
    osc_outputs: [],
    midi: {
        port_name: "",
        channel: 1
    },
    routes: [],
    trajectory: {
        recognition_threshold: 15.0,
        deviation_threshold: 0.035,
        recognition_hold: 1.0,
        action: {
            type: "osc",
            host: "127.0.0.1",
            port: 9001,
            address: "/motion/recognized"
        }
    }
};

// Buffers for Canvas Plot (last 10 seconds at 50ms intervals = 200 samples)
const PLOT_BUFFER_SIZE = 200;
const accelBuffer = { x: new Array(PLOT_BUFFER_SIZE).fill(0), y: new Array(PLOT_BUFFER_SIZE).fill(0), z: new Array(PLOT_BUFFER_SIZE).fill(0) };
const gyroBuffer = { x: new Array(PLOT_BUFFER_SIZE).fill(0), y: new Array(PLOT_BUFFER_SIZE).fill(0), z: new Array(PLOT_BUFFER_SIZE).fill(0) };

// Selected OSC Address from monitor for learn mode
let selectedOSCMonitorAddress = null;

// Temporary list of processors for the route being edited
let editingRouteId = null; // null for new, string for edit
let currentRouteProcessors = [];

// DOM Elements
const el = {
    oscStatusIndicator: document.getElementById('osc-status-indicator'),
    oscStatusText: document.getElementById('osc-status-text'),
    midiStatusIndicator: document.getElementById('midi-status-indicator'),
    midiStatusText: document.getElementById('midi-status-text'),
    globalRateText: document.getElementById('global-rate-text'),
    errorBanner: document.getElementById('error-banner'),
    
    // OSC Inputs
    oscBindIp: document.getElementById('osc-bind-ip'),
    oscPort: document.getElementById('osc-port'),
    oscAccelAddress: document.getElementById('osc-accel-address'),
    oscGyroAddress: document.getElementById('osc-gyro-address'),
    oscFormat: document.getElementById('osc-format'),
    oscAccelIndexes: document.getElementById('osc-accel-indexes'),
    oscGyroIndexes: document.getElementById('osc-gyro-indexes'),
    groupedIndexesRow: document.getElementById('grouped-indexes-row'),
    btnStartOsc: document.getElementById('btn-start-osc'),
    btnStopOsc: document.getElementById('btn-stop-osc'),
    
    // OSC Monitor
    oscMonitorBody: document.getElementById('osc-monitor-body'),
    oscLearnPanel: document.getElementById('osc-learn-panel'),
    learnedAddressDisplay: document.getElementById('learned-address-display'),
    btnLearnAccel: document.getElementById('btn-learn-accel'),
    btnLearnGyro: document.getElementById('btn-learn-gyro'),
    
    // Live signals numerical
    valAccelX: document.getElementById('val-accel-x'),
    valAccelY: document.getElementById('val-accel-y'),
    valAccelZ: document.getElementById('val-accel-z'),
    valGyroX: document.getElementById('val-gyro-x'),
    valGyroY: document.getElementById('val-gyro-y'),
    valGyroZ: document.getElementById('val-gyro-z'),
    
    // Canvas
    accelPlot: document.getElementById('accel-plot'),
    gyroPlot: document.getElementById('gyro-plot'),
    miniAccelPlot: document.getElementById('mini-accel-plot'),
    miniGyroPlot: document.getElementById('mini-gyro-plot'),
    
    // Routes list and editor
    routesContainer: document.getElementById('routes-container'),
    btnNewRoute: document.getElementById('btn-new-route'),
    routeEditor: document.getElementById('route-editor'),
    editorTitle: document.getElementById('editor-title'),
    routeName: document.getElementById('route-name'),
    routeSource: document.getElementById('route-source'),
    btnAddProcessor: document.getElementById('btn-add-processor'),
    processorsListEditor: document.getElementById('processors-list-editor'),
    routeOutType: document.getElementById('route-out-type'),
    outGroupMidi: document.getElementById('out-group-midi'),
    outGroupOsc: document.getElementById('out-group-osc'),
    routeMidiChan: document.getElementById('route-midi-chan'),
    routeMidiCc: document.getElementById('route-midi-cc'),
    routeOscHost: document.getElementById('route-osc-host'),
    routeOscPort: document.getElementById('route-osc-port'),
    routeOscAddr: document.getElementById('route-osc-addr'),
    btnCancelRoute: document.getElementById('btn-cancel-route'),
    btnSaveRoute: document.getElementById('btn-save-route'),
    
    // MIDI Test
    midiGlobalPort: document.getElementById('midi-global-port'),
    midiGlobalChannel: document.getElementById('midi-global-channel'),
    midiTestCc: document.getElementById('midi-test-cc'),
    midiTestValue: document.getElementById('midi-test-value'),
    midiTestValueDisplay: document.getElementById('midi-test-value-display'),
    btnSendMidiTest: document.getElementById('btn-send-midi-test'),
    
    // OSC Test
    oscTestPort: document.getElementById('osc-test-port'),
    oscTestAddress: document.getElementById('osc-test-address'),
    oscTestValue: document.getElementById('osc-test-value'),
    btnSendOscTest: document.getElementById('btn-send-osc-test'),
    
    // Trajectories
    trajLabel: document.getElementById('traj-label'),
    trajMidiChan: document.getElementById('traj-midi-chan'),
    trajMidiCc: document.getElementById('traj-midi-cc'),
    btnTrajRecordStart: document.getElementById('btn-traj-record-start'),
    btnTrajRecordStop: document.getElementById('btn-traj-record-stop'),
    btnTrajDiscardLast: document.getElementById('btn-traj-discard-last'),
    btnTrajRecognizeStart: document.getElementById('btn-traj-recognize-start'),
    btnTrajRecognizeStop: document.getElementById('btn-traj-recognize-stop'),
    trajProgressCard: document.getElementById('traj-progress-card'),
    trajProgressText: document.getElementById('traj-progress-text'),
    trajectoryExamplesList: document.getElementById('trajectory-examples-list'),
    recognitionMatchContainer: document.getElementById('recognition-match-container'),
    recognitionMatchLabel: document.getElementById('recognition-match-label'),
    recognitionMatchDist: document.getElementById('recognition-match-dist'),
    btnSetIdlePos: document.getElementById('btn-set-idle-pos'),
    trajThreshold: document.getElementById('traj-threshold'),
    trajDeviationThreshold: document.getElementById('traj-deviation-threshold'),
    trajRecognitionHold: document.getElementById('traj-recognition-hold'),
    trajActionType: document.getElementById('traj-action-type'),
    trajActionOscGroup: document.getElementById('traj-action-osc-group'),
    trajActionOscHost: document.getElementById('traj-action-osc-host'),
    trajActionOscPort: document.getElementById('traj-action-osc-port'),
    trajActionOscAddr: document.getElementById('traj-action-osc-addr'),
    
    // Session Export/Import Controls
    sessionFilename: document.getElementById('session-filename'),
    btnExportSession: document.getElementById('btn-export-session'),
    importFileInput: document.getElementById('import-file-input')
};

// Debounce state for saves
let saveConfigTimeout = null;

// --- INITIALIZATION ---
window.addEventListener('DOMContentLoaded', async () => {
    setupCanvasDPI(el.accelPlot);
    setupCanvasDPI(el.gyroPlot);
    setupCanvasDPI(el.miniAccelPlot);
    setupCanvasDPI(el.miniGyroPlot);
    
    await loadInitialData();
    
    // Start polling live states (50ms interval)
    setInterval(pollLiveState, 50);
    
    // Poll slower streams (500ms interval)
    setInterval(pollSlowStreams, 500);
    
    setupEventListeners();
});

// Setup Canvas for High DPI screens
function setupCanvasDPI(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
}

async function loadInitialData() {
    try {
        // 1. Fetch config from server
        const resConfig = await fetch('/api/config?_t=' + Date.now(), { cache: 'no-store' });
        const serverConfig = await resConfig.json();
        
        // 2. Browser Persistence Sync: Restore unsaved local values if they exist
        const localSaved = localStorage.getItem('osc_motion_router_persisted_config');
        if (localSaved) {
            try {
                const parsedLocal = JSON.parse(localSaved);
                // Merge local persistent adjustments with server config structure to prevent gaps
                currentConfig = { ...serverConfig, ...parsedLocal };
                console.log("Restored un-saved transient variables from Browser local storage.");
            } catch (e) {
                currentConfig = serverConfig;
            }
        } else {
            currentConfig = serverConfig;
        }

        populateUIFromConfig();
        
        // Push restored configs back to server to synchronize active router state
        await pushConfigToServer(currentConfig);
        
        // 3. Fetch MIDI ports
        await refreshMidiPorts();
        
        // 4. Load saved trajectory examples
        await refreshTrajectoriesList();
    } catch (err) {
        showError("Failed to communicate with server on startup: " + err.message);
    }
}

async function pushConfigToServer(configData) {
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        const out = await res.json();
        currentConfig = out.config;
        showError(null);
    } catch (err) {
        showError("Failed to synchronize configuration with server: " + err.message);
    }
}

function showError(msg) {
    if (msg) {
        el.errorBanner.textContent = msg;
        el.errorBanner.style.display = 'block';
    } else {
        el.errorBanner.style.display = 'none';
    }
}

// --- POPULATE AND GATHER FORM DATA ---

function populateUIFromConfig() {
    el.oscBindIp.value = currentConfig.osc_input.bind_ip;
    el.oscPort.value = currentConfig.osc_input.port;
    el.oscAccelAddress.value = currentConfig.osc_input.accel_address;
    el.oscGyroAddress.value = currentConfig.osc_input.gyro_address;
    el.oscFormat.value = currentConfig.osc_input.format;
    
    // Add indices mapping
    el.oscAccelIndexes.value = (currentConfig.osc_input.accel_indexes || [0, 1, 2]).join(", ");
    el.oscGyroIndexes.value = (currentConfig.osc_input.gyro_indexes || [3, 4, 5]).join(", ");
    
    if (currentConfig.osc_input.format === "grouped") {
        el.groupedIndexesRow.style.display = 'grid';
    } else {
        el.groupedIndexesRow.style.display = 'none';
    }
    
    el.midiGlobalChannel.value = currentConfig.midi.channel;
    
    // Trajectory
    if (!currentConfig.trajectory) {
        currentConfig.trajectory = {
            recognition_threshold: 15.0,
            action: { type: "osc", host: "127.0.0.1", port: 9001, address: "/motion/recognized" }
        };
    }
    el.trajThreshold.value = currentConfig.trajectory.recognition_threshold || 15.0;
    el.trajDeviationThreshold.value = currentConfig.trajectory.deviation_threshold ?? 0.035;
    el.trajRecognitionHold.value = currentConfig.trajectory.recognition_hold ?? 1.0;
    const action = currentConfig.trajectory.action || { type: "osc" };
    el.trajActionType.value = action.type || "osc";
    
    if (action.type === "midi") {
        el.trajActionOscGroup.style.display = 'none';
    } else {
        el.trajActionOscGroup.style.display = 'grid';
        el.trajActionOscHost.value = action.host || "127.0.0.1";
        el.trajActionOscPort.value = action.port || 9001;
        el.trajActionOscAddr.value = action.address || "/motion/recognized";
    }

    renderRoutesList();
}

function gatherConfigFromUI() {
    // Collect settings from UI and merge into currentConfig
    currentConfig.osc_input.bind_ip = el.oscBindIp.value;
    currentConfig.osc_input.port = parseInt(el.oscPort.value) || 9000;
    currentConfig.osc_input.accel_address = el.oscAccelAddress.value;
    currentConfig.osc_input.gyro_address = el.oscGyroAddress.value;
    currentConfig.osc_input.format = el.oscFormat.value;
    
    // Parse indices mapping
    currentConfig.osc_input.accel_indexes = el.oscAccelIndexes.value.split(",").map(x => parseInt(x.trim()) || 0);
    currentConfig.osc_input.gyro_indexes = el.oscGyroIndexes.value.split(",").map(x => parseInt(x.trim()) || 0);
    
    currentConfig.midi.port_name = el.midiGlobalPort.value;
    currentConfig.midi.channel = parseInt(el.midiGlobalChannel.value) || 1;
    
    // Trajectory config
    currentConfig.trajectory.recognition_threshold = parseFloat(el.trajThreshold.value) || 15.0;
    currentConfig.trajectory.deviation_threshold = parseFloat(el.trajDeviationThreshold.value) ?? 0.035;
    currentConfig.trajectory.recognition_hold = parseFloat(el.trajRecognitionHold.value) ?? 1.0;
    
    const trajType = el.trajActionType.value;
    currentConfig.trajectory.action.type = trajType;
    if (trajType === "midi") {
        currentConfig.trajectory.action.port_name = el.midiGlobalPort.value;
        // Keep placeholder defaults for osc
        currentConfig.trajectory.action.host = currentConfig.trajectory.action.host || "127.0.0.1";
    } else {
        currentConfig.trajectory.action.host = el.trajActionOscHost.value;
        currentConfig.trajectory.action.port = parseInt(el.trajActionOscPort.value) || 9001;
        currentConfig.trajectory.action.address = el.trajActionOscAddr.value;
    }
}

async function saveConfigImmediate() {
    gatherConfigFromUI();
    
    // Save to LocalStorage instantly for complete offline/crash browser robustness
    localStorage.setItem('osc_motion_router_persisted_config', JSON.stringify(currentConfig));

    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentConfig)
        });
        const out = await res.json();
        currentConfig = out.config;
        showError(null);
    } catch (err) {
        showError("Failed to save configuration: " + err.message);
    }
}

function saveConfigDebounced() {
    if (saveConfigTimeout) clearTimeout(saveConfigTimeout);
    saveConfigTimeout = setTimeout(saveConfigImmediate, 300);
}

// --- POLLING LOOPS ---

async function pollLiveState() {
    try {
        const res = await fetch('/api/live?_t=' + Date.now(), { cache: 'no-store' });
        const data = await res.json();
        
        // 1. Update numerical labels
        el.valAccelX.textContent = data.raw["accel.x"].toFixed(3);
        el.valAccelY.textContent = data.raw["accel.y"].toFixed(3);
        el.valAccelZ.textContent = data.raw["accel.z"].toFixed(3);
        el.valGyroX.textContent = data.raw["gyro.x"].toFixed(3);
        el.valGyroY.textContent = data.raw["gyro.y"].toFixed(3);
        el.valGyroZ.textContent = data.raw["gyro.z"].toFixed(3);
        
        // 2. Feed plot buffers
        pushToPlotBuffer(accelBuffer, data.raw["accel.x"], data.raw["accel.y"], data.raw["accel.z"]);
        pushToPlotBuffer(gyroBuffer, data.raw["gyro.x"], data.raw["gyro.y"], data.raw["gyro.z"]);
        
        // 3. Render plots
        renderCanvasPlot(el.accelPlot, accelBuffer, ["#ff453a", "#30d158", "#0a84ff"], "G");
        renderCanvasPlot(el.gyroPlot, gyroBuffer, ["#ffd60a", "#bf5af2", "#ff9f0a"], "rad/s");
        renderCanvasPlot(el.miniAccelPlot, accelBuffer, ["#ff453a", "#30d158", "#0a84ff"], "G", false);
        renderCanvasPlot(el.miniGyroPlot, gyroBuffer, ["#ffd60a", "#bf5af2", "#ff9f0a"], "rad/s", false);
        
        // 4. Update status rates and indicators
        el.globalRateText.textContent = data.packet_rate;
    } catch (err) {
        // Don't show modal errors for frequent fast polling, but show status
        el.globalRateText.textContent = "--";
    }
}

async function pollSlowStreams() {
    try {
        // 1. Poll Status
        const resStatus = await fetch('/api/status?_t=' + Date.now(), { cache: 'no-store' });
        const status = await resStatus.json();
        
        // OSC Server indicator
        if (status.osc_receiver_running) {
            el.oscStatusIndicator.className = "indicator running";
            el.oscStatusText.textContent = `Running on port ${status.osc_port}`;
            el.btnStartOsc.style.display = 'none';
            el.btnStopOsc.style.display = 'inline-flex';
        } else {
            el.oscStatusIndicator.className = "indicator stopped";
            el.oscStatusText.textContent = "Stopped";
            el.btnStartOsc.style.display = 'inline-flex';
            el.btnStopOsc.style.display = 'none';
        }
        
        // MIDI status indicator
        if (status.midi_active) {
            el.midiStatusIndicator.className = "indicator running";
            el.midiStatusText.textContent = status.midi_port;
        } else {
            el.midiStatusIndicator.className = "indicator stopped";
            el.midiStatusText.textContent = status.midi_port ? `${status.midi_port} (Closed)` : "None selected";
        }
        
        // Show last error if any
        if (status.last_error) {
            showError(status.last_error);
        } else {
            showError(null);
        }

        // 2. Poll OSC messages
        await refreshOSCMonitor();

        // 3. Poll Trajectory status
        updateTrajectoryStatusUI(status.recording);
    } catch (err) {
        console.error("Error in slow polling loop:", err);
        showError("Disconnected from server. Trying to reconnect...");
        el.oscStatusIndicator.className = "indicator stopped";
        el.oscStatusText.textContent = "Offline";
        el.midiStatusIndicator.className = "indicator stopped";
        el.midiStatusText.textContent = "Offline";
    }
}

function updateTrajectoryStatusUI(recStatus) {
    if (recStatus.test_capture_active && recStatus.is_recording_example) {
        el.trajProgressCard.style.display = 'block';
        el.trajProgressText.innerHTML = `<span class="text-success">RECORDING TEMPLATE ACTIVE NOW - CLICK STOP & SAVE TO FINISH</span>`;
        el.btnTrajRecordStart.style.display = 'none';
        el.btnTrajRecordStop.style.display = 'inline-flex';
        
        el.btnTrajRecognizeStart.style.display = 'inline-flex';
        el.btnTrajRecognizeStop.style.display = 'none';
    } else if (recStatus.recognition_active) {
        el.trajProgressCard.style.display = 'block';
        el.trajProgressText.innerHTML = `<span class="text-success">CONTINUOUS RECOGNITION ACTIVE</span>`;
        el.btnTrajRecordStart.style.display = 'inline-flex';
        el.btnTrajRecordStop.style.display = 'none';
        
        el.btnTrajRecognizeStart.style.display = 'none';
        el.btnTrajRecognizeStop.style.display = 'inline-flex';
    } else {
        el.trajProgressCard.style.display = 'none';
        el.btnTrajRecordStart.style.display = 'inline-flex';
        el.btnTrajRecordStop.style.display = 'none';
        el.btnTrajRecognizeStart.style.display = 'inline-flex';
        el.btnTrajRecognizeStop.style.display = 'none';
    }

    if (recStatus.recognition_result) {
        el.recognitionMatchLabel.textContent = recStatus.recognition_result;
        
        if (recStatus.recognition_triggered) {
            el.recognitionMatchLabel.style.color = '#000000';
            el.recognitionMatchDist.style.color = '#333333';
            el.recognitionMatchContainer.style.backgroundColor = '#ffd60a'; // bright yellow
        } else {
            el.recognitionMatchLabel.style.color = 'var(--warning)';
            el.recognitionMatchDist.style.color = 'var(--text-muted)';
            el.recognitionMatchContainer.style.backgroundColor = '#0b0b0c';
        }
        
        el.recognitionMatchDist.textContent = `Distance: ${recStatus.recognition_distance.toFixed(2)}`;
    } else {
        el.recognitionMatchLabel.textContent = "No gesture matched";
        el.recognitionMatchLabel.style.color = 'var(--text-muted)';
        el.recognitionMatchDist.textContent = "Distance: --";
        el.recognitionMatchDist.style.color = 'var(--text-muted)';
        el.recognitionMatchContainer.style.backgroundColor = '#0b0b0c';
    }
}

// --- PLOT AND CANVAS RENDERER ---

function pushToPlotBuffer(buffer, x, y, z) {
    buffer.x.push(x);
    buffer.y.push(y);
    buffer.z.push(z);
    
    if (buffer.x.length > PLOT_BUFFER_SIZE) {
        buffer.x.shift();
        buffer.y.shift();
        buffer.z.shift();
    }
}

function renderCanvasPlot(canvas, buffer, colors, unit, showLabels = true) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width / (window.devicePixelRatio || 1);
    const height = canvas.height / (window.devicePixelRatio || 1);
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Find min and max for scaling
    let allValues = [...buffer.x, ...buffer.y, ...buffer.z];
    let max = Math.max(...allValues);
    let min = Math.min(...allValues);
    
    // Keep a reasonable minimum range so it doesn't bounce around on noise
    if (max - min < 0.2) {
        const center = (max + min) / 2;
        max = center + 0.1;
        min = center - 0.1;
    }
    
    // Add 10% padding
    const range = max - min;
    max += range * 0.05;
    min -= range * 0.05;
    
    // Draw Grid Lines
    ctx.strokeStyle = '#1d1d24';
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
        const yLine = (height / 4) * i;
        ctx.beginPath();
        ctx.moveTo(0, yLine);
        ctx.lineTo(width, yLine);
        ctx.stroke();
    }
    
    // Draw Center Zero line if it lies within the range
    if (min <= 0 && max >= 0) {
        const zeroY = height - ((0 - min) / (max - min)) * height;
        ctx.strokeStyle = '#3e3e4f';
        ctx.beginPath();
        ctx.moveTo(0, zeroY);
        ctx.lineTo(width, zeroY);
        ctx.stroke();
    }
    
    // Plot the three lines
    const axes = ['x', 'y', 'z'];
    axes.forEach((axis, colorIdx) => {
        const arr = buffer[axis];
        ctx.strokeStyle = colors[colorIdx];
        ctx.lineWidth = showLabels ? 1.5 : 1.0;
        ctx.beginPath();
        
        for (let i = 0; i < arr.length; i++) {
            const val = arr[i];
            const xPos = (width / (PLOT_BUFFER_SIZE - 1)) * i;
            const yPos = height - ((val - min) / (max - min)) * height;
            
            if (i === 0) {
                ctx.moveTo(xPos, yPos);
            } else {
                ctx.lineTo(xPos, yPos);
            }
        }
        ctx.stroke();
    });
    
    // Draw Text Labels for Limits
    if (showLabels) {
        ctx.fillStyle = '#8e8e9a';
        ctx.font = '10px monospace';
        ctx.fillText(`${max.toFixed(2)} ${unit}`, 5, 12);
        ctx.fillText(`${min.toFixed(2)} ${unit}`, 5, height - 5);
    }
}

// --- OSC MONITOR & LEARN ---

async function refreshOSCMonitor() {
    try {
        const res = await fetch('/api/osc/messages?_t=' + Date.now(), { cache: 'no-store' });
        const msgs = await res.json();
        
        if (msgs.length === 0) {
            el.oscMonitorBody.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align: center; color: var(--text-muted); font-style: italic; padding: 1rem;">No messages observed yet. Ensure server is started.</td>
                </tr>`;
            return;
        }
        
        let html = '';
        msgs.reverse().forEach((msg, idx) => {
            const isSelected = selectedOSCMonitorAddress === msg.address;
            html += `
                <tr class="${isSelected ? 'selected' : ''}" onclick="selectOSCMonitorRow(this, '${msg.address}')">
                    <td>${msg.time}</td>
                    <td style="font-family: monospace; font-weight: 600; color: var(--accent);">${msg.address}</td>
                    <td style="font-family: monospace;">[${msg.args.map(a => typeof a === 'number' ? a.toFixed(2) : a).join(', ')}]</td>
                </tr>`;
        });
        el.oscMonitorBody.innerHTML = html;
    } catch (err) {
        console.error("Error updating OSC Monitor table:", err);
    }
}

function selectOSCMonitorRow(row, address) {
    // Clear existing selections
    const rows = el.oscMonitorBody.getElementsByTagName('tr');
    for (let r of rows) {
        r.classList.remove('selected');
    }
    
    row.classList.add('selected');
    selectedOSCMonitorAddress = address;
    el.learnedAddressDisplay.textContent = address;
    el.oscLearnPanel.style.display = 'block';
}

// --- ROUTES LIST & EDITOR ---

function renderRoutesList() {
    if (currentConfig.routes.length === 0) {
        el.routesContainer.innerHTML = `
            <div style="text-align: center; color: var(--text-muted); font-style: italic; padding: 2rem; background-color: #242429; border-radius: 8px; border: 1px dashed var(--border);">
                No routes configured. Click '+ Add New Route' to start routing sensor signals.
            </div>`;
        return;
    }
    
    let html = '';
    currentConfig.routes.forEach((route, idx) => {
        const isEnabled = route.enabled !== false;
        
        // Format processor labels
        let procHtml = '';
        if (route.processors && route.processors.length > 0) {
            route.processors.forEach(p => {
                let params = '';
                if (p.type === 'smooth') params = `α=${p.alpha}`;
                else if (p.type === 'gain') params = `g=${p.gain}`;
                else if (p.type === 'offset') params = `offset=${p.offset}`;
                else if (p.type === 'dead_zone') params = `th=${p.threshold}`;
                else if (p.type === 'remap') params = `[${p.input_min},${p.input_max}]➔[${p.output_min},${p.output_max}]`;
                else if (p.type === 'threshold_event') params = `th=${p.threshold}, ${p.direction}`;
                
                procHtml += `<span class="processor-badge">⚡ ${p.type} (${params})</span>`;
            });
        } else {
            procHtml = '<span style="color: var(--text-muted); font-style: italic;">Direct Connection</span>';
        }
        
        // Format output labels
        let outputLabel = '';
        if (route.output.type === 'midi_cc') {
            outputLabel = `🎵 MIDI Channel ${route.output.channel}, CC ${route.output.cc}`;
            if (route.output.port_name) outputLabel += ` on '${route.output.port_name}'`;
        } else {
            outputLabel = `🌐 OSC sending to ${route.output.host}:${route.output.port} ${route.output.address}`;
        }
        
        html += `
            <div class="route-item" style="border-left: 4px solid ${isEnabled ? 'var(--accent)' : 'var(--border)'}; opacity: ${isEnabled ? 1 : 0.65}">
                <div class="route-header">
                    <div class="route-title">
                        <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="toggleRouteEnabled('${route.id}', this.checked)" style="cursor: pointer;">
                        <span>${route.name || `Route ${idx + 1}`}</span>
                    </div>
                    <span style="font-size: 0.75rem; font-family: monospace; color: var(--text-muted); background-color: #1a1a1e; padding: 0.125rem 0.375rem; border-radius: 4px;">
                        Source: ${route.source}
                    </span>
                </div>
                <div class="route-body">
                    <div><span style="color: var(--text-muted);">Processors:</span> ${procHtml}</div>
                    <div><span style="color: var(--text-muted);">Destination:</span> <strong style="color: var(--accent);">${outputLabel}</strong></div>
                </div>
                <div class="route-actions">
                    <button class="btn btn-sm" onclick="editRoute('${route.id}')" style="margin-right: 0.5rem;">Edit</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteRoute('${route.id}')">Delete</button>
                </div>
            </div>`;
    });
    el.routesContainer.innerHTML = html;
}

function showRouteEditor(show) {
    if (show) {
        el.routeEditor.style.display = 'block';
        el.btnNewRoute.style.display = 'none';
        // Scroll editor into view
        el.routeEditor.scrollIntoView({ behavior: 'smooth' });
    } else {
        el.routeEditor.style.display = 'none';
        el.btnNewRoute.style.display = 'inline-flex';
        editingRouteId = null;
    }
}

// Processor editor items renderer
function renderProcessorsListEditor() {
    if (currentRouteProcessors.length === 0) {
        el.processorsListEditor.innerHTML = `
            <div style="text-align: center; font-size: 0.8rem; color: var(--text-muted); padding: 1rem; border: 1px dashed var(--border); border-radius: 6px;">
                No processors in chain. Signal will route directly.
            </div>`;
        return;
    }
    
    let html = '';
    currentRouteProcessors.forEach((p, idx) => {
        html += `
            <div style="background-color: #1a1a1e; border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; position: relative;">
                <button type="button" class="btn btn-sm btn-danger" onclick="removeProcessor(${idx})" style="position: absolute; top: 0.5rem; right: 0.5rem; padding: 0.125rem 0.375rem; font-size: 0.7rem;">✕</button>
                <div class="form-row" style="grid-template-columns: 1fr 2fr; margin-bottom: 0;">
                    <div class="form-group" style="margin-bottom: 0;">
                        <label>Processor Type</label>
                        <select onchange="changeProcessorType(${idx}, this.value)">
                            <option value="gain" ${p.type === 'gain' ? 'selected' : ''}>Gain (Multiply)</option>
                            <option value="offset" ${p.type === 'offset' ? 'selected' : ''}>Offset (Add)</option>
                            <option value="remap" ${p.type === 'remap' ? 'selected' : ''}>Remap Scale</option>
                            <option value="invert" ${p.type === 'invert' ? 'selected' : ''}>Invert (Negate)</option>
                            <option value="smooth" ${p.type === 'smooth' ? 'selected' : ''}>Smooth Filter</option>
                            <option value="dead_zone" ${p.type === 'dead_zone' ? 'selected' : ''}>Dead Zone</option>
                            <option value="threshold_event" ${p.type === 'threshold_event' ? 'selected' : ''}>Threshold Event</option>
                        </select>
                    </div>
                    <div id="processor-params-${idx}" class="form-row" style="margin-bottom: 0; align-items: flex-end;">
                        ${renderProcessorParams(p, idx)}
                    </div>
                </div>
            </div>`;
    });
    el.processorsListEditor.innerHTML = html;
}

function renderProcessorParams(p, idx) {
    if (p.type === 'gain') {
        return `
            <div class="form-group" style="margin-bottom: 0;">
                <label>Gain Coeff</label>
                <input type="number" step="0.01" value="${p.gain ?? 1.0}" onchange="updateProcessorParam(${idx}, 'gain', parseFloat(this.value))">
            </div>`;
    } else if (p.type === 'offset') {
        return `
            <div class="form-group" style="margin-bottom: 0;">
                <label>Offset Offset</label>
                <input type="number" step="0.01" value="${p.offset ?? 0.0}" onchange="updateProcessorParam(${idx}, 'offset', parseFloat(this.value))">
            </div>`;
    } else if (p.type === 'invert') {
        return `<span style="font-size: 0.75rem; color: var(--text-muted); align-self: center;">No parameters. Outputs -value.</span>`;
    } else if (p.type === 'smooth') {
        return `
            <div class="form-group" style="margin-bottom: 0;">
                <label>Smooth Weight (Alpha: 0 to 1)</label>
                <input type="number" step="0.05" min="0" max="1" value="${p.alpha ?? 0.2}" onchange="updateProcessorParam(${idx}, 'alpha', parseFloat(this.value))">
            </div>`;
    } else if (p.type === 'dead_zone') {
        return `
            <div class="form-group" style="margin-bottom: 0;">
                <label>Threshold Width</label>
                <input type="number" step="0.01" min="0" value="${p.threshold ?? 0.1}" onchange="updateProcessorParam(${idx}, 'threshold', parseFloat(this.value))">
            </div>`;
    } else if (p.type === 'remap') {
        return `
            <div class="form-row-3" style="grid-template-columns: repeat(5, 1fr); gap: 0.15rem; width: 100%;">
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">In Min</label>
                    <input type="number" step="0.1" value="${p.input_min ?? 0.0}" onchange="updateProcessorParam(${idx}, 'input_min', parseFloat(this.value))" style="padding: 0.25rem 0.15rem; font-size: 0.75rem; text-align: center;">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">In Max</label>
                    <input type="number" step="0.1" value="${p.input_max ?? 1.0}" onchange="updateProcessorParam(${idx}, 'input_max', parseFloat(this.value))" style="padding: 0.25rem 0.15rem; font-size: 0.75rem; text-align: center;">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">Out Min</label>
                    <input type="number" step="0.1" value="${p.output_min ?? 0.0}" onchange="updateProcessorParam(${idx}, 'output_min', parseFloat(this.value))" style="padding: 0.25rem 0.15rem; font-size: 0.75rem; text-align: center;">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">Out Max</label>
                    <input type="number" step="0.1" value="${p.output_max ?? 127.0}" onchange="updateProcessorParam(${idx}, 'output_max', parseFloat(this.value))" style="padding: 0.25rem 0.15rem; font-size: 0.75rem; text-align: center;">
                </div>
                <div class="form-group" style="margin-bottom: 0; display: flex; flex-direction: column; align-items: center; justify-content: flex-end;">
                    <label style="font-size: 0.65rem; margin-bottom: 0.5rem;">Clamp</label>
                    <input type="checkbox" ${p.clamp !== false ? 'checked' : ''} onchange="updateProcessorParam(${idx}, 'clamp', this.checked)">
                </div>
            </div>`;
    } else if (p.type === 'threshold_event') {
        return `
            <div class="form-row-3" style="grid-template-columns: 2fr 2fr 2fr; gap: 0.35rem; width: 100%;">
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">Thresh</label>
                    <input type="number" step="0.05" value="${p.threshold ?? 0.5}" onchange="updateProcessorParam(${idx}, 'threshold', parseFloat(this.value))" style="padding: 0.25rem; font-size: 0.75rem;">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">Direction</label>
                    <select onchange="updateProcessorParam(${idx}, 'direction', this.value)" style="padding: 0.25rem; font-size: 0.75rem;">
                        <option value="rising" ${p.direction === 'rising' ? 'selected' : ''}>Rising</option>
                        <option value="falling" ${p.direction === 'falling' ? 'selected' : ''}>Falling</option>
                        <option value="either" ${p.direction === 'either' ? 'selected' : ''}>Either</option>
                    </select>
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.65rem;">Cooldown (ms)</label>
                    <input type="number" min="0" step="10" value="${p.cooldown ?? 100}" onchange="updateProcessorParam(${idx}, 'cooldown', parseFloat(this.value))" style="padding: 0.25rem; font-size: 0.75rem;">
                </div>
            </div>`;
    }
    return '';
}

function addProcessorToChain() {
    // Default to a smooth processor
    currentRouteProcessors.push({
        type: "smooth",
        alpha: 0.2
    });
    renderProcessorsListEditor();
}

function removeProcessor(idx) {
    currentRouteProcessors.splice(idx, 1);
    renderProcessorsListEditor();
}

function changeProcessorType(idx, newType) {
    let base = { type: newType };
    if (newType === 'smooth') base.alpha = 0.2;
    else if (newType === 'gain') base.gain = 1.0;
    else if (newType === 'offset') base.offset = 0.0;
    else if (newType === 'dead_zone') base.threshold = 0.1;
    else if (newType === 'remap') {
        base.input_min = 0.0;
        base.input_max = 1.0;
        base.output_min = 0.0;
        base.output_max = 127.0;
        base.clamp = true;
    } else if (newType === 'threshold_event') {
        base.threshold = 0.5;
        base.direction = 'rising';
        base.cooldown = 100.0;
    }
    
    currentRouteProcessors[idx] = base;
    renderProcessorsListEditor();
}

function updateProcessorParam(idx, paramName, value) {
    currentRouteProcessors[idx][paramName] = value;
}

// Save or add the compiled route
async function saveRoute() {
    const routeName = el.routeName.value.trim() || `Route ${currentConfig.routes.length + 1}`;
    const source = el.routeSource.value;
    const outType = el.routeOutType.value;
    
    const output = { type: outType };
    if (outType === 'midi_cc') {
        output.port_name = el.midiGlobalPort.value;
        output.channel = parseInt(el.routeMidiChan.value) || 1;
        output.cc = parseInt(el.routeMidiCc.value) || 0;
    } else {
        output.host = el.routeOscHost.value.trim() || '127.0.0.1';
        output.port = parseInt(el.routeOscPort.value) || 9001;
        output.address = el.routeOscAddr.value.trim() || '/motion/out';
        output.send_on_change_only = true;
    }
    
    const newRoute = {
        id: editingRouteId || `route_${Date.now()}`,
        name: routeName,
        enabled: true,
        source: source,
        processors: currentRouteProcessors,
        output: output
    };
    
    if (editingRouteId) {
        // Edit existing route
        const index = currentConfig.routes.findIndex(r => r.id === editingRouteId);
        if (index !== -1) {
            currentConfig.routes[index] = newRoute;
        }
    } else {
        // Create new route
        currentConfig.routes.push(newRoute);
    }
    
    await saveConfigImmediate();
    showRouteEditor(false);
}

function editRoute(routeId) {
    const route = currentConfig.routes.find(r => r.id === routeId);
    if (!route) return;
    
    editingRouteId = routeId;
    el.editorTitle.textContent = `Edit Signal Route: ${route.name}`;
    el.routeName.value = route.name;
    el.routeSource.value = route.source;
    
    // Deep copy processors
    currentRouteProcessors = JSON.parse(JSON.stringify(route.processors || []));
    renderProcessorsListEditor();
    
    // Output settings
    el.routeOutType.value = route.output.type;
    if (route.output.type === 'midi_cc') {
        el.outGroupMidi.style.display = 'grid';
        el.outGroupOsc.style.display = 'none';
        el.routeMidiChan.value = route.output.channel || 1;
        el.routeMidiCc.value = route.output.cc || 0;
    } else {
        el.outGroupMidi.style.display = 'none';
        el.outGroupOsc.style.display = 'grid';
        el.routeOscHost.value = route.output.host;
        el.routeOscPort.value = route.output.port;
        el.routeOscAddr.value = route.output.address;
    }
    
    showRouteEditor(true);
}

async function deleteRoute(routeId) {
    if (!confirm("Are you sure you want to delete this signal route?")) return;
    currentConfig.routes = currentConfig.routes.filter(r => r.id !== routeId);
    await saveConfigImmediate();
}

async function toggleRouteEnabled(routeId, isChecked) {
    const route = currentConfig.routes.find(r => r.id === routeId);
    if (route) {
        route.enabled = isChecked;
        await saveConfigImmediate();
    }
}

// --- MIDI & OSC TEST ---

async function refreshMidiPorts() {
    try {
        const res = await fetch('/api/midi/ports?_t=' + Date.now(), { cache: 'no-store' });
        const data = await res.json();
        
        // Check if options actually changed to avoid disrupting the user experience
        const currentPorts = Array.from(el.midiGlobalPort.options).map(o => o.value).filter(v => v !== "");
        const newPorts = data.ports || [];
        
        // Compare lists
        const arraysEqual = currentPorts.length === newPorts.length && currentPorts.every((v, i) => v === newPorts[i]);
        if (arraysEqual && el.midiGlobalPort.value === currentConfig.midi.port_name) {
            return; // No change, do nothing
        }

        let html = '';
        if (newPorts.length === 0) {
            html = `<option value="">No MIDI ports available</option>`;
        } else {
            html = newPorts.map(p => `<option value="${p}">${p}</option>`).join('');
        }
        
        // Keep track of what was selected
        const previouslySelected = el.midiGlobalPort.value || currentConfig.midi.port_name;
        
        // Populate global MIDI drop down
        el.midiGlobalPort.innerHTML = html;
        
        // Restore values
        if (previouslySelected && newPorts.includes(previouslySelected)) {
            el.midiGlobalPort.value = previouslySelected;
        } else if (currentConfig.midi.port_name && newPorts.includes(currentConfig.midi.port_name)) {
            el.midiGlobalPort.value = currentConfig.midi.port_name;
        }
    } catch (err) {
        console.error("Failed to list MIDI ports:", err);
    }
}

// --- TRAJECTORIES MVP ---

async function refreshTrajectoriesList() {
    try {
        const res = await fetch('/api/trajectories?_t=' + Date.now(), { cache: 'no-store' });
        const data = await res.json();
        
        if (data.trajectories.length === 0) {
            el.trajectoryExamplesList.innerHTML = `
                <div style="text-align: center; color: var(--text-muted); font-size: 0.75rem; font-style: italic; padding: 1rem;">
                    No gesture templates saved yet.
                </div>`;
            return;
        }
        
        // Reverse array so last saved template is on top
        const reversedTrajectories = [...data.trajectories].reverse();
        
        let html = '';
        reversedTrajectories.forEach(traj => {
            const ch = traj.midi_channel || 1;
            const cc = traj.midi_cc || 22;
            const variantsCount = (traj.vectors && traj.vectors.length) ? traj.vectors.length : 1;
            
            html += `
                <div class="trajectory-row-item" style="display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.5rem; background-color: #1a1a1e; border: 1px solid var(--border); border-radius: 4px; margin-bottom: 0.35rem;">
                    <!-- Leftmost Section: Variant/Layer count indicator -->
                    <div style="display: flex; align-items: center; justify-content: center; background-color: rgba(10, 132, 255, 0.1); border: 1px solid var(--accent); border-radius: 4px; padding: 0.2rem 0.4rem; font-size: 0.7rem; font-weight: 600; color: var(--accent); white-space: nowrap;" title="${variantsCount} variants/layers stored">
                        L${variantsCount}
                    </div>

                    <!-- Left Section: Label and Channels -->
                    <div style="flex: 2; min-width: 130px; display: flex; flex-direction: column;">
                        <strong style="color: var(--accent); font-size: 0.85rem;">${traj.label}</strong>
                        <span style="font-size: 0.65rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="Channels: ${traj.channels.join(',')}">
                            [${traj.channels.join(',')}]
                        </span>
                    </div>
                    
                    <!-- Mid Section: Compact inputs for MIDI CC -->
                    <div style="flex: 3; display: flex; align-items: center; gap: 0.5rem; justify-content: flex-end;">
                        <div style="display: flex; align-items: center; gap: 0.25rem;">
                            <span style="font-size: 0.65rem; color: var(--text-muted); white-space: nowrap;">MIDI Ch:</span>
                            <input type="number" id="midi-chan-${traj.id}" value="${ch}" min="1" max="16" style="font-size: 0.7rem; width: 36px; padding: 0.15rem 0.25rem; background: #222; color: #fff; border: 1px solid #444; border-radius: 3px; text-align: center;">
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.25rem;">
                            <span style="font-size: 0.65rem; color: var(--text-muted); white-space: nowrap;">CC #:</span>
                            <input type="number" id="midi-cc-${traj.id}" value="${cc}" min="0" max="127" style="font-size: 0.7rem; width: 36px; padding: 0.15rem 0.25rem; background: #222; color: #fff; border: 1px solid #444; border-radius: 3px; text-align: center;">
                        </div>
                    </div>
                    
                    <!-- Right Section: Save and Delete Buttons -->
                    <div style="display: flex; align-items: center; gap: 0.35rem;">
                        <button class="btn btn-success" style="padding: 0.2rem 0.4rem; font-size: 0.65rem; border-radius: 3px;" onclick="saveTrajectoryMidiParams('${traj.id}')">Save</button>
                        <button class="btn btn-danger" style="padding: 0.2rem 0.4rem; font-size: 0.65rem; border-radius: 3px;" onclick="deleteTrajectoryExample('${traj.id}')">✕</button>
                    </div>
                </div>`;
        });
        el.trajectoryExamplesList.innerHTML = html;
    } catch (err) {
        console.error("Error listing trajectories:", err);
    }
}

window.saveTrajectoryMidiParams = async function(trajId) {
    const type = 'cc';
    const channel = parseInt(document.getElementById(`midi-chan-${trajId}`).value) || 1;
    const cc = parseInt(document.getElementById(`midi-cc-${trajId}`).value) || 22;
    const note = 60;
    
    try {
        const res = await fetch(`/api/trajectories/${trajId}/midi`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                midi_channel: channel,
                midi_cc: cc,
                midi_note: note,
                midi_type: type
            })
        });
        if (res.ok) {
            showError(null);
            alert("MIDI parameters saved successfully!");
            await refreshTrajectoriesList();
        } else {
            const errData = await res.json();
            showError("Failed to save trajectory MIDI parameters: " + errData.detail);
        }
    } catch (err) {
        showError("Save MIDI parameters error: " + err.message);
    }
};

async function deleteTrajectoryExample(trajId) {
    if (!confirm("Delete this trajectory template example?")) return;
    try {
        const res = await fetch(`/api/trajectories/${trajId}`, { method: 'DELETE' });
        if (res.ok) {
            await refreshTrajectoriesList();
        }
    } catch (err) {
        showError("Failed to delete trajectory: " + err.message);
    }
}

// --- EVENT LISTENERS SETUP ---

function setupEventListeners() {
    // Session JSON File Export Trigger
    el.btnExportSession.addEventListener('click', () => {
        gatherConfigFromUI();
        const rawJsonString = JSON.stringify(currentConfig, null, 2);
        
        // Generate virtual trigger download file
        const blob = new Blob([rawJsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        
        const customName = el.sessionFilename.value.trim() || "motion_router_session";
        a.href = url;
        a.download = `${customName}.json`;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup download DOM structures
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log("Successfully exported active session parameters as:", customName);
    });

    // Session JSON File Import Reader
    el.importFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const importedData = JSON.parse(e.target.result);
                
                // Confirm valid JSON configuration attributes
                if (typeof importedData !== 'object' || !importedData.osc_input || !importedData.routes) {
                    throw new Error("Invalid Session config file structure. Essential keys are missing.");
                }

                currentConfig = importedData;
                
                // Synchronize LocalStorage and active server config state
                localStorage.setItem('osc_motion_router_persisted_config', JSON.stringify(currentConfig));
                populateUIFromConfig();
                await pushConfigToServer(currentConfig);
                
                alert("Session Config successfully loaded and imported!");
                showError(null);
            } catch (err) {
                alert("Failed to import configuration: " + err.message);
            }
        };
        reader.readAsText(file);
        
        // Reset input field value
        el.importFileInput.value = '';
    });

    // Save-on-edit input forms
    const autoSaveInputs = [
        el.oscBindIp, el.oscPort, el.oscAccelAddress, el.oscGyroAddress, el.oscFormat,
        el.oscAccelIndexes, el.oscGyroIndexes,
        el.midiGlobalPort, el.midiGlobalChannel, el.trajThreshold, el.trajDeviationThreshold, el.trajRecognitionHold, el.trajActionType,
        el.trajActionOscHost, el.trajActionOscPort, el.trajActionOscAddr
    ];
    autoSaveInputs.forEach(input => {
        input.addEventListener('change', saveConfigDebounced);
        input.addEventListener('input', saveConfigDebounced);
    });

    // Refresh MIDI ports when the dropdown gets focus
    el.midiGlobalPort.addEventListener('focus', refreshMidiPorts);

    // Toggle grouped index fields based on format selection
    el.oscFormat.addEventListener('change', () => {
        if (el.oscFormat.value === "grouped") {
            el.groupedIndexesRow.style.display = 'grid';
        } else {
            el.groupedIndexesRow.style.display = 'none';
        }
    });

    // Toggle trajectory action group visibility on select change
    el.trajActionType.addEventListener('change', () => {
        if (el.trajActionType.value === "midi") {
            el.trajActionOscGroup.style.display = 'none';
        } else {
            el.trajActionOscGroup.style.display = 'grid';
        }
    });

    // Toggle routing destination editor fields
    el.routeOutType.addEventListener('change', () => {
        if (el.routeOutType.value === 'midi_cc') {
            el.outGroupMidi.style.display = 'grid';
            el.outGroupOsc.style.display = 'none';
        } else {
            el.outGroupMidi.style.display = 'none';
            el.outGroupOsc.style.display = 'grid';
        }
    });

    // OSC Server start / stop
    el.btnStartOsc.addEventListener('click', async () => {
        try {
            await saveConfigImmediate();
            const res = await fetch('/api/osc/start', { method: 'POST' });
            if (!res.ok) {
                const errData = await res.json();
                showError("OSC receiver failed to start: " + errData.detail);
            }
        } catch (err) {
            showError("Failed to send start OSC request: " + err.message);
        }
    });
    
    el.btnStopOsc.addEventListener('click', async () => {
        try {
            await fetch('/api/osc/stop', { method: 'POST' });
        } catch (err) {
            showError("Failed to send stop OSC request: " + err.message);
        }
    });

    // Learn OSC Addr buttons
    el.btnLearnAccel.addEventListener('click', async () => {
        if (selectedOSCMonitorAddress) {
            el.oscAccelAddress.value = selectedOSCMonitorAddress;
            await saveConfigImmediate();
            el.oscLearnPanel.style.display = 'none';
            selectedOSCMonitorAddress = null;
            await refreshOSCMonitor();
        }
    });

    el.btnLearnGyro.addEventListener('click', async () => {
        if (selectedOSCMonitorAddress) {
            el.oscGyroAddress.value = selectedOSCMonitorAddress;
            await saveConfigImmediate();
            el.oscLearnPanel.style.display = 'none';
            selectedOSCMonitorAddress = null;
            await refreshOSCMonitor();
        }
    });

    // Route Editor Actions
    el.btnNewRoute.addEventListener('click', () => {
        editingRouteId = null;
        el.editorTitle.textContent = "Add New Signal Route";
        el.routeName.value = '';
        el.routeSource.value = 'accel.x';
        currentRouteProcessors = [];
        renderProcessorsListEditor();
        el.routeOutType.value = 'midi_cc';
        el.outGroupMidi.style.display = 'grid';
        el.outGroupOsc.style.display = 'none';
        showRouteEditor(true);
    });

    el.btnCancelRoute.addEventListener('click', () => {
        showRouteEditor(false);
    });

    el.btnSaveRoute.addEventListener('click', saveRoute);
    el.btnAddProcessor.addEventListener('click', addProcessorToChain);

    // CC slider indicator update
    el.midiTestValue.addEventListener('input', () => {
        el.midiTestValueDisplay.textContent = el.midiTestValue.value;
    });

    // Global Manual CC Test Trigger
    el.btnSendMidiTest.addEventListener('click', async () => {
        const payload = {
            port_name: el.midiGlobalPort.value,
            channel: parseInt(el.midiGlobalChannel.value) || 1,
            cc: parseInt(el.midiTestCc.value) || 0,
            value: parseInt(el.midiTestValue.value) || 0
        };
        try {
            const res = await fetch('/api/midi/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showError(null);
            } else {
                const errData = await res.json();
                showError("MIDI CC Test failed: " + errData.detail);
            }
        } catch (err) {
            showError("MIDI Test send error: " + err.message);
        }
    });

    // Global Manual OSC Test Trigger
    el.btnSendOscTest.addEventListener('click', async () => {
        const payload = {
            host: "127.0.0.1",
            port: parseInt(el.oscTestPort.value) || 9001,
            address: el.oscTestAddress.value.trim() || "/test/signal",
            value: parseFloat(el.oscTestValue.value) || 1.0
        };
        try {
            const res = await fetch('/api/osc/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showError(null);
            } else {
                const errData = await res.json();
                showError("OSC Test failed: " + errData.detail);
            }
        } catch (err) {
            showError("OSC Test send error: " + err.message);
        }
    });

    // Status bar stop replay on click (removed)

    // Trajectory Template record example (Start)
    el.btnTrajRecordStart.addEventListener('click', async () => {
        const label = el.trajLabel.value.trim();
        if (!label) {
            alert("Please provide a name/label for the gesture first.");
            return;
        }
        
        // Collect checked channels
        const checkedChannels = [];
        const checks = document.querySelectorAll('.traj-channel-check');
        checks.forEach(c => {
            if (c.checked) checkedChannels.push(c.value);
        });
        
        if (checkedChannels.length === 0) {
            alert("Please select at least one channel to record for the template.");
            return;
        }

        try {
            // Ensure config is up to date first
            await saveConfigImmediate();
            
            const res = await fetch('/api/trajectories/record/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    label: label,
                    channels: checkedChannels,
                    midi_channel: parseInt(el.trajMidiChan.value) || 1,
                    midi_cc: parseInt(el.trajMidiCc.value) || 22
                })
            });
            if (res.ok) {
                showError(null);
                // Immediately query and update status
                const resSt = await fetch('/api/trajectories/status');
                const st = await resSt.json();
                updateTrajectoryStatusUI(st);
            } else {
                const errData = await res.json();
                showError("Trajectory template recording failed: " + errData.detail);
            }
        } catch (err) {
            showError("Trajectory record template error: " + err.message);
        }
    });

    // Trajectory Template record example (Stop & Save)
    el.btnTrajRecordStop.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/trajectories/record/stop', {
                method: 'POST'
            });
            if (res.ok) {
                showError(null);
                // Immediately refresh saved templates list
                await refreshTrajectoriesList();
                // Query and update status
                const resSt = await fetch('/api/trajectories/status');
                const st = await resSt.json();
                updateTrajectoryStatusUI(st);
            } else {
                const errData = await res.json();
                showError("Stopping trajectory template recording failed: " + errData.detail);
            }
        } catch (err) {
            showError("Trajectory stop record error: " + err.message);
        }
    });

    // Trajectory Continuous Recognition Start
    el.btnTrajRecognizeStart.addEventListener('click', async () => {
        const checkedChannels = [];
        const checks = document.querySelectorAll('.traj-channel-check');
        checks.forEach(c => {
            if (c.checked) checkedChannels.push(c.value);
        });
        
        if (checkedChannels.length === 0) {
            alert("Please select at least one channel to recognize.");
            return;
        }

        const duration = 3.0; // Fixed default continuous comparison window (seconds)

        try {
            // Save settings first
            await saveConfigImmediate();
            
            const res = await fetch('/api/trajectories/recognize/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    duration: duration,
                    channels: checkedChannels
                })
            });
            if (res.ok) {
                showError(null);
                const resSt = await fetch('/api/trajectories/status');
                const st = await resSt.json();
                updateTrajectoryStatusUI(st);
            } else {
                const errData = await res.json();
                showError("Trajectory continuous recognition failed: " + errData.detail);
            }
        } catch (err) {
            showError("Trajectory recognition start error: " + err.message);
        }
    });

    // Trajectory Continuous Recognition Stop
    el.btnTrajRecognizeStop.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/trajectories/recognize/stop', {
                method: 'POST'
            });
            if (res.ok) {
                showError(null);
                const resSt = await fetch('/api/trajectories/status');
                const st = await resSt.json();
                updateTrajectoryStatusUI(st);
            } else {
                const errData = await res.json();
                showError("Stopping trajectory recognition failed: " + errData.detail);
            }
        } catch (err) {
            showError("Trajectory recognition stop error: " + err.message);
        }
    });

    // Set Idle Position click event
    el.btnSetIdlePos.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/trajectories/idle', {
                method: 'POST'
            });
            if (res.ok) {
                const data = await res.json();
                alert("Idle position offset stored successfully!");
                console.log("Idle offsets configured to:", data.idle_offsets);
            } else {
                const errData = await res.json();
                showError("Failed to store idle position: " + errData.detail);
            }
        } catch (err) {
            showError("Store idle position error: " + err.message);
        }
    });

    // Discard Last Recording click event
    el.btnTrajDiscardLast.addEventListener('click', async () => {
        const label = el.trajLabel.value.trim();
        if (!label) {
            alert("Please type the Gesture Label of the recording you want to discard.");
            return;
        }

        if (!confirm(`Are you sure you want to discard/undo the last recorded variant for gesture '${label}'?`)) {
            return;
        }

        try {
            const res = await fetch('/api/trajectories/discard-last', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label: label })
            });
            if (res.ok) {
                const data = await res.json();
                showError(null);
                alert(data.message);
                await refreshTrajectoriesList();
            } else {
                const errData = await res.json();
                showError("Discard last recording failed: " + errData.detail);
                alert("Could not discard: " + errData.detail);
            }
        } catch (err) {
            showError("Discard last recording error: " + err.message);
        }
    });
}
