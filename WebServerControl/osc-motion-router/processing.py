import math
import time
import threading
from typing import List, Dict, Any, Optional
from osc_io import osc_receiver
from midi_io import midi_manager

class RouteRuntime:
    def __init__(self, route_config: Dict[str, Any]):
        self.route_id = route_config.get("id")
        self.config = route_config
        self.processors_state: List[Dict[str, Any]] = [{} for _ in route_config.get("processors", [])]
        self.last_sent_value: Optional[Any] = None
        self.last_sent_time: float = 0.0
        self.cooked_value: float = 0.0

    def reset(self, route_config: Dict[str, Any]):
        self.config = route_config
        self.processors_state = [{} for _ in route_config.get("processors", [])]
        self.last_sent_value = None
        self.last_sent_time = 0.0
        self.cooked_value = 0.0

class RouteProcessor:
    def __init__(self):
        self.lock = threading.Lock()
        self.runtimes: Dict[str, RouteRuntime] = {}
        # Stores the latest cooked value for each route
        self.cooked_values: Dict[str, float] = {}

    def sync_routes(self, routes_config: List[Dict[str, Any]]):
        """Synchronizes runtime states with the latest configuration."""
        with self.lock:
            active_ids = set()
            for rc in routes_config:
                rid = rc.get("id")
                if not rid:
                    continue
                active_ids.add(rid)
                if rid not in self.runtimes:
                    self.runtimes[rid] = RouteRuntime(rc)
                else:
                    # Reset or update configuration
                    # If config is different, we can update it
                    if self.runtimes[rid].config != rc:
                        self.runtimes[rid].reset(rc)
            
            # Clean up deleted routes
            for rid in list(self.runtimes.keys()):
                if rid not in active_ids:
                    del self.runtimes[rid]
                    if rid in self.cooked_values:
                        del self.cooked_values[rid]

    def get_cooked_values(self) -> Dict[str, float]:
        with self.lock:
            return dict(self.cooked_values)

    def process_signals(self, updated_signals: List[str]):
        """Processes all active routes based on updated signals."""
        with self.lock:
            # We copy the runtimes list to avoid locking issues if some call tries to modify config
            runtimes_list = list(self.runtimes.values())

        for rt in runtimes_list:
            if not rt.config.get("enabled", True):
                continue

            source = rt.config.get("source", "")
            if not source:
                continue

            # Determine if this route needs to be processed
            should_process = False
            if source in updated_signals:
                should_process = True
            elif source == "accel.magnitude" and any(s.startswith("accel.") for s in updated_signals):
                should_process = True
            elif source == "gyro.magnitude" and any(s.startswith("gyro.") for s in updated_signals):
                should_process = True

            if not should_process:
                continue

            # 1. Fetch initial value
            val = self._get_source_value(source)
            if val is None:
                continue

            # 2. Run processor chain
            processors = rt.config.get("processors", [])
            for idx, p in enumerate(processors):
                state = rt.processors_state[idx]
                val = self._apply_processor(p, val, state)

            # Store the final cooked value
            with self.lock:
                rt.cooked_value = val
                self.cooked_values[rt.route_id] = val

            # 3. Handle routing output
            output_config = rt.config.get("output", {})
            out_type = output_config.get("type")
            if not out_type:
                continue

            now = time.time()
            time_since_last_send = now - rt.last_sent_time
            # Rate limit: max 100 messages/sec (10ms interval)
            if time_since_last_send < 0.01:
                continue

            if out_type == "midi_cc":
                # Convert value to integer MIDI range 0-127
                int_val = int(round(val))
                int_val = max(0, min(127, int_val))
                
                # Check if changed
                if rt.last_sent_value is None or rt.last_sent_value != int_val:
                    port_name = output_config.get("port_name", "")
                    if not port_name:
                        from config import config_manager
                        port_name = config_manager.get("midi", {}).get("port_name", "")
                    channel = output_config.get("channel", 1)
                    cc = output_config.get("cc", 0)
                    
                    success = midi_manager.send_cc(port_name, channel, cc, int_val)
                    if success:
                        rt.last_sent_value = int_val
                        rt.last_sent_time = now
                        
            elif out_type == "osc":
                host = output_config.get("host", "127.0.0.1")
                port = output_config.get("port", 9001)
                address = output_config.get("address", "/motion/out")
                send_on_change_only = output_config.get("send_on_change_only", True)
                
                # Check if changed
                if not send_on_change_only or rt.last_sent_value is None or abs(rt.last_sent_value - val) > 1e-5:
                    osc_receiver.send_osc_message(host, port, address, val)
                    rt.last_sent_value = val
                    rt.last_sent_time = now

    def _get_source_value(self, source: str) -> Optional[float]:
        # Lock when reading from latest_signals in osc_receiver
        with osc_receiver.lock:
            signals = osc_receiver.latest_signals
            if source in signals:
                return signals[source]
            elif source == "accel.magnitude":
                x = signals.get("accel.x", 0.0)
                y = signals.get("accel.y", 0.0)
                z = signals.get("accel.z", 0.0)
                return math.sqrt(x*x + y*y + z*z)
            elif source == "gyro.magnitude":
                x = signals.get("gyro.x", 0.0)
                y = signals.get("gyro.y", 0.0)
                z = signals.get("gyro.z", 0.0)
                return math.sqrt(x*x + y*y + z*z)
        return None

    def _apply_processor(self, p: Dict[str, Any], val: float, state: Dict[str, Any]) -> float:
        p_type = p.get("type")
        if p_type == "gain":
            gain = p.get("gain", 1.0)
            return val * gain
            
        elif p_type == "offset":
            offset = p.get("offset", 0.0)
            return val + offset
            
        elif p_type == "remap":
            input_min = p.get("input_min", 0.0)
            input_max = p.get("input_max", 1.0)
            output_min = p.get("output_min", 0.0)
            output_max = p.get("output_max", 127.0)
            clamp = p.get("clamp", True)
            
            if input_max == input_min:
                result = output_min
            else:
                result = output_min + (val - input_min) * (output_max - output_min) / (input_max - input_min)
                
            if clamp:
                min_out = min(output_min, output_max)
                max_out = max(output_min, output_max)
                result = max(min_out, min(result, max_out))
            return result
            
        elif p_type == "invert":
            return -val
            
        elif p_type == "smooth":
            alpha = p.get("alpha", 0.2)
            # Ensure alpha is within bounds
            alpha = max(0.0, min(1.0, alpha))
            
            prev = state.get("previous_value")
            if prev is None:
                state["previous_value"] = val
                return val
            else:
                smoothed = alpha * val + (1.0 - alpha) * prev
                state["previous_value"] = smoothed
                return smoothed
                
        elif p_type == "dead_zone":
            threshold = p.get("threshold", 0.1)
            if abs(val) < threshold:
                return 0.0
            return val
            
        elif p_type == "threshold_event":
            threshold = p.get("threshold", 0.5)
            direction = p.get("direction", "rising")  # rising, falling, either
            cooldown = p.get("cooldown", 100.0)  # in ms
            
            now = time.time()
            last_val = state.get("last_value")
            last_trigger = state.get("last_trigger_time", 0.0)
            triggered = False
            
            if last_val is not None:
                cooldown_sec = cooldown / 1000.0
                is_cooldown_over = (now - last_trigger) >= cooldown_sec
                
                is_rising = last_val < threshold <= val
                is_falling = last_val > threshold >= val
                
                if direction == "rising" and is_rising:
                    if is_cooldown_over:
                        triggered = True
                elif direction == "falling" and is_falling:
                    if is_cooldown_over:
                        triggered = True
                elif direction == "either" and (is_rising or is_falling):
                    if is_cooldown_over:
                        triggered = True
            
            state["last_value"] = val
            if triggered:
                state["last_trigger_time"] = now
                return 1.0
            else:
                return 0.0
                
        return val

# Global route processor instance
route_processor = RouteProcessor()

# Connect the callback in osc_receiver
osc_receiver.set_on_signal_update(route_processor.process_signals)
