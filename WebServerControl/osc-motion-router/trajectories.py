import os
import sys
import json
import time
import threading
from typing import List, Dict, Any, Optional
import numpy as np
from config import config_manager
from osc_io import osc_receiver
from processing import route_processor

class TrajectoryManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.data_dir = config_manager.data_dir
        self.recordings_dir = config_manager.recordings_dir
        self.recordings_index_path = os.path.join(self.recordings_dir, "index.json")
        
        # Ensure directory exists
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        # Trajectories examples directory
        self.trajectories_dir = os.path.join(self.data_dir, "trajectories")
        os.makedirs(self.trajectories_dir, exist_ok=True)
        self.trajectories_index_path = os.path.join(self.trajectories_dir, "index.json")

        # Recording state
        self.recording_active = False
        self.recording_name = ""
        self.recording_start_time = 0.0
        self.recording_buffer = {
            "timestamps": [],
            "accel_x": [], "accel_y": [], "accel_z": [],
            "gyro_x": [], "gyro_y": [], "gyro_z": []
        }

        # Replay state
        self.replay_active = False
        self.replay_thread: Optional[threading.Thread] = None
        self.replay_loop = False
        self.replay_current_index = 0
        self.replay_total_samples = 0
        self.replay_progress = 0.0  # 0.0 to 100.0
        self.replay_name = ""

        # Trajectory recording / recognition state
        self.test_capture_active = False
        self.test_capture_start_time = 0.0
        self.test_capture_duration = 3.0  # seconds
        self.test_capture_channels = ["accel.x", "accel.y", "accel.z"]
        self.test_capture_buffer = {
            "timestamps": []
        }
        for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
            self.test_capture_buffer[ch] = []
            
        self.recognition_active = False
        self.recognition_result = ""
        self.recognition_distance = 0.0
        self.recognition_triggered = False

        # Load indices
        self.recordings_list = self._load_json_index(self.recordings_index_path)
        self.trajectories_list = self._load_json_index(self.trajectories_index_path)

    def _load_json_index(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading index from {path}: {e}", file=sys.stderr)
            return []

    def _save_json_index(self, path: str, index_list: List[Dict[str, Any]]):
        try:
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(index_list, f, indent=2)
            if os.path.exists(path):
                os.remove(path)
            os.rename(tmp_path, path)
        except Exception as e:
            print(f"Error saving index to {path}: {e}", file=sys.stderr)

    # --- Recording Logic ---
    def start_recording(self, name: str):
        with self.lock:
            if self.recording_active:
                return
            self.recording_active = True
            self.recording_name = name or "recording"
            self.recording_start_time = time.time()
            self.recording_buffer = {
                "timestamps": [],
                "accel_x": [], "accel_y": [], "accel_z": [],
                "gyro_x": [], "gyro_y": [], "gyro_z": []
            }
        print(f"Started recording: {self.recording_name}")

    def handle_incoming_sample(self, signals: Dict[str, float]):
        """Buffers a sample if recording or trajectory test capture is active."""
        now = time.time()
        
        # 1. Normal Recording
        # Avoid locking unless we are actually recording to minimize overhead
        if self.recording_active:
            with self.lock:
                # Re-verify inside lock
                if self.recording_active:
                    self.recording_buffer["timestamps"].append(now)
                    self.recording_buffer["accel_x"].append(signals.get("accel.x", 0.0))
                    self.recording_buffer["accel_y"].append(signals.get("accel.y", 0.0))
                    self.recording_buffer["accel_z"].append(signals.get("accel.z", 0.0))
                    self.recording_buffer["gyro_x"].append(signals.get("gyro.x", 0.0))
                    self.recording_buffer["gyro_y"].append(signals.get("gyro.y", 0.0))
                    self.recording_buffer["gyro_z"].append(signals.get("gyro.z", 0.0))

        # 2. Trajectory Test Capture
        if self.test_capture_active:
            with self.lock:
                if self.test_capture_active:
                    elapsed = now - self.test_capture_start_time
                    if elapsed <= self.test_capture_duration:
                        self.test_capture_buffer["timestamps"].append(now)
                        for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                            self.test_capture_buffer[ch].append(signals.get(ch, 0.0))
                    else:
                        # Capture completed!
                        self.test_capture_active = False
                        # Trigger evaluation in a separate thread to not block incoming OSC callbacks
                        threading.Thread(target=self._evaluate_test_capture, daemon=True).start()

    def stop_recording(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.recording_active:
                return None
            
            self.recording_active = False
            timestamps = self.recording_buffer["timestamps"]
            if not timestamps:
                print("No samples recorded, aborting save.")
                return None
            
            duration = timestamps[-1] - timestamps[0]
            timestamp_int = int(self.recording_start_time)
            filename = f"{timestamp_int}_{self.recording_name}.npz"
            filepath = os.path.join(self.recordings_dir, filename)
            
            # Save npz file
            try:
                np.savez_compressed(
                    filepath,
                    timestamps=np.array(timestamps),
                    accel_x=np.array(self.recording_buffer["accel_x"]),
                    accel_y=np.array(self.recording_buffer["accel_y"]),
                    accel_z=np.array(self.recording_buffer["accel_z"]),
                    gyro_x=np.array(self.recording_buffer["gyro_x"]),
                    gyro_y=np.array(self.recording_buffer["gyro_y"]),
                    gyro_z=np.array(self.recording_buffer["gyro_z"])
                )
            except Exception as e:
                print(f"Error saving npz file: {e}", file=sys.stderr)
                return None

            # Add to index
            relative_path = os.path.join("data", "recordings", filename)
            entry = {
                "id": f"{timestamp_int}_{self.recording_name}",
                "name": self.recording_name,
                "timestamp": self.recording_start_time,
                "duration": duration,
                "file_path": relative_path
            }
            self.recordings_list.append(entry)
            self._save_json_index(self.recordings_index_path, self.recordings_list)
            
        print(f"Stopped recording. Saved to {filepath}")
        return entry

    def delete_recording(self, rec_id: str) -> bool:
        with self.lock:
            found = None
            for item in self.recordings_list:
                if item["id"] == rec_id:
                    found = item
                    break
            if not found:
                return False
                
            # Remove file
            filename = os.path.basename(found["file_path"])
            fullpath = os.path.join(self.recordings_dir, filename)
            if os.path.exists(fullpath):
                try:
                    os.remove(fullpath)
                except Exception as e:
                    print(f"Error deleting recording file {fullpath}: {e}", file=sys.stderr)
                    
            self.recordings_list.remove(found)
            self._save_json_index(self.recordings_index_path, self.recordings_list)
            return True

    # --- Replay Logic ---
    def start_replay(self, rec_id: str, loop: bool = False) -> bool:
        with self.lock:
            if self.replay_active:
                self._stop_replay_unlocked()
                
            found = None
            for item in self.recordings_list:
                if item["id"] == rec_id:
                    found = item
                    break
            if not found:
                print(f"Recording '{rec_id}' not found for replay")
                return False
                
            filename = os.path.basename(found["file_path"])
            fullpath = os.path.join(self.recordings_dir, filename)
            if not os.path.exists(fullpath):
                print(f"Recording file '{fullpath}' missing", file=sys.stderr)
                return False
                
            try:
                data = np.load(fullpath)
                # Load fully into RAM to avoid locks or file handles remaining open
                self.replay_data = {
                    "timestamps": data["timestamps"],
                    "accel_x": data["accel_x"],
                    "accel_y": data["accel_y"],
                    "accel_z": data["accel_z"],
                    "gyro_x": data["gyro_x"],
                    "gyro_y": data["gyro_y"],
                    "gyro_z": data["gyro_z"]
                }
            except Exception as e:
                print(f"Failed to load npz file for replay: {e}", file=sys.stderr)
                return False
                
            self.replay_active = True
            self.replay_loop = loop
            self.replay_name = found["name"]
            self.replay_current_index = 0
            self.replay_total_samples = len(self.replay_data["timestamps"])
            self.replay_progress = 0.0
            
            self.replay_thread = threading.Thread(target=self._replay_loop_worker, daemon=True)
            self.replay_thread.start()
            return True

    def _replay_loop_worker(self):
        print(f"Replay worker thread started for: {self.replay_name}")
        while True:
            # Get samples
            with self.lock:
                if not self.replay_active:
                    break
                data = self.replay_data
                total = self.replay_total_samples
                idx = self.replay_current_index
                loop = self.replay_loop
                
            if idx >= total:
                if loop:
                    with self.lock:
                        self.replay_current_index = 0
                        idx = 0
                else:
                    break

            # Read sample values
            t_curr = data["timestamps"][idx]
            sigs = {
                "accel.x": float(data["accel_x"][idx]),
                "accel.y": float(data["accel_y"][idx]),
                "accel.z": float(data["accel_z"][idx]),
                "gyro.x": float(data["gyro_x"][idx]),
                "gyro.y": float(data["gyro_y"][idx]),
                "gyro.z": float(data["gyro_z"][idx])
            }
            
            # Update live signal values in the receiver
            with osc_receiver.lock:
                osc_receiver.latest_signals.update(sigs)
                osc_receiver.latest_timestamp = time.time()
                
            # Run routes
            route_processor.process_signals(list(sigs.keys()))
            
            # Feed recorder if active (re-recording)
            self.handle_incoming_sample(sigs)
            
            # Determine sleep time
            with self.lock:
                self.replay_current_index += 1
                self.replay_progress = (self.replay_current_index / total) * 100.0
                
                if self.replay_current_index < total:
                    t_next = data["timestamps"][self.replay_current_index]
                    sleep_time = t_next - t_curr
                    if sleep_time < 0 or sleep_time > 1.0: # safety cap
                        sleep_time = 0.01
                else:
                    sleep_time = 0.01

            if sleep_time > 0:
                time.sleep(sleep_time)
                
        with self.lock:
            self.replay_active = False
            self.replay_progress = 100.0
        print("Replay worker thread finished")

    def stop_replay(self):
        with self.lock:
            self._stop_replay_unlocked()

    def _stop_replay_unlocked(self):
        self.replay_active = False
        self.replay_thread = None
        self.replay_progress = 0.0
        self.replay_name = ""

    # --- Trajectory Example Recording & Comparison ---
    def record_trajectory_example(self, label: str, duration: float, channels: List[str]) -> bool:
        """
        Initiates trajectory example recording.
        Will sleep for 3s (countdown) in a separate thread, then record for 'duration'.
        """
        with self.lock:
            if self.test_capture_active or self.recording_active:
                return False
                
            # Set up parameters
            self.test_capture_active = True
            self.test_capture_duration = duration
            self.test_capture_channels = channels
            self.test_capture_buffer = {"timestamps": []}
            for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                self.test_capture_buffer[ch] = []
                
            # Set mode: recording example
            self.example_label = label
            self.is_recording_example = True
            self.test_capture_start_time = time.time() + 3.0 # Starts in 3 seconds
            
        print(f"Trajectory example countdown started for label: {label} (starts in 3s)")
        # Run countdown wait in background
        threading.Thread(target=self._countdown_and_start_capture, daemon=True).start()
        return True

    def start_trajectory_recognition_capture(self, duration: float, channels: List[str]) -> bool:
        """
        Initiates a single test capture for comparison against saved trajectories.
        No countdown. Starts immediately.
        """
        with self.lock:
            if self.test_capture_active:
                return False
                
            self.test_capture_active = True
            self.test_capture_duration = duration
            self.test_capture_channels = channels
            self.test_capture_buffer = {"timestamps": []}
            for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                self.test_capture_buffer[ch] = []
                
            self.is_recording_example = False
            self.test_capture_start_time = time.time()
            self.recognition_triggered = False
            self.recognition_result = ""
            self.recognition_distance = 0.0
            
        print(f"Trajectory recognition test capture started immediately for {duration} seconds")
        return True

    def _countdown_and_start_capture(self):
        time.sleep(3.0)
        with self.lock:
            # Reset start time to now to start recording actual samples
            self.test_capture_start_time = time.time()
            # Clear buffer to ensure we only get samples from now on
            self.test_capture_buffer = {"timestamps": []}
            for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                self.test_capture_buffer[ch] = []
            print("Trajectory example recording ACTIVE NOW")

    def _evaluate_test_capture(self):
        """Processes the captured trajectory (either saves as example or compares for recognition)."""
        with self.lock:
            timestamps = list(self.test_capture_buffer["timestamps"])
            # Load selected channels
            channels = list(self.test_capture_channels)
            label = getattr(self, "example_label", "trajectory")
            is_example = getattr(self, "is_recording_example", False)
            
            if not timestamps or len(timestamps) < 5:
                print("Not enough samples captured for trajectory recognition.", file=sys.stderr)
                return

            # Extract data columns
            data_cols = []
            for ch in channels:
                data_cols.append(self.test_capture_buffer[ch])
            
            # Convert to numpy arrays
            data_matrix = np.column_stack(data_cols) # shape (N, num_channels)
            t_array = np.array(timestamps)
            
            # 1. Resample to 100 points
            resampled = self._resample_trajectory(t_array, data_matrix, 100)
            
            # 2. Normalize by subtracting mean of each channel
            mean = resampled.mean(axis=0)
            normalized = resampled - mean
            
            # 3. Flatten into 1D vector
            flat_vector = normalized.flatten().tolist()

        if is_example:
            # Save as example
            self._save_trajectory_example(label, channels, flat_vector)
        else:
            # Perform recognition
            self._recognize_trajectory(channels, flat_vector)

    def _resample_trajectory(self, t_array: np.ndarray, data: np.ndarray, target_points: int = 100) -> np.ndarray:
        N = len(t_array)
        num_channels = data.shape[1]
        if N < 2:
            return np.zeros((target_points, num_channels))
        
        t_target = np.linspace(t_array[0], t_array[-1], target_points)
        resampled = np.zeros((target_points, num_channels))
        for i in range(num_channels):
            resampled[:, i] = np.interp(t_target, t_array, data[:, i])
        return resampled

    def _save_trajectory_example(self, label: str, channels: List[str], flat_vector: List[float]):
        with self.lock:
            example_id = f"traj_{int(time.time())}"
            entry = {
                "id": example_id,
                "label": label,
                "timestamp": time.time(),
                "channels": channels,
                "vector": flat_vector
            }
            self.trajectories_list.append(entry)
            self._save_json_index(self.trajectories_index_path, self.trajectories_list)
        print(f"Saved trajectory example for '{label}' with {len(flat_vector)} size")

    def delete_trajectory_example(self, traj_id: str) -> bool:
        with self.lock:
            found = None
            for item in self.trajectories_list:
                if item["id"] == traj_id:
                    found = item
                    break
            if not found:
                return False
            self.trajectories_list.remove(found)
            self._save_json_index(self.trajectories_index_path, self.trajectories_list)
            return True

    def _recognize_trajectory(self, channels: List[str], test_vector: List[float]):
        """Compares test_vector with stored examples matching the same channels."""
        with self.lock:
            examples = [ex for ex in self.trajectories_list if ex["channels"] == channels]
            
            if not examples:
                print("No matching trajectory examples found for channel set:", channels)
                self.recognition_result = "No matching templates"
                self.recognition_distance = 0.0
                return

            best_match = None
            min_dist = float("inf")
            test_np = np.array(test_vector)

            for ex in examples:
                ex_np = np.array(ex["vector"])
                # Euclidean distance
                dist = np.linalg.norm(test_np - ex_np)
                if dist < min_dist:
                    min_dist = dist
                    best_match = ex

            # Retrieve recognition threshold from configuration (default is high, user configured)
            # Let's say threshold of 10.0 Euclidean distance
            # We can read this threshold from the route/trajectory configuration or allow configuring it in global config
            # Let's check config, if not set, let's use a threshold of 15.0 as default
            config_threshold = config_manager.config.get("trajectory", {}).get("recognition_threshold", 15.0)
            
            self.recognition_distance = float(min_dist)
            
            if min_dist <= config_threshold and best_match:
                self.recognition_result = best_match["label"]
                self.recognition_triggered = True
                print(f"Trajectory RECOGNIZED: '{best_match['label']}' (distance: {min_dist:.2f} <= threshold {config_threshold:.2f})")
                
                # Trigger action (OSC message or MIDI CC)
                self._trigger_recognition_action(best_match["label"])
            else:
                self.recognition_result = f"None (Closest: '{best_match['label'] if best_match else 'Unknown'}' with distance {min_dist:.2f} > threshold {config_threshold:.2f})"
                self.recognition_triggered = False
                print(f"Trajectory NOT recognized. Closest was '{best_match['label'] if best_match else 'None'}' distance: {min_dist:.2f}")

    def _trigger_recognition_action(self, label: str):
        """Triggers the configured OSC/MIDI action on successful recognition."""
        traj_config = config_manager.config.get("trajectory", {})
        action = traj_config.get("action", {})
        action_type = action.get("type", "osc")
        
        if action_type == "osc":
            host = action.get("host", "127.0.0.1")
            port = action.get("port", 9001)
            address = action.get("address", "/motion/recognized")
            # We can send 1.0 or the label name as argument. Let's send 1.0
            osc_receiver.send_osc_message(host, port, address, 1.0)
            print(f"Recognition OSC action triggered: sending 1.0 to {host}:{port} {address}")
        elif action_type == "midi":
            port_name = action.get("port_name", "")
            channel = action.get("channel", 1)
            cc = action.get("cc", 22)
            value = action.get("value", 127)
            # Send MIDI CC
            from midi_io import midi_manager
            midi_manager.send_cc(port_name, channel, cc, value)
            print(f"Recognition MIDI CC action triggered: sending CC {cc} val {value} to port '{port_name}'")

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            # Let's estimate remaining countdown if test capture has not started yet
            countdown = 0.0
            if self.test_capture_active:
                now = time.time()
                if now < self.test_capture_start_time:
                    countdown = max(0.0, self.test_capture_start_time - now)
            
            return {
                "recording_active": self.recording_active,
                "recording_name": self.recording_name,
                "recording_duration": (time.time() - self.recording_start_time) if self.recording_active else 0.0,
                "replay_active": self.replay_active,
                "replay_name": self.replay_name,
                "replay_progress": self.replay_progress,
                "test_capture_active": self.test_capture_active,
                "countdown": countdown,
                "recognition_result": self.recognition_result,
                "recognition_distance": self.recognition_distance,
                "recognition_triggered": self.recognition_triggered
            }

# Global trajectory manager instance
trajectory_manager = TrajectoryManager()
