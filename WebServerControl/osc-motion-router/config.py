import os
import sys
import json
import shutil
import threading
from typing import Any, Dict

DEFAULT_CONFIG = {
    "web_port": 8765,
    "osc_input": {
        "enabled": True,
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

class ConfigManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.data_dir = self._get_data_dir()
        self.config_path = os.path.join(self.data_dir, "config.json")
        self.recordings_dir = os.path.join(self.data_dir, "recordings")
        
        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.recordings_dir, exist_ok=True)
        
        self.config = {}
        self.load()
        
        # For debounce saving
        self._save_timer = None
        self._save_debounce_delay = 0.3  # 300ms

    def _get_data_dir(self) -> str:
        if getattr(sys, 'frozen', False):
            if sys.platform == 'win32':
                base_dir = os.environ.get('APPDATA', os.path.expanduser('~'))
                return os.path.join(base_dir, 'OscMotionRouter')
            elif sys.platform == 'darwin':
                return os.path.expanduser('~/Library/Application Support/OscMotionRouter')
            else:
                return os.path.expanduser('~/.local/share/osc-motion-router')
        else:
            # Under osc-motion-router/data in dev mode
            current_dir = os.path.dirname(os.path.abspath(__file__))
            return os.path.join(current_dir, "data")

    def load(self):
        with self.lock:
            if not os.path.exists(self.config_path):
                self.config = json.loads(json.dumps(DEFAULT_CONFIG)) # deep copy
                self._save_atomic_unlocked()
            else:
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    self.config = self._validate_and_merge(loaded, DEFAULT_CONFIG)
                except Exception as e:
                    print(f"Error loading config, using defaults: {e}", file=sys.stderr)
                    self.config = json.loads(json.dumps(DEFAULT_CONFIG))
                    self._save_atomic_unlocked()

    def _validate_and_merge(self, loaded: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively validate and merge config to ensure all defaults are present."""
        merged = {}
        for key, val in defaults.items():
            if key not in loaded:
                merged[key] = json.loads(json.dumps(val))
            elif isinstance(val, dict) and isinstance(loaded[key], dict):
                merged[key] = self._validate_and_merge(loaded[key], val)
            else:
                merged[key] = loaded[key]
        # Also preserve any top-level key that is not in defaults (if any)
        for key, val in loaded.items():
            if key not in merged:
                merged[key] = val
        return merged

    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            return self.config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.config))

    def update_all(self, new_config: Dict[str, Any]):
        with self.lock:
            # Validate and merge the new config with our existing config structure
            self.config = self._validate_and_merge(new_config, DEFAULT_CONFIG)
        self.save_debounced()

    def update_key(self, key: str, value: Any):
        with self.lock:
            self.config[key] = value
        self.save_debounced()

    def save_debounced(self):
        with self.lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(self._save_debounce_delay, self._save_atomic)
            self._save_timer.start()

    def _save_atomic(self):
        with self.lock:
            self._save_atomic_unlocked()

    def _save_atomic_unlocked(self):
        tmp_path = self.config_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            shutil.move(tmp_path, self.config_path)
        except Exception as e:
            print(f"Error writing configuration atomically: {e}", file=sys.stderr)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def save_immediate(self):
        with self.lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            self._save_atomic_unlocked()

# Global config manager instance
config_manager = ConfigManager()
