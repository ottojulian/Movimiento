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
        self.lock = threading.RLock()
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
            
        self.is_recording_example = False
        self.recognition_active = False
        self.recognition_result = ""
        self.recognition_distance = 0.0
        self.recognition_triggered = False
        
        self.recognition_buffer = {
            "timestamps": []
        }
        for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
            self.recognition_buffer[ch] = []
        self.last_recognition_time = 0.0
        self.last_recognized_label = None

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
        
        # Apply idle offset adjustments from config
        traj_config = config_manager.config.get("trajectory", {})
        idle_offsets = traj_config.get("idle_offsets", {})
        adjusted_signals = dict(signals)
        for key in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
            if key in adjusted_signals and key in idle_offsets:
                adjusted_signals[key] = adjusted_signals[key] - idle_offsets[key]

        # 1. Normal Recording
        # Avoid locking unless we are actually recording to minimize overhead
        if self.recording_active:
            with self.lock:
                # Re-verify inside lock
                if self.recording_active:
                    self.recording_buffer["timestamps"].append(now)
                    self.recording_buffer["accel_x"].append(adjusted_signals.get("accel.x", 0.0))
                    self.recording_buffer["accel_y"].append(adjusted_signals.get("accel.y", 0.0))
                    self.recording_buffer["accel_z"].append(adjusted_signals.get("accel.z", 0.0))
                    self.recording_buffer["gyro_x"].append(adjusted_signals.get("gyro.x", 0.0))
                    self.recording_buffer["gyro_y"].append(adjusted_signals.get("gyro.y", 0.0))
                    self.recording_buffer["gyro_z"].append(adjusted_signals.get("gyro.z", 0.0))

        # 2. Trajectory Test Capture (Manual Template Recording)
        if self.test_capture_active:
            with self.lock:
                if self.test_capture_active:
                    self.test_capture_buffer["timestamps"].append(now)
                    for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                        self.test_capture_buffer[ch].append(adjusted_signals.get(ch, 0.0))

        # 3. Continuous Recognition (Wekinator Mode)
        if getattr(self, "recognition_active", False):
            with self.lock:
                if getattr(self, "recognition_active", False):
                    self.recognition_buffer["timestamps"].append(now)
                    for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                        self.recognition_buffer[ch].append(adjusted_signals.get(ch, 0.0))
                    
                    # Clean up old samples outside the window
                    window_size_sec = self.test_capture_duration
                    cutoff_time = now - window_size_sec
                    
                    # Find how many samples are before cutoff
                    timestamps = self.recognition_buffer["timestamps"]
                    keep_idx = 0
                    while keep_idx < len(timestamps) and timestamps[keep_idx] < cutoff_time:
                        keep_idx += 1
                    
                    if keep_idx > 0:
                        self.recognition_buffer["timestamps"] = timestamps[keep_idx:]
                        for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                            self.recognition_buffer[ch] = self.recognition_buffer[ch][keep_idx:]
                    
                    # Throttle evaluations to every 100ms
                    if now - self.last_recognition_time >= 0.1:
                        self.last_recognition_time = now
                        threading.Thread(target=self._evaluate_recognition_window, daemon=True).start()

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
    def start_trajectory_example_recording(self, label: str, channels: List[str], midi_channel: int = 1, midi_cc: int = 22) -> bool:
        """
        Initiates trajectory example recording manually.
        Starts immediately.
        """
        with self.lock:
            if self.test_capture_active or self.recording_active:
                return False
                
            # Set up parameters
            self.test_capture_active = True
            self.test_capture_channels = channels
            self.test_capture_buffer = {"timestamps": []}
            for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                self.test_capture_buffer[ch] = []
                
            # Set mode: recording example
            self.example_label = label
            self.example_midi_channel = midi_channel
            self.example_midi_cc = midi_cc
            self.is_recording_example = True
            self.test_capture_start_time = time.time()
            
        print(f"Trajectory example recording started manually for label: {label}")
        return True

    def stop_trajectory_example_recording(self) -> bool:
        """
        Stops the manual trajectory example recording and triggers evaluation to save it.
        """
        with self.lock:
            if not self.test_capture_active or not self.is_recording_example:
                return False
            
            self.test_capture_active = False
            # Trigger evaluation in a separate thread to process and save the template
            threading.Thread(target=self._evaluate_test_capture, daemon=True).start()
            return True

    def start_trajectory_recognition(self, duration: float, channels: List[str]) -> bool:
        """
        Initiates continuous trajectory recognition.
        No countdown. Starts immediately.
        """
        with self.lock:
            if self.test_capture_active:
                return False
                
            self.recognition_active = True
            self.test_capture_duration = duration
            self.test_capture_channels = channels
            self.recognition_buffer = {"timestamps": []}
            for ch in ["accel.x", "accel.y", "accel.z", "gyro.x", "gyro.y", "gyro.z"]:
                self.recognition_buffer[ch] = []
                
            self.last_recognition_time = 0.0
            self.last_recognized_label = None
            self.recognition_triggered = False
            self.recognition_result = "Analyzing..."
            self.recognition_distance = 0.0
            
        print(f"Continuous trajectory recognition started (window: {duration}s)")
        return True

    def stop_trajectory_recognition(self) -> bool:
        """
        Stops continuous trajectory recognition.
        """
        with self.lock:
            if not getattr(self, "recognition_active", False):
                return False
            self.recognition_active = False
            self.recognition_triggered = False
            self.recognition_result = ""
            self.recognition_distance = 0.0
            self.last_recognized_label = None
        print("Continuous trajectory recognition stopped")
        return True

    def _evaluate_recognition_window(self):
        with self.lock:
            if not getattr(self, "recognition_active", False):
                return

            timestamps = list(self.recognition_buffer["timestamps"])
            channels = list(self.test_capture_channels)
            
            # Check if we have enough samples
            if not timestamps or len(timestamps) < 5 or (timestamps[-1] - timestamps[0]) < 0.2:
                return

            # Extract data columns
            data_cols = []
            for ch in channels:
                data_cols.append(list(self.recognition_buffer[ch]))
            
            # Convert to numpy matrix
            data_matrix = np.column_stack(data_cols)
            
            # --- Motion Gate / Idle Check ---
            # Calculate standard deviation along the time axis for each active channel.
            # If the maximum standard deviation among all active comparison channels is 
            # extremely small, the device is static (no meaningful gestural trajectory).
            std_deviations = np.std(data_matrix, axis=0)
            max_std = np.max(std_deviations) if len(std_deviations) > 0 else 0.0
            
            # Idle threshold: Retrieve configured deviation threshold (defaults to 0.035)
            # captures gravity noise on an idle desk to prevent false triggers when static.
            config_dev_thresh = config_manager.config.get("trajectory", {}).get("deviation_threshold", 0.035)
            
            if max_std < config_dev_thresh:
                self.recognition_result = f"Idle (Static, max std: {max_std:.3f} < {config_dev_thresh:.3f})"
                self.recognition_triggered = False
                self.recognition_distance = 0.0
                
                if getattr(self, "last_recognized_label", None) is not None:
                    print(f"Device went static. Resetting recognized gesture label from '{self.last_recognized_label}'")
                    self.last_recognized_label = None
                return
            
            t_array = np.array(timestamps)
            
            # 1. Resample to 50 points for efficient and responsive DTW
            resampled = self._resample_trajectory(t_array, data_matrix, 50)
            
            # Use raw resampled values instead of mean-centering to preserve spatial relationships
            # (e.g., keeping absolute X/Y coordinate differences to distinguish left from right side of a square)
            normalized = resampled
            
            # 3. Flatten into 1D vector
            flat_vector = normalized.flatten().tolist()
            
        # Perform recognition
        self._recognize_trajectory(channels, flat_vector)

    def _evaluate_test_capture(self):
        """Processes the captured trajectory (either saves as example or compares for recognition)."""
        with self.lock:
            timestamps = list(self.test_capture_buffer["timestamps"])
            # Load selected channels
            channels = list(self.test_capture_channels)
            label = getattr(self, "example_label", "trajectory")
            is_example = getattr(self, "is_recording_example", False)
            midi_channel = getattr(self, "example_midi_channel", 1)
            midi_cc = getattr(self, "example_midi_cc", 22)
            
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
            
            # 1. Resample to 50 points
            resampled = self._resample_trajectory(t_array, data_matrix, 50)
            
            # Use raw resampled values instead of mean-centering to preserve spatial relationships
            # (e.g., keeping absolute X/Y coordinate differences to distinguish left from right side of a square)
            normalized = resampled
            
            # 3. Flatten into 1D vector
            flat_vector = normalized.flatten().tolist()

        if is_example:
            # Save as example
            self._save_trajectory_example(label, channels, flat_vector, midi_channel, midi_cc)
        else:
            # Perform recognition
            self._recognize_trajectory(channels, flat_vector)

    def _resample_trajectory(self, t_array: np.ndarray, data: np.ndarray, target_points: int = 50) -> np.ndarray:
        N = len(t_array)
        num_channels = data.shape[1]
        if N < 2:
            return np.zeros((target_points, num_channels))
        
        t_target = np.linspace(t_array[0], t_array[-1], target_points)
        resampled = np.zeros((target_points, num_channels))
        for i in range(num_channels):
            resampled[:, i] = np.interp(t_target, t_array, data[:, i])
        return resampled

    def _compute_dtw_distance(self, s1: np.ndarray, s2: np.ndarray) -> float:
        """
        Computes the Dynamic Time Warping (DTW) alignment cost between s1 and s2.
        Normalizes by (N + M) to keep the distance metric independent of sampling length.
        """
        N, C = s1.shape
        M, _ = s2.shape
        
        # Pairwise distance matrix
        diff = s1[:, np.newaxis, :] - s2[np.newaxis, :, :]  # (N, M, C)
        dist_matrix = np.linalg.norm(diff, axis=2)          # (N, M)
        
        # DP table initialization
        dtw = np.full((N + 1, M + 1), float('inf'))
        dtw[0, 0] = 0.0
        
        for i in range(1, N + 1):
            for j in range(1, M + 1):
                cost = dist_matrix[i - 1, j - 1]
                dtw[i, j] = cost + min(dtw[i - 1, j],     # insertion
                                       dtw[i, j - 1],     # deletion
                                       dtw[i - 1, j - 1]) # match
                                       
        return float(dtw[N, M] / (N + M))

    def _save_trajectory_example(self, label: str, channels: List[str], flat_vector: List[float], midi_channel: int = 1, midi_cc: int = 22):
        with self.lock:
            # Check if an example with the same label already exists
            existing = None
            for item in self.trajectories_list:
                if item["label"] == label:
                    existing = item
                    break
            
            if existing:
                # If "vectors" is not in existing, initialize with the old "vector"
                if "vectors" not in existing:
                    existing["vectors"] = [existing["vector"]]
                
                existing["vectors"].append(flat_vector)
                existing["vector"] = flat_vector
                existing["timestamp"] = time.time()
                # Keep channels in sync in case they changed
                existing["channels"] = channels
                print(f"Added variant to existing gesture '{label}'. Total variants: {len(existing['vectors'])}")
            else:
                example_id = f"traj_{int(time.time())}"
                entry = {
                    "id": example_id,
                    "label": label,
                    "timestamp": time.time(),
                    "channels": channels,
                    "vector": flat_vector,
                    "vectors": [flat_vector],
                    "midi_channel": midi_channel,
                    "midi_cc": midi_cc,
                    "midi_note": 60,
                    "midi_type": "cc"  # "cc" or "note"
                }
                self.trajectories_list.append(entry)
                print(f"Saved new trajectory example for '{label}' with {len(flat_vector)} size (ch {midi_channel}, cc {midi_cc})")
                
            self._save_json_index(self.trajectories_index_path, self.trajectories_list)

    def update_trajectory_midi_params(self, traj_id: str, midi_channel: int, midi_cc: int, midi_note: int, midi_type: str) -> bool:
        with self.lock:
            for item in self.trajectories_list:
                if item["id"] == traj_id:
                    item["midi_channel"] = midi_channel
                    item["midi_cc"] = midi_cc
                    item["midi_note"] = midi_note
                    item["midi_type"] = midi_type
                    self._save_json_index(self.trajectories_index_path, self.trajectories_list)
                    return True
            return False

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

    def discard_last_trajectory_variant(self, label: str) -> Dict[str, Any]:
        """Discards the most recently added variant (or the entire template if only 1 exists) for a label."""
        with self.lock:
            found = None
            for item in self.trajectories_list:
                if item["label"] == label:
                    found = item
                    break
            
            if not found:
                return {"status": "error", "message": f"No template found with label '{label}'"}
            
            # Reconstruct or verify the vectors list
            if "vectors" not in found or not found["vectors"]:
                found["vectors"] = [found["vector"]]
                
            if len(found["vectors"]) <= 1:
                # Only 1 variant remains, delete the whole template
                self.trajectories_list.remove(found)
                self._save_json_index(self.trajectories_index_path, self.trajectories_list)
                return {"status": "deleted", "message": f"Discarded only variant. Entire gesture template '{label}' removed."}
            else:
                # Remove the last variant
                discarded = found["vectors"].pop()
                # Update current active fallback vector to the previous variant
                found["vector"] = found["vectors"][-1]
                found["timestamp"] = time.time()
                self._save_json_index(self.trajectories_index_path, self.trajectories_list)
                return {
                    "status": "success", 
                    "message": f"Discarded last variant for '{label}'. Remaining variants: {len(found['vectors'])}",
                    "remaining": len(found["vectors"])
                }

    def _recognize_trajectory(self, channels: List[str], test_vector: List[float]):
        """Compares test_vector with stored examples matching the same channels using DTW."""
        with self.lock:
            # Check recognition hold cooldown
            now = time.time()
            last_trig_time = getattr(self, "last_recognition_trigger_time", 0.0)
            hold_duration = config_manager.config.get("trajectory", {}).get("recognition_hold", 1.0)
            if now - last_trig_time < hold_duration:
                # Still within hold cooldown window, retain the last recognized gesture or stay in cooldown status
                if getattr(self, "last_recognized_label", None):
                    self.recognition_result = f"{self.last_recognized_label} (Hold: {hold_duration - (now - last_trig_time):.1f}s)"
                    self.recognition_triggered = True
                else:
                    self.recognition_result = f"Hold Cooldown ({hold_duration - (now - last_trig_time):.1f}s)"
                    self.recognition_triggered = False
                return

            examples = [ex for ex in self.trajectories_list if ex["channels"] == channels]
            
            if not examples:
                print("No matching trajectory examples found for channel set:", channels)
                self.recognition_result = "No matching templates"
                self.recognition_distance = 0.0
                return

            best_match = None
            min_dist = float("inf")
            
            # Reconstruct test matrix from flattened vector
            test_np = np.array(test_vector).reshape(-1, len(channels))

            for ex in examples:
                variants = ex.get("vectors")
                if not variants:
                    variants = [ex["vector"]]
                
                for variant in variants:
                    # Reconstruct template matrix from flattened vector
                    ex_np = np.array(variant).reshape(-1, len(channels))
                    
                    # Compute Dynamic Time Warping distance
                    dist = self._compute_dtw_distance(test_np, ex_np)
                    if dist < min_dist:
                        min_dist = dist
                        best_match = ex

            # Retrieve recognition threshold from configuration (default is high, user configured)
            # Default threshold for DTW is configured, e.g. 1.0 or 2.0
            config_threshold = config_manager.config.get("trajectory", {}).get("recognition_threshold", 15.0)
            
            self.recognition_distance = float(min_dist)
            
            if min_dist <= config_threshold and best_match:
                label = best_match["label"]
                self.recognition_result = label
                self.recognition_triggered = True
                
                # Edge triggered trigger action (only on change)
                if getattr(self, "last_recognized_label", None) != label:
                    print(f"Trajectory RECOGNIZED via DTW: '{label}' (distance: {min_dist:.4f} <= threshold {config_threshold:.2f})")
                    self._trigger_recognition_action(label)
                    self.last_recognized_label = label
                    self.last_recognition_trigger_time = now
            else:
                closest_label = best_match["label"] if best_match else "Unknown"
                self.recognition_result = f"None (Closest: '{closest_label}' with distance {min_dist:.2f} > threshold {config_threshold:.2f})"
                self.recognition_triggered = False
                
                if getattr(self, "last_recognized_label", None) is not None:
                    print(f"Trajectory NOT recognized anymore via DTW. Closest was '{closest_label}' distance: {min_dist:.2f} > threshold {config_threshold:.2f}")
                    self.last_recognized_label = None

    def _trigger_recognition_action(self, label: str):
        """Triggers the configured OSC/MIDI action on successful recognition."""
        traj_config = config_manager.config.get("trajectory", {})
        action = traj_config.get("action", {})
        action_type = action.get("type", "osc")
        
        # Find the actual trajectory example to read its specific MIDI configurations
        matched_traj = None
        with self.lock:
            for item in self.trajectories_list:
                if item["label"] == label:
                    matched_traj = item
                    break

        if action_type == "osc":
            host = action.get("host", "127.0.0.1")
            port = action.get("port", 9001)
            address = action.get("address", "/motion/recognized")
            # Send the recognized label as a string argument
            osc_receiver.send_osc_message(host, port, address, label)
            print(f"Recognition OSC action triggered: sending '{label}' to {host}:{port} {address}")
        elif action_type == "midi":
            port_name = action.get("port_name", "")
            if not port_name:
                port_name = config_manager.get("midi", {}).get("port_name", "")
            
            # Use specific template's MIDI settings or fallback to globals
            channel = 1
            cc_num = 22
            note_num = 60
            midi_type = "cc"
            
            if matched_traj:
                channel = matched_traj.get("midi_channel", 1)
                cc_num = matched_traj.get("midi_cc", 22)
                note_num = matched_traj.get("midi_note", 60)
                midi_type = matched_traj.get("midi_type", "cc")
            else:
                channel = action.get("channel", 1)
                cc_num = action.get("cc", 22)
            
            value = action.get("value", 127)
            
            from midi_io import midi_manager
            if midi_type == "cc":
                midi_manager.send_cc(port_name, channel, cc_num, value)
                print(f"Recognition MIDI CC action triggered for '{label}': sending CC {cc_num} val {value} on channel {channel} to port '{port_name}'")
            elif midi_type == "note":
                midi_manager.send_note_on_off(port_name, channel, note_num, value)
                print(f"Recognition MIDI Note action triggered for '{label}': sending Note {note_num} vel {value} on channel {channel} to port '{port_name}'")

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
                "is_recording_example": getattr(self, "is_recording_example", False),
                "recognition_active": getattr(self, "recognition_active", False),
                "countdown": countdown,
                "recognition_result": self.recognition_result,
                "recognition_distance": self.recognition_distance,
                "recognition_triggered": self.recognition_triggered
            }

# Global trajectory manager instance
trajectory_manager = TrajectoryManager()
