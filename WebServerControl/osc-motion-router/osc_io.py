import time
import socket
import threading
import sys
from typing import Any, Dict, List, Tuple
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

class OSCReceiverManager:
    def __init__(self):
        self.lock = threading.Lock()
        
        # Signal State
        self.latest_signals = {
            "accel.x": 0.0,
            "accel.y": 0.0,
            "accel.z": 0.0,
            "gyro.x": 0.0,
            "gyro.y": 0.0,
            "gyro.z": 0.0
        }
        self.latest_timestamp = 0.0
        self.packet_count = 0
        self.packet_rate = 0.0
        self.last_error = ""
        
        # Recent observed messages for monitor (max 100)
        self.observed_messages: List[Dict[str, Any]] = []
        
        # Rolling packet timestamps for rate calculation (last 2 seconds)
        self.packet_timestamps: List[float] = []
        
        # Server reference
        self.server: BlockingOSCUDPServer = None
        self.server_thread: threading.Thread = None
        self.running = False
        
        # Clients cache for OSC outputs
        self.clients_lock = threading.Lock()
        self.clients: Dict[Tuple[str, int], SimpleUDPClient] = {}
        
        # Route processing callback
        self.on_signal_update_callback = None

    def set_on_signal_update(self, callback):
        self.on_signal_update_callback = callback

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            # Clean old packet timestamps to update rate
            self._update_packet_rate_unlocked()
            return {
                "running": self.running,
                "latest_timestamp": self.latest_timestamp,
                "packet_count": self.packet_count,
                "packet_rate": self.packet_rate,
                "last_error": self.last_error,
                "latest_signals": dict(self.latest_signals)
            }

    def get_observed_messages(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.observed_messages)

    def send_osc_message(self, host: str, port: int, address: str, value: float):
        """Sends an OSC message containing a single float value."""
        try:
            key = (host, port)
            with self.clients_lock:
                if key not in self.clients:
                    self.clients[key] = SimpleUDPClient(host, port)
                client = self.clients[key]
            client.send_message(address, float(value))
        except Exception as e:
            print(f"Error sending OSC message to {host}:{port} {address}: {e}", file=sys.stderr)

    def clear_clients_cache(self):
        with self.clients_lock:
            self.clients.clear()

    def _update_packet_rate_unlocked(self):
        now = time.time()
        # Filter to keep only timestamps from the last 1.0 second
        self.packet_timestamps = [t for t in self.packet_timestamps if now - t <= 1.0]
        self.packet_rate = len(self.packet_timestamps)

    def _add_observed_message(self, address: str, args: List[Any], sender_ip: str):
        now_str = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
        msg = {
            "time": now_str,
            "ip": sender_ip,
            "address": address,
            "args": args
        }
        self.observed_messages.append(msg)
        if len(self.observed_messages) > 100:
            self.observed_messages.pop(0)

    def _handle_osc_message(self, address: str, args: List[Any], sender_ip: str, config: Dict[str, Any]):
        now = time.time()
        with self.lock:
            self.packet_count += 1
            self.packet_timestamps.append(now)
            self._update_packet_rate_unlocked()
            self.latest_timestamp = now
            self._add_observed_message(address, args, sender_ip)
            
            # Map input
            osc_in = config.get("osc_input", {})
            accel_addr = osc_in.get("accel_address", "/sensor/accel")
            gyro_addr = osc_in.get("gyro_address", "/sensor/gyro")
            fmt = osc_in.get("format", "grouped")
            
            updated_signals = []
            
            if fmt == "grouped":
                accel_indexes = osc_in.get("accel_indexes", [0, 1, 2])
                gyro_indexes = osc_in.get("gyro_indexes", [0, 1, 2])
                
                if address == accel_addr:
                    for i, axis in enumerate(["x", "y", "z"]):
                        if i < len(accel_indexes):
                            idx = accel_indexes[i]
                            if idx < len(args):
                                try:
                                    val = float(args[idx])
                                    self.latest_signals[f"accel.{axis}"] = val
                                    updated_signals.append(f"accel.{axis}")
                                except (ValueError, TypeError):
                                    pass
                if address == gyro_addr:
                    for i, axis in enumerate(["x", "y", "z"]):
                        if i < len(gyro_indexes):
                            idx = gyro_indexes[i]
                            if idx < len(args):
                                try:
                                    val = float(args[idx])
                                    self.latest_signals[f"gyro.{axis}"] = val
                                    updated_signals.append(f"gyro.{axis}")
                                except (ValueError, TypeError):
                                    pass
            else:  # separated format
                # Expect address to be e.g. /sensor/accel/x or /sensor/accel/y etc.
                if address == f"{accel_addr}/x" and len(args) > 0:
                    try:
                        self.latest_signals["accel.x"] = float(args[0])
                        updated_signals.append("accel.x")
                    except (ValueError, TypeError): pass
                elif address == f"{accel_addr}/y" and len(args) > 0:
                    try:
                        self.latest_signals["accel.y"] = float(args[0])
                        updated_signals.append("accel.y")
                    except (ValueError, TypeError): pass
                elif address == f"{accel_addr}/z" and len(args) > 0:
                    try:
                        self.latest_signals["accel.z"] = float(args[0])
                        updated_signals.append("accel.z")
                    except (ValueError, TypeError): pass
                elif address == f"{gyro_addr}/x" and len(args) > 0:
                    try:
                        self.latest_signals["gyro.x"] = float(args[0])
                        updated_signals.append("gyro.x")
                    except (ValueError, TypeError): pass
                elif address == f"{gyro_addr}/y" and len(args) > 0:
                    try:
                        self.latest_signals["gyro.y"] = float(args[0])
                        updated_signals.append("gyro.y")
                    except (ValueError, TypeError): pass
                elif address == f"{gyro_addr}/z" and len(args) > 0:
                    try:
                        self.latest_signals["gyro.z"] = float(args[0])
                        updated_signals.append("gyro.z")
                    except (ValueError, TypeError): pass
            
        # Call processing callback outside the lock to avoid deadlock if routes lock
        if updated_signals and self.on_signal_update_callback:
            self.on_signal_update_callback(updated_signals)

    def start(self, config: Dict[str, Any]):
        with self.lock:
            if self.running:
                return True
            
            osc_in = config.get("osc_input", {})
            bind_ip = osc_in.get("bind_ip", "0.0.0.0")
            port = osc_in.get("port", 9000)
            
            dispatcher = Dispatcher()
            
            # Catch all OSC messages
            def default_handler(address, *args):
                # Retrieve client IP if possible, else default
                # python-osc default_handler is passed (client_address, address, *args) if set up or just normal dispatcher logic.
                # Actually, dispatcher.map handles arguments. A dispatcher default handler takes:
                # (address, *args).
                # To get the sender ip, we can use a custom handler or map.
                # In python-osc, the server default handler can be mapped.
                # Let's map everything with a catch-all block.
                # Wait! Let's check python-osc default handler signature.
                # Standard dispatcher default handler is called as:
                # handler(address, *args)
                # But dispatcher has no default way to pass sender IP unless we customize.
                # Wait! python-osc's blocking server can use a dispatcher that handles this,
                # or we can inspect dispatcher code or override.
                # Wait, if we use dispatcher.set_default_handler, it is called with:
                # dispatcher.set_default_handler(default_handler) -> handler(address, *args)
                # How do we get the sender's IP?
                # Actually, blocking server handles incoming packets and passes them to dispatcher.
                # If we inspect `BlockingOSCUDPServer`'s handler, it calls dispatcher with message.
                # But wait, python-osc has been updated, and we can register a dispatcher function.
                # Let's check how we can get sender's IP or if we can just use "Unknown" if not easily accessible.
                # Wait! In python-osc, we can get client_address inside the handler if we use a server that passes it, or we can just bind to a standard socket and parse manually, OR python-osc BlockingOSCUDPServer actually has an underlying handle_request that doesn't easily expose the sender IP to the dispatcher callback.
                # Wait, is there a way to get it?
                # Let's look at python-osc: `dispatcher.map` takes handlers.
                # A handler receives the `address` and `*args`.
                # If we want the client address, can we get it?
                # python-osc dispatcher doesn't pass sender_ip directly. But wait!
                # We can write a custom subclass of OSCUDPServer or inspect the socket,
                # or we can just write "Local/Remote" or use a helper, or just use a dummy or "Unknown" sender IP or check if we can get it.
                # Wait, can we subclass the Dispatcher or blocking server?
                # Let's see: `BlockingOSCUDPServer` subclasses `socketserver.UDPServer`.
                # In standard `socketserver.UDPServer`, `self.client_address` is available on the request.
                # Inside `BlockingOSCUDPServer.verify_request` or `finish_request`, we have it.
                # But actually, simpler is: python-osc's message parser is fully accessible, or we can just use "Unknown" or get it from socket if needed.
                # Wait! Let's look at `BlockingOSCUDPServer`'s callback system.
                # A handler in python-osc can be mapped like:
                # `dispatcher.map("/address", handler, needs_reply_address=True)` or something? No, that's not standard.
                # Actually, we can get the sender IP easily if we subclass `BlockingOSCUDPServer` or if we override `finish_request`!
                # Let's see how `BlockingOSCUDPServer` is implemented. It overrides `finish_request` to call `_inspect_and_dispatch` or similar:
                # ```python
                # def finish_request(self, request, client_address):
                #     self.client_address = client_address # we can store it in a thread-local or on the server instance!
                #     super().finish_request(request, client_address)
                # ```
                # Wait, yes! Inside the server handler, we can store `client_address` on the server instance itself (using a thread local since it's a blocking single-threaded server, or just an attribute since it runs sequentially in its own thread).
                # That is extremely simple and brilliant! Let's do that.
                pass
            
            class CustomOSCServer(BlockingOSCUDPServer):
                def __init__(self, server_address, dispatcher):
                    super().__init__(server_address, dispatcher)
                    self.current_client_address = None

                def finish_request(self, request, client_address):
                    self.current_client_address = client_address
                    try:
                        super().finish_request(request, client_address)
                    finally:
                        self.current_client_address = None

            def catch_all_handler(address, *args):
                # Retrieve client IP
                sender_ip = "Unknown"
                if self.server and self.server.current_client_address:
                    sender_ip = self.server.current_client_address[0]
                
                # Call handle_osc_message
                self._handle_osc_message(address, list(args), sender_ip, config)

            dispatcher.set_default_handler(catch_all_handler)
            
            try:
                self.server = CustomOSCServer((bind_ip, port), dispatcher)
                self.last_error = ""
            except Exception as e:
                self.last_error = f"Failed to bind OSC input to {bind_ip}:{port} - {e}"
                print(self.last_error, file=sys.stderr)
                self.server = None
                return False
            
            self.running = True
            
            def run_server():
                try:
                    self.server.serve_forever()
                except Exception as e:
                    print(f"OSC server loop error: {e}", file=sys.stderr)
                finally:
                    with self.lock:
                        self.running = False
                        self.server = None
            
            self.server_thread = threading.Thread(target=run_server, name="OSCReceiverThread", daemon=True)
            self.server_thread.start()
            print(f"OSC input server started on {bind_ip}:{port}")
            return True

    def stop(self):
        with self.lock:
            if not self.running or not self.server:
                return
            
            # Shutdown the server
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                print(f"Error shutting down OSC server: {e}", file=sys.stderr)
            
            self.running = False
            self.server = None
            self.server_thread = None
            print("OSC input server stopped")

# Global osc receiver manager instance
osc_receiver = OSCReceiverManager()
