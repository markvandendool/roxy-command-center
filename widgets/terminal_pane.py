#!/usr/bin/env python3
"""
Terminal pane widget with command history.
ROXY-CMD-STORY-022: Embedded terminal for service actions.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango, Gdk
import subprocess
import threading
from collections import deque
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CommandEntry:
    """A command and its output."""
    command: str
    output: str
    exit_code: int
    timestamp: datetime
    duration_ms: int = 0


class TerminalPane(Gtk.Box):
    """
    Terminal pane with command history and output display.
    
    Features:
    - Command input with history
    - Scrollable output
    - Color-coded status
    - Copy output
    """
    
    MAX_HISTORY = 50
    
    def __init__(self, on_command: Optional[Callable[[str], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("terminal-pane")
        
        self.on_command_callback = on_command
        self._history: deque = deque(maxlen=self.MAX_HISTORY)
        self._history_index = -1
        self._is_running = False
        
        self._build_ui()
    
    def _build_ui(self):
        # Output area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.append(scrolled)
        
        # Text view for output
        self.output_view = Gtk.TextView()
        self.output_view.set_editable(False)
        self.output_view.set_cursor_visible(False)
        self.output_view.set_monospace(True)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.output_view.set_left_margin(8)
        self.output_view.set_right_margin(8)
        self.output_view.set_top_margin(8)
        self.output_view.set_bottom_margin(8)
        self.output_view.add_css_class("terminal-output")
        scrolled.set_child(self.output_view)
        
        # Get text buffer
        self.buffer = self.output_view.get_buffer()
        
        # Create tags for formatting
        self.tag_command = self.buffer.create_tag(
            "command", 
            foreground="#7c3aed",
            weight=Pango.Weight.BOLD
        )
        self.tag_success = self.buffer.create_tag(
            "success",
            foreground="#22c55e"
        )
        self.tag_error = self.buffer.create_tag(
            "error",
            foreground="#ef4444"
        )
        self.tag_timestamp = self.buffer.create_tag(
            "timestamp",
            foreground="#6b7280",
            scale=0.9
        )
        
        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)
        
        # Input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_box.set_margin_top(8)
        input_box.set_margin_bottom(8)
        input_box.set_margin_start(8)
        input_box.set_margin_end(8)
        self.append(input_box)
        
        # Prompt label
        prompt = Gtk.Label(label="$")
        prompt.add_css_class("monospace")
        input_box.append(prompt)
        
        # Command entry
        self.entry = Gtk.Entry()
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("Enter command...")
        self.entry.add_css_class("monospace")
        self.entry.connect("activate", self._on_entry_activate)
        input_box.append(self.entry)
        
        # Key controller for history navigation
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.entry.add_controller(key_controller)
        
        # Run button
        self.run_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.run_btn.set_tooltip_text("Run command")
        self.run_btn.connect("clicked", self._on_run_clicked)
        input_box.append(self.run_btn)
        
        # Clear button
        clear_btn = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic")
        clear_btn.set_tooltip_text("Clear output")
        clear_btn.connect("clicked", self._on_clear_clicked)
        input_box.append(clear_btn)
        
        # Add welcome message
        self._append_text("Roxy Command Center Terminal\n", self.tag_timestamp)
        self._append_text("Type a command or use quick actions from the panels.\n\n", self.tag_timestamp)
    
    def _on_entry_activate(self, entry):
        """Handle Enter key in entry."""
        command = entry.get_text().strip()
        if command:
            self.run_command(command)
            entry.set_text("")
    
    def _on_run_clicked(self, button):
        """Handle run button click."""
        command = self.entry.get_text().strip()
        if command:
            self.run_command(command)
            self.entry.set_text("")
    
    def _on_clear_clicked(self, button):
        """Clear output."""
        self.buffer.set_text("")
    
    def _on_key_pressed(self, controller, keyval, keycode, state) -> bool:
        """Handle key presses for history navigation."""
        if keyval == Gdk.KEY_Up:
            self._navigate_history(-1)
            return True
        elif keyval == Gdk.KEY_Down:
            self._navigate_history(1)
            return True
        return False
    
    def _navigate_history(self, direction: int):
        """Navigate command history."""
        if not self._history:
            return
        
        if self._history_index == -1:
            # Starting from current input
            if direction == -1:
                self._history_index = len(self._history) - 1
            else:
                return
        else:
            new_index = self._history_index + direction
            if 0 <= new_index < len(self._history):
                self._history_index = new_index
            elif direction == 1:
                self._history_index = -1
                self.entry.set_text("")
                return
            else:
                return
        
        if 0 <= self._history_index < len(self._history):
            cmd = list(self._history)[self._history_index].command
            self.entry.set_text(cmd)
            self.entry.set_position(-1)
    
    def run_command(self, command: str):
        """Run a command asynchronously."""
        if self._is_running:
            self._append_text("Command already running...\n", self.tag_error)
            return
        
        self._is_running = True
        self._history_index = -1
        self.run_btn.set_sensitive(False)
        self.entry.set_sensitive(False)
        
        # Display command
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_text(f"[{timestamp}] ", self.tag_timestamp)
        self._append_text(f"$ {command}\n", self.tag_command)
        
        # Notify callback
        if self.on_command_callback:
            self.on_command_callback(command)
        
        # Run in thread
        start_time = GLib.get_monotonic_time()
        
        def run_async():
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                output = result.stdout + result.stderr
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                output = "Command timed out after 60 seconds"
                exit_code = -1
            except Exception as e:
                output = str(e)
                exit_code = -1
            
            duration_ms = (GLib.get_monotonic_time() - start_time) // 1000
            
            GLib.idle_add(
                self._on_command_complete,
                command, output, exit_code, duration_ms
            )
        
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
    
    def _on_command_complete(self, command: str, output: str, exit_code: int, duration_ms: int):
        """Handle command completion."""
        self._is_running = False
        self.run_btn.set_sensitive(True)
        self.entry.set_sensitive(True)
        self.entry.grab_focus()
        
        # Add to history
        entry = CommandEntry(
            command=command,
            output=output,
            exit_code=exit_code,
            timestamp=datetime.now(),
            duration_ms=duration_ms
        )
        self._history.append(entry)
        
        # Display output
        if output:
            self._append_text(output)
            if not output.endswith("\n"):
                self._append_text("\n")
        
        # Display status
        if exit_code == 0:
            self._append_text(f"✓ Completed in {duration_ms}ms\n\n", self.tag_success)
        else:
            self._append_text(f"✗ Exit code: {exit_code} ({duration_ms}ms)\n\n", self.tag_error)
        
        # Scroll to end
        self._scroll_to_end()
        
        return False
    
    def _append_text(self, text: str, tag=None):
        """Append text to output buffer."""
        end_iter = self.buffer.get_end_iter()
        if tag:
            self.buffer.insert_with_tags(end_iter, text, tag)
        else:
            self.buffer.insert(end_iter, text)
    
    def _scroll_to_end(self):
        """Scroll output to end."""
        mark = self.buffer.get_insert()
        self.output_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
    
    def run_quick_command(self, label: str, command: str):
        """Run a predefined quick command."""
        self._append_text(f"[Quick Action: {label}]\n", self.tag_timestamp)
        self.run_command(command)


class QuickActionsBar(Gtk.Box):
    """
    Quick action buttons for common commands.
    """
    
    def __init__(self, terminal: TerminalPane):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.terminal = terminal
        self.add_css_class("quick-actions")
        
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        
        # Label
        label = Gtk.Label(label="Quick:")
        label.add_css_class("dim-label")
        self.append(label)
        
        # Add quick action buttons
        quick_actions = [
            ("Status", "systemctl --user status"),
            ("Journal", "journalctl --user -n 50 --no-pager"),
            ("Top", "top -bn1 | head -20"),
            ("GPU", "cat /sys/class/drm/card*/device/gpu_busy_percent 2>/dev/null || nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader"),
            ("Ollama", "curl -s http://localhost:11434/api/tags | jq -r '.models[].name' 2>/dev/null || echo 'Ollama not responding'"),
        ]
        
        for label_text, command in quick_actions:
            btn = Gtk.Button(label=label_text)
            btn.add_css_class("flat")
            btn.add_css_class("pill")
            btn.connect("clicked", self._on_quick_action, label_text, command)
            self.append(btn)
    
    def _on_quick_action(self, button, label: str, command: str):
        """Handle quick action button click."""
        self.terminal.run_quick_command(label, command)


class TerminalPage(Gtk.Box):
    """
    Full terminal page with quick actions.
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Terminal pane
        self.terminal = TerminalPane()
        self.terminal.set_vexpand(True)
        self.append(self.terminal)
        
        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)
        
        # Quick actions
        quick_actions = QuickActionsBar(self.terminal)
        self.append(quick_actions)
    
    def run_command(self, command: str):
        """Run a command in the terminal."""
        self.terminal.run_command(command)
