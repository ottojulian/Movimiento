import sys
import threading
import time
from typing import List, Dict, Any, Optional
import mido

class MIDIManager:
    def __init__(self):
        self.lock = threading.Lock()
        # Cache of open output ports: port_name -> open_port_object
        self.open_ports: Dict[str, Any] = {}
        self.last_error = ""

    def get_output_ports(self) -> List[str]:
        """Lists available MIDI output port names."""
        try:
            # mido.get_output_names() returns duplicates sometimes, let's deduplicate while preserving order
            ports = []
            for name in mido.get_output_names():
                if name not in ports:
                    ports.append(name)
            return ports
        except Exception as e:
            self.last_error = f"Error listing MIDI ports: {e}"
            print(self.last_error, file=sys.stderr)
            return []

    def _get_or_open_port(self, port_name: str) -> Optional[Any]:
        """Gets an open port from cache or attempts to open it. Thread-safe."""
        if not port_name:
            return None
            
        with self.lock:
            if port_name in self.open_ports:
                self.last_error = ""
                return self.open_ports[port_name]
            
            try:
                # Open port using mido
                # python-rtmidi is used in the background as mido backend
                port = mido.open_output(port_name)
                self.open_ports[port_name] = port
                print(f"Successfully opened MIDI port: {port_name}")
                self.last_error = ""
                return port
            except Exception as e:
                self.last_error = f"Failed to open MIDI port '{port_name}': {e}"
                print(self.last_error, file=sys.stderr)
                return None

    def send_cc(self, port_name: str, channel: int, cc: int, value: int) -> bool:
        """
        Sends a MIDI CC message to the specified port.
        channel is 1-indexed (1-16), mido uses 0-indexed (0-15).
        value is 0-127.
        Returns True if successful, False otherwise.
        """
        port = self._get_or_open_port(port_name)
        if not port:
            return False
            
        try:
            # Construct MIDI message
            # Channel is 0-15 in mido, convert from 1-16
            mido_channel = max(0, min(15, channel - 1))
            msg = mido.Message('control_change', channel=mido_channel, control=cc, value=value)
            port.send(msg)
            return True
        except Exception as e:
            self.last_error = f"Error sending MIDI message to '{port_name}': {e}"
            print(self.last_error, file=sys.stderr)
            # Remove from cache since it might be disconnected
            with self.lock:
                if port_name in self.open_ports:
                    try:
                        self.open_ports[port_name].close()
                    except Exception:
                        pass
                    del self.open_ports[port_name]
            return False

    def send_note_on_off(self, port_name: str, channel: int, note: int, velocity: int = 127, duration_sec: float = 0.1) -> bool:
        """
        Sends a MIDI Note On and then Note Off (after a short delay or synchronously)
        to the specified port.
        """
        port = self._get_or_open_port(port_name)
        if not port:
            return False
        try:
            mido_channel = max(0, min(15, channel - 1))
            msg_on = mido.Message('note_on', channel=mido_channel, note=note, velocity=velocity)
            port.send(msg_on)
            
            # Send note_off asynchronously to avoid blocking the main stream
            def send_off():
                time.sleep(duration_sec)
                try:
                    msg_off = mido.Message('note_off', channel=mido_channel, note=note, velocity=0)
                    port.send(msg_off)
                except Exception:
                    pass
            threading.Thread(target=send_off, daemon=True).start()
            return True
        except Exception as e:
            self.last_error = f"Error sending Note On to '{port_name}': {e}"
            print(self.last_error, file=sys.stderr)
            return False

    def close_all(self):
        """Closes all open MIDI ports."""
        with self.lock:
            for port_name, port in list(self.open_ports.items()):
                try:
                    port.close()
                    print(f"Closed MIDI port: {port_name}")
                except Exception as e:
                    print(f"Error closing MIDI port '{port_name}': {e}", file=sys.stderr)
            self.open_ports.clear()

# Global MIDI manager instance
midi_manager = MIDIManager()
