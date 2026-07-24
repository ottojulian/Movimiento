import os
import sys
import socket
import time
import threading
import webbrowser
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Import local modules
from config import config_manager
from osc_io import osc_receiver
from midi_io import midi_manager
from processing import route_processor
from trajectories import trajectory_manager

# Wire up the master signal handler callback
def on_signal_update(updated_signals: List[str]):
    # 1. Process routes
    route_processor.process_signals(updated_signals)
    
    # 2. Feed recording / trajectory analyzer with the latest signals
    with osc_receiver.lock:
        sigs = dict(osc_receiver.latest_signals)
    trajectory_manager.handle_incoming_sample(sigs)

# Register the master signal update callback
osc_receiver.set_on_signal_update(on_signal_update)

# Initialize route_processor with initial routes from config
route_processor.sync_routes(config_manager.get("routes", []))

# Auto-start OSC receiver if enabled on startup
initial_config = config_manager.get_all()
if initial_config.get("osc_input", {}).get("enabled", True):
    osc_receiver.start(initial_config)

# --- FastAPI App Setup ---
app = FastAPI(title="OSC Motion Router API")

# Request Models
class ConfigUpdateModel(BaseModel):
    web_port: Optional[int] = None
    osc_input: Optional[Dict[str, Any]] = None
    osc_outputs: Optional[List[Dict[str, Any]]] = None
    midi: Optional[Dict[str, Any]] = None
    routes: Optional[List[Dict[str, Any]]] = None
    trajectory: Optional[Dict[str, Any]] = None

class MidiTestModel(BaseModel):
    port_name: str
    channel: int
    cc: int
    value: int

class OscTestModel(BaseModel):
    host: str
    port: int
    address: str
    value: float

class RecordStartModel(BaseModel):
    name: str

class ReplayStartModel(BaseModel):
    id: str
    loop: bool = False

class TrajectoryRecordModel(BaseModel):
    label: str
    duration: float = 3.0
    channels: List[str] = ["accel.x", "accel.y", "accel.z"]

class TrajectoryRecognizeModel(BaseModel):
    duration: float = 3.0
    channels: List[str] = ["accel.x", "accel.y", "accel.z"]


# --- API Endpoints ---

@app.get("/api/status")
def get_status():
    osc_status = osc_receiver.get_status()
    midi_ports = midi_manager.get_output_ports()
    traj_status = trajectory_manager.get_status()
    
    # Global midi configuration
    global_midi = config_manager.get("midi", {})
    configured_midi_port = global_midi.get("port_name", "")
    
    # Determine MIDI state
    midi_active = False
    if configured_midi_port in midi_ports:
        # Check if actually cached/open
        with midi_manager.lock:
            midi_active = configured_midi_port in midi_manager.open_ports
    
    return {
        "osc_receiver_running": osc_status["running"],
        "osc_bind_ip": config_manager.get("osc_input", {}).get("bind_ip", "0.0.0.0"),
        "osc_port": config_manager.get("osc_input", {}).get("port", 9000),
        "latest_timestamp": osc_status["latest_timestamp"],
        "packet_count": osc_status["packet_count"],
        "packet_rate": osc_status["packet_rate"],
        "midi_active": midi_active,
        "midi_port": configured_midi_port,
        "last_error": osc_status["last_error"] or midi_manager.last_error,
        "recording": traj_status
    }

@app.get("/api/config")
def get_config():
    return config_manager.get_all()

@app.post("/api/config")
def update_config(data: Dict[str, Any]):
    # Save incoming dictionary
    config_manager.update_all(data)
    
    # Sync route processor
    route_processor.sync_routes(data.get("routes", []))
    
    # Clear client caches for outgoing OSC if outputs changed
    osc_receiver.clear_clients_cache()
    
    return {"status": "success", "config": config_manager.get_all()}

@app.get("/api/live")
def get_live():
    with osc_receiver.lock:
        raw = dict(osc_receiver.latest_signals)
        rate = osc_receiver.packet_rate
        timestamp = osc_receiver.latest_timestamp
        
    cooked = route_processor.get_cooked_values()
    
    return {
        "raw": raw,
        "cooked": cooked,
        "packet_rate": rate,
        "timestamp": timestamp,
        "replay": trajectory_manager.get_status()
    }

@app.get("/api/osc/messages")
def get_osc_messages():
    return osc_receiver.get_observed_messages()

@app.post("/api/osc/start")
def start_osc():
    cfg = config_manager.get_all()
    success = osc_receiver.start(cfg)
    if not success:
        raise HTTPException(status_code=400, detail=osc_receiver.last_error or "Failed to start OSC receiver")
    return {"status": "success", "message": "OSC receiver started"}

