import os
import sys
import threading
from typing import Dict, List, Type
from config import config_manager

class BasePlugin:
    plugin_id: str = "base"
    name: str = "Base Plugin"
    description: str = "Base plugin class"

    def initialize(self, app) -> None:
        pass

    def process_signals(self, signals: Dict[str, float], updated_signals: List[str]) -> None:
        pass

    def shutdown(self) -> None:
        pass


class PluginManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.plugins_classes: List[Type[BasePlugin]] = []
        self.active_plugins: Dict[str, BasePlugin] = {}
        self.initialized = False

    def register_plugin_class(self, cls: Type[BasePlugin]):
        """Registers a plugin class to be loaded if enabled."""
        with self.lock:
            if cls not in self.plugins_classes:
                self.plugins_classes.append(cls)

    def load_and_initialize(self, app):
        """Loads and initializes all enabled registered plugins."""
        with self.lock:
            if self.initialized:
                return
            
            # Fetch enabled/disabled configuration
            plugins_config = config_manager.config.get("plugins", {})
            
            # Save any missing default configurations
            config_updated = False
            for cls in self.plugins_classes:
                pid = cls.plugin_id
                if pid not in plugins_config:
                    plugins_config[pid] = True
                    config_updated = True
            
            if config_updated:
                config_manager.update_key("plugins", plugins_config)
                config_manager.save_immediate()
            
            for cls in self.plugins_classes:
                pid = cls.plugin_id
                is_enabled = plugins_config.get(pid, True)
                
                if is_enabled:
                    try:
                        print(f"Loading plugin: {cls.name} ({pid})...")
                        instance = cls()
                        instance.initialize(app)
                        self.active_plugins[pid] = instance
                    except Exception as e:
                        print(f"Error initializing plugin '{pid}': {e}", file=sys.stderr)
            
            self.initialized = True

    def process_signals(self, signals: Dict[str, float], updated_signals: List[str]):
        """Dispatches real-time signal values to all active plugins."""
        # Avoid locking in real-time loop if possible, or keep it short.
        # We can copy the active plugins list to run safely.
        with self.lock:
            if not self.initialized:
                return
            plugins = list(self.active_plugins.values())
            
        for plugin in plugins:
            try:
                plugin.process_signals(signals, updated_signals)
            except Exception as e:
                # We do not want one failing plugin to crash the entire thread callback
                print(f"Error running process_signals in plugin '{plugin.plugin_id}': {e}", file=sys.stderr)

    def shutdown(self):
        """Shuts down all loaded active plugins."""
        with self.lock:
            for pid, plugin in list(self.active_plugins.items()):
                try:
                    print(f"Shutting down plugin: {plugin.name}...")
                    plugin.shutdown()
                except Exception as e:
                    print(f"Error during shutdown of plugin '{pid}': {e}", file=sys.stderr)
            self.active_plugins.clear()
            self.initialized = False

# Global plugin manager instance
plugin_manager = PluginManager()