@app.post("/api/osc/stop")
def stop_osc():
    osc_receiver.stop()
    return {"status": "success", "message": "OSC receiver stopped"}

@app.get("/api/midi/ports")
def get_midi_ports():
    return {"ports": midi_manager.get_output_ports()}

@app.post("/api/midi/test")
def test_midi(payload: MidiTestModel):
    success = midi_manager.send_cc(payload.port_name, payload.channel, payload.cc, payload.value)
    if not success:
        raise HTTPException(status_code=400, detail=midi_manager.last_error or "Failed to send MIDI CC")
    return {"status": "success"}

@app.post("/api/osc/test")
def test_osc(payload: OscTestModel):
    osc_receiver.send_osc_message(payload.host, payload.port, payload.address, payload.value)
    return {"status": "success"}

# --- Recording & Replay ---

@app.get("/api/recordings")
def list_recordings():
    return {"recordings": trajectory_manager.recordings_list}

@app.post("/api/record/start")
def start_record(payload: RecordStartModel):
    trajectory_manager.start_recording(payload.name)
    return {"status": "success", "message": f"Recording '{payload.name}' started"}

@app.post("/api/record/stop")
def stop_record():
    entry = trajectory_manager.stop_recording()
    if not entry:
        raise HTTPException(status_code=400, detail="No samples recorded or failed to save")
    return {"status": "success", "recording": entry}

@app.delete("/api/recordings/{rec_id}")
def delete_recording(rec_id: str):
    success = trajectory_manager.delete_recording(rec_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {"status": "success"}

@app.post("/api/replay/start")
def start_replay(payload: ReplayStartModel):
    success = trajectory_manager.start_replay(payload.id, payload.loop)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start replay")
    return {"status": "success"}

@app.post("/api/replay/stop")
def stop_replay():
    trajectory_manager.stop_replay()
    return {"status": "success"}

# --- Trajectories ---

@app.get("/api/trajectories")
def list_trajectories():
    return {"trajectories": trajectory_manager.trajectories_list}

@app.delete("/api/trajectories/{traj_id}")
def delete_trajectory(traj_id: str):
    success = trajectory_manager.delete_trajectory_example(traj_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trajectory example not found")
    return {"status": "success"}

@app.post("/api/trajectories/record")
def record_trajectory_example(payload: TrajectoryRecordModel):
    success = trajectory_manager.record_trajectory_example(
        payload.label, payload.duration, payload.channels
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot start trajectory recording (another action is busy)")
    return {"status": "success", "message": f"Trajectory countdown started for '{payload.label}'"}

@app.post("/api/trajectories/recognize")
def recognize_trajectory(payload: TrajectoryRecognizeModel):
    success = trajectory_manager.start_trajectory_recognition_capture(
        payload.duration, payload.channels
    )
    if not success:
        raise HTTPException(status_code=400, detail="Cannot start trajectory recognition (another action is busy)")
    return {"status": "success", "message": "Trajectory capture started for recognition"}

@app.get("/api/trajectories/status")
def get_trajectory_status():
    return trajectory_manager.get_status()


# --- Cleanup and Shutdown ---

@app.on_event("shutdown")
def shutdown_event():
    print("Shutting down and cleaning up resources...")
    osc_receiver.stop()
    trajectory_manager.stop_replay()
    config_manager.save_immediate()
    midi_manager.close_all()


# --- Serve Static Frontend Files ---
# Resolve the web/ directory relative to this script
current_dir = os.path.dirname(os.path.abspath(__file__))
web_dir = os.path.join(current_dir, "web")
os.makedirs(web_dir, exist_ok=True)

# Mount web directory
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")


# --- Main entry point ---

def find_available_port(start_port: int) -> int:
    port = start_port
    while port < 65535:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            port += 1
    return start_port

def open_browser(port: int):
    time.sleep(1.2) # Wait slightly for Uvicorn to initialize
    url = f"http://127.0.0.1:{port}"
    print(f"\n==================================================")
    print(f"OSC Motion Router is running!")
    print(f"Open your browser at: {url}")
    print(f"==================================================\n")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Failed to auto-open browser: {e}", file=sys.stderr)

if __name__ == "__main__":
    configured_port = config_manager.get("web_port", 8765)
    final_port = find_available_port(configured_port)
    
    # Update config file if the port changed
    if final_port != configured_port:
        print(f"Port {configured_port} was busy, using available port {final_port}")
        config_manager.update_key("web_port", final_port)
        config_manager.save_immediate()

    # Launch browser thread
    threading.Thread(target=open_browser, args=(final_port,), daemon=True).start()

    # Start FastAPI / Uvicorn server
    uvicorn.run(app, host="127.0.0.1", port=final_port)
