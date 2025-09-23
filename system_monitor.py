"""
Windows 11 System Monitor - Enhanced Edition
A resource-efficient system monitor for Windows 11 that displays battery and system information
in the taskbar and can create an optional overlay on screen.
"""

import sys
import os
import psutil
import wmi
import time
import threading
import ctypes
import socket
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, 
    QMainWindow, QVBoxLayout, QLabel, QDialog, 
    QSlider, QHBoxLayout, QCheckBox, QTabWidget,
    QPushButton, QComboBox, QGroupBox, QSpinBox,
    QRadioButton
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, pyqtSignal, QSize, QTime, QElapsedTimer
from PyQt6.QtGui import QIcon, QAction, QPainter, QColor, QPen, QFont, QPixmap, QImage, QFontMetrics, QRadialGradient

# Optional GPU monitoring
try:
    import GPUtil
    HAS_GPU_UTIL = True
except ImportError:
    HAS_GPU_UTIL = False

try:
    import py3nvml.py3nvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

class FPSCounter:
    """Counts frames per second efficiently"""
    def __init__(self, update_interval=1.0):
        self.update_interval = update_interval  # Update interval in seconds
        self.frame_count = 0
        self.fps = 0
        self.last_update_time = time.time()
        self.last_frame_time = time.time()
        self.frame_times = []  # Store last 100 frame times for calculating averages
        self.max_frame_times = 100
        self.running = True
        self.lock = threading.Lock()
        
        # Start the update thread
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
    
    
    def register_frame(self):
        """Register a new frame - call this as frequently as possible"""
        # Simple implementation without try/except to avoid overhead
        current_time = time.time()
        frame_time = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        with self.lock:
            self.frame_count += 1
            # Add frame time to list (for frame time calculation)
            self.frame_times.append(frame_time)
            if len(self.frame_times) > self.max_frame_times:
                self.frame_times.pop(0)
    
    def _update_loop(self):
        """Background thread that calculates FPS at regular intervals"""
        while self.running:
            time.sleep(self.update_interval)
            current_time = time.time()
            elapsed = current_time - self.last_update_time
            
            with self.lock:
                if elapsed > 0:
                    self.fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.last_update_time = current_time
    
    def get_fps(self):
        """Get the current FPS value"""
        with self.lock:
            return self.fps
    
    def get_frame_time(self):
        """Get the average frame time in milliseconds"""
        with self.lock:
            if not self.frame_times:
                return 0
            avg_frame_time = sum(self.frame_times) / len(self.frame_times)
            return avg_frame_time * 1000  # Convert to milliseconds
    
    def stop(self):
        """Stop the FPS counter"""
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)


class NetworkSpeedMonitor:
    """Monitor network speed in real-time"""
    def __init__(self):
        self.last_bytes_sent = 0
        self.last_bytes_recv = 0
        self.last_check_time = time.time()
        self.speed_up = 0  # bytes per second
        self.speed_down = 0  # bytes per second
    
    def update(self):
        """Update network speed measurements"""
        current_time = time.time()
        net_io = psutil.net_io_counters()
        
        # Calculate time difference
        time_diff = current_time - self.last_check_time
        
        # First update will just store values
        if self.last_bytes_sent > 0 and self.last_bytes_recv > 0:
            # Calculate bytes per second
            bytes_sent_diff = net_io.bytes_sent - self.last_bytes_sent
            bytes_recv_diff = net_io.bytes_recv - self.last_bytes_recv
            
            # Sometimes counters might reset or overflow
            if bytes_sent_diff >= 0 and bytes_recv_diff >= 0:
                self.speed_up = bytes_sent_diff / time_diff
                self.speed_down = bytes_recv_diff / time_diff
        
        # Update stored values
        self.last_bytes_sent = net_io.bytes_sent
        self.last_bytes_recv = net_io.bytes_recv
        self.last_check_time = current_time
        
        return {
            'speed_up': self.speed_up,
            'speed_down': self.speed_down
        }
    
    def get_speed_info(self):
        """Get current network speed information"""
        self.update()
        return {
            'speed_up': self.speed_up,
            'speed_down': self.speed_down
        }
    
    @staticmethod
    def format_speed(bytes_per_second):
        """Format network speed in a human-readable format"""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.1f} B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        elif bytes_per_second < 1024 * 1024 * 1024:
            return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024 * 1024):.1f} GB/s"


class SystemMonitor:
    """Class to monitor system resources with minimal overhead"""
    def __init__(self):
        self.wmi_interface = wmi.WMI()
        self.network_monitor = NetworkSpeedMonitor()
        self.fps_counter = FPSCounter()
        self.hostname = socket.gethostname()
        self.ip_address = self._get_ip_address()
        self.previous_cpu_times = None
        self.cpu_cores = psutil.cpu_count(logical=False)
        self.cpu_threads = psutil.cpu_count(logical=True)
        self.cpu_per_core = [0] * self.cpu_threads
        self._init_gpu_monitoring()
        
        # Start the FPS counter with direct connection
        self.fps_update_timer = QTimer()
        self.fps_update_timer.timeout.connect(self.fps_counter.register_frame)
        self.fps_update_timer.start(16)  # approximately 60 fps
    def _init_gpu_monitoring(self):
        """Initialize GPU monitoring based on available libraries"""
        self.has_gpu = False
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.nvml_device_count = nvml.nvmlDeviceGetCount()
                if self.nvml_device_count > 0:
                    self.has_gpu = True
                    self.gpu_type = "NVIDIA"
            except:
                pass
        
        if not self.has_gpu and HAS_GPU_UTIL:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    self.has_gpu = True
                    self.gpu_type = "AMD/Intel"
            except:
                pass
    
    def _get_ip_address(self):
        """Get the machine's IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # doesn't need to be reachable
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            s.close()
        except:
            ip = '127.0.0.1'
        return ip
    
    def get_battery_info(self):
        """Get battery information in an optimized way"""
        battery = psutil.sensors_battery()
        if not battery:
            return {
                'percent': 0,
                'power_plugged': True,
                'status': 'No Battery',
                'time_left': '∞'
            }
        
        # Calculate remaining time only if unplugged
        if battery.power_plugged:
            time_left = '∞'
            status = 'Charging' if battery.percent < 100 else 'Plugged In'
        else:
            # Only calculate time if actually discharging
            if battery.secsleft > 0:
                hours, remainder = divmod(battery.secsleft, 3600)
                minutes, _ = divmod(remainder, 60)
                time_left = f"{hours:02d}:{minutes:02d}"
            else:
                time_left = 'Calculating...'
            status = 'Discharging'
        
        return {
            'percent': battery.percent,
            'power_plugged': battery.power_plugged,
            'status': status,
            'time_left': time_left
        }
    
    def get_cpu_usage(self):
        """Get CPU usage optimized for minimal impact"""
        # Use interval=None for instantaneous reading
        return psutil.cpu_percent(interval=0.1)
    
    def get_cpu_per_core(self):
        """Get CPU usage per core/thread"""
        return psutil.cpu_percent(interval=0.1, percpu=True)
    
    def get_cpu_detailed(self):
        """Get detailed CPU information"""
        current_cpu_times = psutil.cpu_times_percent()
        
        result = {
            'usage': self.get_cpu_usage(),
            'cores': self.cpu_cores,
            'threads': self.cpu_threads,
            'per_core': self.get_cpu_per_core(),
            'user': current_cpu_times.user,
            'system': current_cpu_times.system,
            'idle': current_cpu_times.idle,
            'frequency': psutil.cpu_freq().current if psutil.cpu_freq() else 0
        }
        
        return result
    
    def get_memory_usage(self):
        """Get memory usage with minimal system impact"""
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            'percent': memory.percent,
            'used': self.format_bytes(memory.used),
            'total': self.format_bytes(memory.total),
            'used_bytes': memory.used,
            'total_bytes': memory.total,
            'swap_percent': swap.percent,
            'swap_used': self.format_bytes(swap.used),
            'swap_total': self.format_bytes(swap.total)
        }
    
    def get_disk_usage(self):
        """Get disk usage of the system drive"""
        disks = {}
        for partition in psutil.disk_partitions():
            if partition.fstype:  # Skip empty drives
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks[partition.mountpoint] = {
                        'percent': usage.percent,
                        'used': self.format_bytes(usage.used),
                        'total': self.format_bytes(usage.total),
                        'device': partition.device,
                        'fstype': partition.fstype
                    }
                except (PermissionError, FileNotFoundError):
                    # Some mountpoints might not be accessible
                    pass
        
        # Also get system drive
        system_drive = os.getenv('SystemDrive', 'C:')
        if system_drive + '\\' not in disks:
            try:
                usage = psutil.disk_usage(system_drive)
                disks[system_drive] = {
                    'percent': usage.percent,
                    'used': self.format_bytes(usage.used),
                    'total': self.format_bytes(usage.total),
                    'device': system_drive,
                    'fstype': 'System'
                }
            except:
                pass
                
        return disks
    
    def get_network_io(self):
        """Get current network I/O stats"""
        net_io = psutil.net_io_counters()
        speed_info = self.network_monitor.get_speed_info()
        
        return {
            'bytes_sent': self.format_bytes(net_io.bytes_sent),
            'bytes_recv': self.format_bytes(net_io.bytes_recv),
            'speed_up': self.network_monitor.format_speed(speed_info['speed_up']),
            'speed_down': self.network_monitor.format_speed(speed_info['speed_down']),
            'speed_up_raw': speed_info['speed_up'],
            'speed_down_raw': speed_info['speed_down'],
            'hostname': self.hostname,
            'ip_address': self.ip_address
        }
    
    def get_fps_info(self):
        """Get FPS information"""
        return {
            'fps': self.fps_counter.get_fps(),
            'frame_time': self.fps_counter.get_frame_time()
        }
    
    def get_gpu_info(self):
        """Get GPU information if available"""
        if not self.has_gpu:
            return {'available': False}
            
        result = {'available': True, 'type': self.gpu_type}
        
        # Try NVML for NVIDIA GPUs
        if self.gpu_type == "NVIDIA" and HAS_NVML:
            try:
                gpu_data = []
                for i in range(self.nvml_device_count):
                    handle = nvml.nvmlDeviceGetHandleByIndex(i)
                    name = nvml.nvmlDeviceGetName(handle)
                    util = nvml.nvmlDeviceGetUtilizationRates(handle)
                    memory = nvml.nvmlDeviceGetMemoryInfo(handle)
                    temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
                    
                    gpu_data.append({
                        'id': i,
                        'name': name,
                        'util': util.gpu,
                        'memory_used': self.format_bytes(memory.used),
                        'memory_total': self.format_bytes(memory.total),
                        'memory_percent': (memory.used / memory.total) * 100 if memory.total else 0,
                        'temp': temp
                    })
                result['gpus'] = gpu_data
            except:
                pass
        
        # Try GPUtil for other GPUs
        elif self.gpu_type == "AMD/Intel" and HAS_GPU_UTIL:
            try:
                gpu_data = []
                gpus = GPUtil.getGPUs()
                for i, gpu in enumerate(gpus):
                    gpu_data.append({
                        'id': i,
                        'name': gpu.name,
                        'util': gpu.load * 100,
                        'memory_used': self.format_bytes(gpu.memoryUsed * 1024 * 1024),
                        'memory_total': self.format_bytes(gpu.memoryTotal * 1024 * 1024),
                        'memory_percent': gpu.memoryUtil * 100,
                        'temp': gpu.temperature
                    })
                result['gpus'] = gpu_data
            except:
                pass
        
        # Fallback to WMI
        if 'gpus' not in result:
            try:
                gpu_info = self.wmi_interface.Win32_VideoController()[0]
                result['basic'] = {
                    'name': gpu_info.Name,
                    'driver_version': gpu_info.DriverVersion,
                    'adapter_ram': self.format_bytes(int(gpu_info.AdapterRAM)) if hasattr(gpu_info, 'AdapterRAM') and gpu_info.AdapterRAM else "Unknown"
                }
            except Exception:
                result['basic'] = {'name': 'Unknown', 'driver_version': 'Unknown'}
                
        return result
    
    def get_system_uptime(self):
        """Get system uptime"""
        uptime_seconds = int(time.time() - psutil.boot_time())
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        
        if days > 0:
            return f"{days}d {hours:02d}h {minutes:02d}m"
        else:
            return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
    
    def get_system_info(self):
        """Get system information"""
        return {
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'os': 'Windows 11',
            'cpu_cores': self.cpu_cores,
            'cpu_threads': self.cpu_threads,
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')
        }
            
    @staticmethod
    def format_bytes(bytes_value):
        """Format bytes to human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} PB"


class SystemMonitorThread(QThread):
    """Thread to monitor system resources without blocking the main thread"""
    update_signal = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.monitor = SystemMonitor()
        self.running = True
        self.interval = 1  # Update interval in seconds
        self.low_resource_interval = 2.5  # Update interval in low resource mode
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self.low_resource_mode = False
        self.collected_info = {}
        self.collection_schedule = {
            # Key: info type, Value: [seconds between updates, last update time]
            'battery': [2, 0],
            'cpu': [1, 0],
            'memory': [2, 0],
            'disk': [10, 0],  # Less frequent disk checks
            'network': [1, 0],
            'fps': [0.5, 0],
            'gpu': [3, 0],    # Less frequent GPU checks
            'uptime': [10, 0], # Update uptime rarely
            'system': [30, 0]  # System info rarely changes
        }
        
    def run(self):
        # First update immediately for essential metrics
        self.collected_info = {
            'battery': self.monitor.get_battery_info(),
            'cpu': self.monitor.get_cpu_detailed(),
            'memory': self.monitor.get_memory_usage(),
            'network': self.monitor.get_network_io(),
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'elapsed_ms': self.elapsed_timer.elapsed()
        }
        self.update_signal.emit(self.collected_info)
        
        last_update_time = time.time()
        
        while self.running:
            # Use adaptive interval based on mode
            current_interval = self.low_resource_interval if self.low_resource_mode else self.interval
            
            # Sleep but break into smaller chunks for more responsive shutdown
            sleep_chunks = 10
            chunk_time = current_interval / sleep_chunks
            for _ in range(sleep_chunks):
                if not self.running:
                    break
                time.sleep(chunk_time)
            
            # Check if we're still running after sleep
            if not self.running:
                break
                
            # Only collect what's needed based on schedule
            current_time = time.time()
            self.collect_scheduled_info(current_time)
            
            # Always update timestamp and elapsed time
            self.collected_info['timestamp'] = datetime.now().strftime('%H:%M:%S')
            self.collected_info['elapsed_ms'] = self.elapsed_timer.elapsed()
            
            # Emit update with all available info (some may be from previous collections)
            self.update_signal.emit(self.collected_info)
            last_update_time = current_time
    
    def collect_scheduled_info(self, current_time):
        """Collect only the information that needs updating based on schedule"""
        for info_type, (interval, last_update) in self.collection_schedule.items():
            # Skip if update not needed yet
            if current_time - last_update < interval:
                continue
                
            # Update this metric
            try:
                if info_type == 'battery':
                    self.collected_info['battery'] = self.monitor.get_battery_info()
                elif info_type == 'cpu':
                    self.collected_info['cpu'] = self.monitor.get_cpu_detailed()
                elif info_type == 'memory':
                    self.collected_info['memory'] = self.monitor.get_memory_usage()
                elif info_type == 'disk':
                    self.collected_info['disk'] = self.monitor.get_disk_usage()
                elif info_type == 'network':
                    self.collected_info['network'] = self.monitor.get_network_io()
                elif info_type == 'fps':
                    self.collected_info['fps'] = self.monitor.get_fps_info()
                elif info_type == 'gpu':
                    self.collected_info['gpu'] = self.monitor.get_gpu_info()
                elif info_type == 'uptime':
                    self.collected_info['uptime'] = self.monitor.get_system_uptime()
                elif info_type == 'system':
                    self.collected_info['system'] = self.monitor.get_system_info()
                
                # Update last update time
                self.collection_schedule[info_type][1] = current_time
            except Exception as e:
                print(f"Error collecting {info_type}: {e}")
    
    def stop(self):
        self.running = False
        self.wait()
    
    def set_update_interval(self, seconds):
        """Set the update interval in seconds"""
        self.interval = max(0.5, seconds)
        
    def set_low_resource_mode(self, enabled):
        """Set low resource mode"""
        self.low_resource_mode = enabled
        if enabled:
            # Increase all collection intervals in low resource mode
            for info_type in self.collection_schedule:
                self.collection_schedule[info_type][0] *= 2


class OverlayWindow(QWidget):
    """Transparent overlay window to display system information"""
    def __init__(self, opacity=0.7):
        super().__init__(None)
        self.opacity_value = opacity
        self.system_info = {}
        self.view_mode = "compact"  # compact, detailed, fps, network, system
        self.setup_ui()
        
    def setup_ui(self):
        # Make window frameless and transparent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Set default size and position (top right corner)
        self.resize(280, 200)
        self.position_window()
    
    def position_window(self):
        """Position the overlay window in the top-right corner"""
        screen_geometry = QApplication.primaryScreen().geometry()
        window_size = self.size()
        self.move(
            screen_geometry.width() - window_size.width() - 20,
            20  # 20px from the top
        )
    
    def set_system_info(self, info):
        """Update the system info to be displayed"""
        self.system_info = info
        self.update()
    
    def set_opacity(self, opacity):
        """Set the opacity of the overlay window"""
        self.opacity_value = opacity / 100.0
        self.update()
    
    def set_view_mode(self, mode):
        """Set the view mode for the overlay"""
        self.view_mode = mode
        self.update()
        
    def toggle_view_mode(self):
        """Toggle between different view modes"""
        modes = ["compact", "detailed", "fps", "network", "system"]
        current_index = modes.index(self.view_mode)
        next_index = (current_index + 1) % len(modes)
        self.view_mode = modes[next_index]
        self.update()
    
    def paintEvent(self, event):
        """Custom paint event for drawing system information"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Create semi-transparent background with rounded corners
        bg_color = QColor(20, 20, 20, int(self.opacity_value * 180))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.rect(), 10, 10)
        
        # Border
        border_color = QColor(60, 60, 60, int(self.opacity_value * 220))
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 10, 10)
        
        # Set up text properties
        painter.setPen(QPen(QColor(220, 220, 220)))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        
        # Get system information
        if not self.system_info:
            painter.drawText(10, 20, "Waiting for data...")
            return
        
        # Draw based on current view mode
        if self.view_mode == "compact":
            self.draw_compact_view(painter)
        elif self.view_mode == "detailed":
            self.draw_detailed_view(painter)
        elif self.view_mode == "fps":
            self.draw_fps_view(painter)
        elif self.view_mode == "network":
            self.draw_network_view(painter)
        elif self.view_mode == "system":
            self.draw_system_view(painter)
    
    def draw_compact_view(self, painter):
        """Draw the compact view with essential info"""
        # Layout settings
        line_height = 18
        left_margin = 10
        top_margin = 10
        y_pos = top_margin
        
        # Draw title with mode info
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(left_margin, y_pos, "System Monitor - Basic")
        y_pos += line_height + 5
        
        # Reset font for regular info
        normal_font = QFont("Segoe UI", 9)
        painter.setFont(normal_font)
        
        # Draw timestamp
        if 'timestamp' in self.system_info:
            painter.drawText(left_margin, y_pos, f"Updated: {self.system_info['timestamp']}")
            y_pos += line_height
        
        # Draw FPS if available
        if 'fps' in self.system_info:
            fps = self.system_info['fps']
            painter.setPen(QPen(self.get_fps_color(fps['fps'])))
            painter.drawText(left_margin, y_pos, f"FPS: {fps['fps']:.1f} | Frame: {fps['frame_time']:.1f}ms")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
            
        # Draw battery information
        if 'battery' in self.system_info:
            battery = self.system_info['battery']
            status_text = f"{battery['status']} - {battery['percent']}%"
            if battery['status'] == 'Discharging':
                status_text += f" ({battery['time_left']} left)"
            painter.drawText(left_margin, y_pos, f"Battery: {status_text}")
            y_pos += line_height
        
        # Draw CPU usage
        if 'cpu' in self.system_info and isinstance(self.system_info['cpu'], dict):
            cpu = self.system_info['cpu']
            cpu_value = cpu['usage']
            painter.setPen(QPen(self.get_usage_color(cpu_value)))
            painter.drawText(left_margin, y_pos, f"CPU: {cpu_value:.1f}% | {cpu['frequency']:.0f} MHz")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
        elif 'cpu' in self.system_info:
            cpu_value = self.system_info['cpu']
            painter.setPen(QPen(self.get_usage_color(cpu_value)))
            painter.drawText(left_margin, y_pos, f"CPU: {cpu_value:.1f}%")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
        
        # Draw memory usage
        if 'memory' in self.system_info:
            memory = self.system_info['memory']
            painter.setPen(QPen(self.get_usage_color(memory['percent'])))
            painter.drawText(left_margin, y_pos, 
                            f"RAM: {memory['percent']}% ({memory['used']}/{memory['total']})")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
        
        # Draw network speed
        if 'network' in self.system_info:
            network = self.system_info['network']
            if 'speed_up' in network and 'speed_down' in network:
                painter.drawText(left_margin, y_pos, 
                               f"Network: ↑{network['speed_up']} ↓{network['speed_down']}")
                y_pos += line_height
            else:
                painter.drawText(left_margin, y_pos, 
                               f"Network: ↑{network['bytes_sent']} ↓{network['bytes_recv']}")
                y_pos += line_height
        
        # Draw GPU info if available
        if 'gpu' in self.system_info and self.system_info['gpu']['available']:
            gpu = self.system_info['gpu']
            if 'gpus' in gpu and gpu['gpus']:
                g = gpu['gpus'][0]  # Just show the first GPU in compact mode
                painter.setPen(QPen(self.get_usage_color(g['util'])))
                painter.drawText(left_margin, y_pos, 
                               f"GPU: {g['util']:.1f}% | {g['temp']}°C")
                painter.setPen(QPen(QColor(220, 220, 220)))
                y_pos += line_height
            elif 'basic' in gpu:
                painter.drawText(left_margin, y_pos, f"GPU: {gpu['basic']['name']}")
                y_pos += line_height
        
        # Draw uptime
        if 'uptime' in self.system_info:
            painter.drawText(left_margin, y_pos, f"Uptime: {self.system_info['uptime']}")
            y_pos += line_height
        
        # Draw click instruction at the bottom
        instruction_font = QFont("Segoe UI", 8, QFont.Weight.Light, True)
        painter.setFont(instruction_font)
        painter.drawText(left_margin, self.height() - 10, "Click to change view • Double-click to hide")
    
    def draw_detailed_view(self, painter):
        """Draw the detailed view with comprehensive system info"""
        # Layout settings
        line_height = 18
        left_margin = 10
        top_margin = 10
        y_pos = top_margin
        
        # Draw title with mode info
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(left_margin, y_pos, "System Monitor - Detailed")
        y_pos += line_height + 5
        
        # Reset font for regular info
        normal_font = QFont("Segoe UI", 9)
        painter.setFont(normal_font)
        
        # Draw timestamp
        if 'timestamp' in self.system_info:
            painter.drawText(left_margin, y_pos, f"Updated: {self.system_info['timestamp']}")
            y_pos += line_height
        
        # Draw battery information with more detail
        if 'battery' in self.system_info:
            battery = self.system_info['battery']
            status_text = f"{battery['status']} - {battery['percent']}%"
            if battery['status'] == 'Discharging':
                status_text += f" ({battery['time_left']} left)"
            painter.drawText(left_margin, y_pos, f"Battery: {status_text}")
            y_pos += line_height
        
        # Draw detailed CPU info
        if 'cpu' in self.system_info and isinstance(self.system_info['cpu'], dict):
            cpu = self.system_info['cpu']
            cpu_value = cpu['usage']
            painter.setPen(QPen(self.get_usage_color(cpu_value)))
            painter.drawText(left_margin, y_pos, 
                           f"CPU: {cpu_value:.1f}% (User: {cpu['user']:.1f}% Sys: {cpu['system']:.1f}%)")
            y_pos += line_height
            painter.drawText(left_margin, y_pos,
                           f"CPU Freq: {cpu['frequency']:.0f} MHz | {cpu['cores']} cores, {cpu['threads']} threads")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
            
            # Draw individual core usage if available
            if 'per_core' in cpu and cpu['per_core']:
                # Just show first 6 cores/threads to avoid clutter
                cores_to_show = min(6, len(cpu['per_core']))
                core_text = "Cores: "
                for i in range(cores_to_show):
                    core_text += f"{cpu['per_core'][i]:.0f}% "
                if cores_to_show < len(cpu['per_core']):
                    core_text += "..."
                painter.drawText(left_margin, y_pos, core_text)
                y_pos += line_height
        
        # Draw detailed memory information
        if 'memory' in self.system_info:
            memory = self.system_info['memory']
            painter.setPen(QPen(self.get_usage_color(memory['percent'])))
            painter.drawText(left_margin, y_pos, 
                          f"RAM: {memory['percent']:.1f}% ({memory['used']}/{memory['total']})")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
            
            # Add swap info
            if 'swap_percent' in memory:
                painter.setPen(QPen(self.get_usage_color(memory['swap_percent'])))
                painter.drawText(left_margin, y_pos, 
                               f"Swap: {memory['swap_percent']:.1f}% ({memory['swap_used']}/{memory['swap_total']})")
                painter.setPen(QPen(QColor(220, 220, 220)))
                y_pos += line_height
        
        # Draw disk information
        if 'disk' in self.system_info:
            disks = self.system_info['disk']
            if isinstance(disks, dict):
                # Show system drive first
                system_drive = os.getenv('SystemDrive', 'C:')
                if system_drive in disks:
                    disk = disks[system_drive]
                    painter.setPen(QPen(self.get_usage_color(disk['percent'])))
                    painter.drawText(left_margin, y_pos, 
                                   f"Disk {system_drive}: {disk['percent']}% ({disk['used']}/{disk['total']})")
                    painter.setPen(QPen(QColor(220, 220, 220)))
                    y_pos += line_height
                
                # Show other drives (limited to 2 more to avoid clutter)
                other_drives = [d for d in disks.keys() if d != system_drive][:2]
                for drive in other_drives:
                    disk = disks[drive]
                    painter.setPen(QPen(self.get_usage_color(disk['percent'])))
                    painter.drawText(left_margin, y_pos, 
                                   f"Disk {drive}: {disk['percent']}% ({disk['used']}/{disk['total']})")
                    painter.setPen(QPen(QColor(220, 220, 220)))
                    y_pos += line_height
            else:
                # Legacy format - single disk info
                disk = self.system_info['disk']
                painter.setPen(QPen(self.get_usage_color(disk['percent'])))
                painter.drawText(left_margin, y_pos, 
                               f"Disk: {disk['percent']}% ({disk['used']}/{disk['total']})")
                painter.setPen(QPen(QColor(220, 220, 220)))
                y_pos += line_height
        
        # Draw network information
        if 'network' in self.system_info:
            network = self.system_info['network']
            if 'speed_up' in network and 'speed_down' in network:
                painter.drawText(left_margin, y_pos, 
                               f"Network: ↑{network['speed_up']} ↓{network['speed_down']}")
                y_pos += line_height
                
                if 'ip_address' in network:
                    painter.drawText(left_margin, y_pos, f"IP: {network['ip_address']}")
                    y_pos += line_height
        
        # Draw uptime
        if 'uptime' in self.system_info:
            painter.drawText(left_margin, y_pos, f"Uptime: {self.system_info['uptime']}")
        
        # Draw click instruction at the bottom
        instruction_font = QFont("Segoe UI", 8, QFont.Weight.Light, True)
        painter.setFont(instruction_font)
        painter.drawText(left_margin, self.height() - 10, "Click to change view • Double-click to hide")
    
    def draw_fps_view(self, painter):
        """Draw FPS-focused view with performance metrics"""
        # Make the window larger for FPS view
        if self.width() < 300:
            self.resize(300, self.height())
            
        # Layout settings
        line_height = 18
        left_margin = 10
        top_margin = 10
        y_pos = top_margin
        
        # Draw title with mode info
        title_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(left_margin, y_pos, "Performance Monitor")
        y_pos += line_height + 8
        
        # Use larger font for FPS display
        fps_font = QFont("Segoe UI", 20, QFont.Weight.Bold)
        painter.setFont(fps_font)
        
        # Draw large FPS number
        if 'fps' in self.system_info:
            fps = self.system_info['fps']['fps']
            painter.setPen(QPen(self.get_fps_color(fps)))
            painter.drawText(self.width() // 2 - 50, y_pos, f"{fps:.1f} FPS")
            y_pos += line_height + 15
        
        # Reset font for regular info
        normal_font = QFont("Segoe UI", 9)
        painter.setFont(normal_font)
        painter.setPen(QPen(QColor(220, 220, 220)))
        
        # Draw frame time
        if 'fps' in self.system_info:
            frame_time = self.system_info['fps']['frame_time']
            painter.drawText(left_margin, y_pos, f"Frame Time: {frame_time:.2f} ms")
            y_pos += line_height
        
        # Draw horizontal separator line
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(left_margin,  y_pos,  self.width() - left_margin, y_pos)
        y_pos += line_height
        painter.setPen(QPen(QColor(220, 220, 220)))
        
        # Draw CPU info
        if 'cpu' in self.system_info and isinstance(self.system_info['cpu'], dict):
            cpu = self.system_info['cpu']
            cpu_value = cpu['usage']
            painter.setPen(QPen(self.get_usage_color(cpu_value)))
            painter.drawText(left_margin, y_pos, f"CPU: {cpu_value:.1f}% | {cpu['frequency']:.0f} MHz")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
        
        # Draw GPU info if available
        if 'gpu' in self.system_info and self.system_info['gpu']['available']:
            gpu = self.system_info['gpu']
            if 'gpus' in gpu and gpu['gpus']:
                for g in gpu['gpus']:
                    painter.setPen(QPen(self.get_usage_color(g['util'])))
                    painter.drawText(left_margin, y_pos, 
                                   f"GPU {g['id']}: {g['util']:.1f}% | {g['temp']}°C")
                    painter.setPen(QPen(QColor(220, 220, 220)))
                    y_pos += line_height
                    painter.drawText(left_margin + 10, y_pos, 
                                   f"VRAM: {g['memory_percent']:.1f}% ({g['memory_used']}/{g['memory_total']})")
                    y_pos += line_height
            elif 'basic' in gpu:
                painter.drawText(left_margin, y_pos, f"GPU: {gpu['basic']['name']}")
                y_pos += line_height
        
        # Draw RAM info
        if 'memory' in self.system_info:
            memory = self.system_info['memory']
            painter.setPen(QPen(self.get_usage_color(memory['percent'])))
            painter.drawText(left_margin, y_pos, 
                          f"RAM: {memory['percent']:.1f}% ({memory['used']}/{memory['total']})")
            painter.setPen(QPen(QColor(220, 220, 220)))
            y_pos += line_height
        
        # Draw click instruction at the bottom
        instruction_font = QFont("Segoe UI", 8, QFont.Weight.Light, True)
        painter.setFont(instruction_font)
        painter.drawText(left_margin, self.height() - 10, "Click to change view • Double-click to hide")
    
    def draw_network_view(self, painter):
        """Draw network-focused view with detailed network information"""
        # Layout settings
        line_height = 18
        left_margin = 10
        top_margin = 10
        y_pos = top_margin
        
        # Draw title with mode info
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(left_margin, y_pos, "Network Monitor")
        y_pos += line_height + 5
        
        # Reset font for regular info
        normal_font = QFont("Segoe UI", 9)
        painter.setFont(normal_font)
        
        if 'network' in self.system_info:
            network = self.system_info['network']
            
            # Draw hostname and IP
            if 'hostname' in network and 'ip_address' in network:
                painter.drawText(left_margin, y_pos, f"Host: {network['hostname']}")
                y_pos += line_height
                painter.drawText(left_margin, y_pos, f"IP: {network['ip_address']}")
                y_pos += line_height
            
            # Draw horizontal separator
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawLine(left_margin,  y_pos,  self.width() - left_margin, y_pos)
            y_pos += line_height
            painter.setPen(QPen(QColor(220, 220, 220)))
            
            # Draw current network speed with larger font
            if 'speed_up' in network and 'speed_down' in network:
                # Use a larger font for the speeds
                speed_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
                painter.setFont(speed_font)
                
                # Draw download speed
                painter.setPen(QPen(QColor(0, 200, 0)))
                painter.drawText(left_margin, y_pos, f"↓ {network['speed_down']}")
                y_pos += line_height + 5
                
                # Draw upload speed
                painter.setPen(QPen(QColor(200, 120, 0)))
                painter.drawText(left_margin, y_pos, f"↑ {network['speed_up']}")
                y_pos += line_height + 5
                
                # Reset to normal font and color
                painter.setFont(normal_font)
                painter.setPen(QPen(QColor(220, 220, 220)))
            
            # Draw total transferred data
            painter.drawText(left_margin, y_pos, f"Total Received: {network['bytes_recv']}")
            y_pos += line_height
            painter.drawText(left_margin, y_pos, f"Total Sent: {network['bytes_sent']}")
            y_pos += line_height
        else:
            painter.drawText(left_margin, y_pos, "Network information not available")
        
        # Draw timestamp at the bottom
        if 'timestamp' in self.system_info:
            painter.drawText(left_margin, self.height() - 30, f"Updated: {self.system_info['timestamp']}")
        
        # Draw click instruction at the bottom
        instruction_font = QFont("Segoe UI", 8, QFont.Weight.Light, True)
        painter.setFont(instruction_font)
        painter.drawText(left_margin, self.height() - 10, "Click to change view • Double-click to hide")
    
    def draw_system_view(self, painter):
        """Draw system information view"""
        # Layout settings
        line_height = 18
        left_margin = 10
        top_margin = 10
        y_pos = top_margin
        
        # Draw title with mode info
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(left_margin, y_pos, "System Information")
        y_pos += line_height + 5
        
        # Reset font for regular info
        normal_font = QFont("Segoe UI", 9)
        painter.setFont(normal_font)
        
        # Draw system information
        if 'system' in self.system_info:
            system = self.system_info['system']
            
            # Draw OS information
            if 'os' in system:
                painter.drawText(left_margin, y_pos, f"OS: {system['os']}")
                y_pos += line_height
            
            # Draw hostname and IP
            if 'hostname' in system and 'ip_address' in system:
                painter.drawText(left_margin, y_pos, f"Host: {system['hostname']}")
                y_pos += line_height
                painter.drawText(left_margin, y_pos, f"IP: {system['ip_address']}")
                y_pos += line_height
            
            # Draw CPU information
            if 'cpu_cores' in system and 'cpu_threads' in system:
                painter.drawText(left_margin, y_pos, 
                               f"CPU: {system['cpu_cores']} cores, {system['cpu_threads']} threads")
                y_pos += line_height
            
            # Draw boot time
            if 'boot_time' in system:
                painter.drawText(left_margin, y_pos, f"Boot Time: {system['boot_time']}")
                y_pos += line_height
        
        # Draw GPU information
        if 'gpu' in self.system_info and self.system_info['gpu']['available']:
            gpu = self.system_info['gpu']
            painter.drawText(left_margin, y_pos, f"GPU Type: {gpu['type']}")
            y_pos += line_height
            
            if 'gpus' in gpu and gpu['gpus']:
                for g in gpu['gpus']:
                    painter.drawText(left_margin, y_pos, f"GPU {g['id']}: {g['name']}")
                    y_pos += line_height
                    painter.drawText(left_margin + 10, y_pos, 
                                   f"VRAM: {g['memory_total']}")
                    y_pos += line_height
            elif 'basic' in gpu:
                painter.drawText(left_margin, y_pos, f"GPU: {gpu['basic']['name']}")
                y_pos += line_height
                if 'adapter_ram' in gpu['basic']:
                    painter.drawText(left_margin + 10, y_pos, 
                                   f"VRAM: {gpu['basic']['adapter_ram']}")
                    y_pos += line_height
        
        # Draw uptime
        if 'uptime' in self.system_info:
            painter.drawText(left_margin, y_pos, f"Uptime: {self.system_info['uptime']}")
            y_pos += line_height
        
        # Draw timestamp at the bottom
        if 'timestamp' in self.system_info:
            painter.drawText(left_margin, self.height() - 30, f"Updated: {self.system_info['timestamp']}")
        
        # Draw click instruction at the bottom
        instruction_font = QFont("Segoe UI", 8, QFont.Weight.Light, True)
        painter.setFont(instruction_font)
        painter.drawText(left_margin, self.height() - 10, "Click to change view • Double-click to hide")
    
    def get_usage_color(self, percentage):
        """Get color based on usage percentage"""
        if percentage < 50:
            return QColor(0, 255, 0)  # Green for low usage
        elif percentage < 80:
            return QColor(255, 255, 0)  # Yellow for medium usage
        else:
            return QColor(255, 0, 0)  # Red for high usage
    
    def get_fps_color(self, fps):
        """Get color based on FPS value"""
        if fps >= 60:
            return QColor(0, 255, 0)  # Green for high FPS
        elif fps >= 30:
            return QColor(255, 255, 0)  # Yellow for medium FPS
        else:
            return QColor(255, 0, 0)  # Red for low FPS
    
    def mousePressEvent(self, event):
        """Handle mouse press events for dragging the window"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events for dragging the window"""
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release events for changing view mode"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_view_mode()
            event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """Handle mouse double click events for hiding the overlay"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Hide overlay (will be handled by parent window)
            self.hide()
            event.accept()


class SettingsDialog(QDialog):
    """Settings dialog for the system monitor"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Monitor Settings")
        self.resize(350, 300)
        self.setup_ui()
    
    def setup_ui(self):
        main_layout = QVBoxLayout()
        
        # Create tabs
        tabs = QTabWidget()
        main_layout.addWidget(tabs)
        
        # General tab
        general_tab = QWidget()
        general_layout = QVBoxLayout()
        general_tab.setLayout(general_layout)
        
        # Update interval setting
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Update Interval:"))
        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setMinimum(5)  # 0.5 seconds
        self.interval_slider.setMaximum(50)  # 5 seconds
        self.interval_slider.setValue(10)  # 1 second default
        self.interval_value_label = QLabel("1.0s")
        interval_layout.addWidget(self.interval_slider)
        interval_layout.addWidget(self.interval_value_label)
        general_layout.addLayout(interval_layout)
        
        # Overlay opacity setting
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Overlay Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setMinimum(10)
        self.opacity_slider.setMaximum(95)
        self.opacity_slider.setValue(70)
        self.opacity_value_label = QLabel("70%")
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_value_label)
        general_layout.addLayout(opacity_layout)
        
        # Default view mode
        view_layout = QHBoxLayout()
        view_layout.addWidget(QLabel("Default View:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Compact", "Detailed", "FPS", "Network", "System"])
        view_layout.addWidget(self.view_mode_combo)
        general_layout.addLayout(view_layout)
        
        # Show on startup setting
        self.startup_checkbox = QCheckBox("Show overlay on startup")
        general_layout.addWidget(self.startup_checkbox)
        
        # Start with Windows setting
        self.windows_startup_checkbox = QCheckBox("Start with Windows")
        general_layout.addWidget(self.windows_startup_checkbox)
        
        # Add spacer
        general_layout.addStretch()
        
        # Display tab
        display_tab = QWidget()
        display_layout = QVBoxLayout()
        display_tab.setLayout(display_layout)
        
        # Show battery percentage on icon
        self.show_battery_percent_checkbox = QCheckBox("Show battery percentage on taskbar icon")
        self.show_battery_percent_checkbox.setChecked(True)
        display_layout.addWidget(self.show_battery_percent_checkbox)
        
        # Show FPS counter
        self.show_fps_checkbox = QCheckBox("Enable FPS counter")
        self.show_fps_checkbox.setChecked(True)
        display_layout.addWidget(self.show_fps_checkbox)
        
        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light", "System"])
        theme_layout.addWidget(self.theme_combo)
        display_layout.addLayout(theme_layout)
        
        # Add spacer
        display_layout.addStretch()
        
        # Advanced tab
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout()
        advanced_tab.setLayout(advanced_layout)
        
        # Low resource mode
        self.low_resource_checkbox = QCheckBox("Low resource mode")
        self.low_resource_checkbox.setToolTip("Reduces update frequency and disables some features to minimize system impact")
        advanced_layout.addWidget(self.low_resource_checkbox)
        
        # Advanced metrics checkbox
        self.advanced_metrics_checkbox = QCheckBox("Show advanced metrics")
        self.advanced_metrics_checkbox.setToolTip("Show detailed technical metrics like per-core CPU usage and memory details")
        advanced_layout.addWidget(self.advanced_metrics_checkbox)
        
        # New: Monitoring options group
        monitoring_group = QGroupBox("Monitoring Options")
        monitoring_layout = QVBoxLayout()
        
        # Network adapter selection
        network_layout = QHBoxLayout()
        network_layout.addWidget(QLabel("Network Adapter:"))
        self.network_adapter_combo = QComboBox()
        self.network_adapter_combo.addItem("Auto-detect")
        # We'll populate this with actual adapters later
        for i in range(1, 5):
            self.network_adapter_combo.addItem(f"Adapter {i}")
        network_layout.addWidget(self.network_adapter_combo)
        monitoring_layout.addLayout(network_layout)
        
        # GPU monitoring options
        self.gpu_monitoring_checkbox = QCheckBox("Enable GPU monitoring")
        self.gpu_monitoring_checkbox.setToolTip("May increase system impact slightly")
        monitoring_layout.addWidget(self.gpu_monitoring_checkbox)
        
        # Disk monitoring options
        self.disk_monitoring_checkbox = QCheckBox("Monitor all disk drives")
        self.disk_monitoring_checkbox.setToolTip("Monitor all drives instead of just system drive")
        monitoring_layout.addWidget(self.disk_monitoring_checkbox)
        
        # Process monitoring
        self.process_monitoring_checkbox = QCheckBox("Monitor top processes")
        self.process_monitoring_checkbox.setToolTip("Show CPU and memory usage of top processes")
        monitoring_layout.addWidget(self.process_monitoring_checkbox)
        
        monitoring_group.setLayout(monitoring_layout)
        advanced_layout.addWidget(monitoring_group)
        
        # Notifications group
        notification_group = QGroupBox("Notifications")
        notification_layout = QVBoxLayout()
        
        # Battery notifications
        self.battery_notify_checkbox = QCheckBox("Battery alerts")
        self.battery_notify_checkbox.setToolTip("Show notification when battery is low")
        notification_layout.addWidget(self.battery_notify_checkbox)
        
        # High usage notifications
        self.usage_notify_checkbox = QCheckBox("Resource usage alerts")
        self.usage_notify_checkbox.setToolTip("Show notification when CPU/RAM usage is high")
        notification_layout.addWidget(self.usage_notify_checkbox)
        
        notification_group.setLayout(notification_layout)
        advanced_layout.addWidget(notification_group)
        
        # Show advanced metrics
        self.advanced_metrics_checkbox = QCheckBox("Show advanced metrics")
        advanced_layout.addWidget(self.advanced_metrics_checkbox)
        
        # Add spacer
        advanced_layout.addStretch()
        
        # Appearance tab
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout()
        appearance_tab.setLayout(appearance_layout)
        
        # Overlay position
        position_group = QGroupBox("Overlay Position")
        position_layout = QHBoxLayout()
        
        # Position selection with radio buttons
        self.position_top_left = QRadioButton("Top Left")
        self.position_top_right = QRadioButton("Top Right")
        self.position_bottom_left = QRadioButton("Bottom Left")
        self.position_bottom_right = QRadioButton("Bottom Right")
        self.position_custom = QRadioButton("Custom")
        
        # Default to top-right
        self.position_top_right.setChecked(True)
        
        # Add to layout
        position_layout.addWidget(self.position_top_left)
        position_layout.addWidget(self.position_top_right)
        position_layout.addWidget(self.position_bottom_left)
        position_layout.addWidget(self.position_bottom_right)
        position_layout.addWidget(self.position_custom)
        
        position_group.setLayout(position_layout)
        appearance_layout.addWidget(position_group)
        
        # Color scheme group
        color_group = QGroupBox("Color Scheme")
        color_layout = QVBoxLayout()
        
        # Color customization
        self.custom_colors_checkbox = QCheckBox("Use custom colors")
        color_layout.addWidget(self.custom_colors_checkbox)
        
        # Font selection
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Font Size:"))
        self.font_size_spinner = QSpinBox()
        self.font_size_spinner.setRange(7, 16)
        self.font_size_spinner.setValue(9)
        font_layout.addWidget(self.font_size_spinner)
        
        color_layout.addLayout(font_layout)
        
        # Custom color options (shown when custom_colors is checked)
        self.color_normal_label = QLabel("Normal Text: RGB(220,220,220)")
        self.color_high_label = QLabel("High Usage: RGB(255,0,0)")
        self.color_med_label = QLabel("Medium Usage: RGB(255,255,0)")
        self.color_low_label = QLabel("Low Usage: RGB(0,255,0)")
        
        color_layout.addWidget(self.color_normal_label)
        color_layout.addWidget(self.color_high_label)
        color_layout.addWidget(self.color_med_label)
        color_layout.addWidget(self.color_low_label)
        
        color_group.setLayout(color_layout)
        appearance_layout.addWidget(color_group)
        
        # Add spacer
        appearance_layout.addStretch()
        
        # Add tabs to tab widget
        tabs.addTab(general_tab, "General")
        tabs.addTab(display_tab, "Display")
        tabs.addTab(appearance_tab, "Appearance")
        tabs.addTab(advanced_tab, "Advanced")
        
        # Add buttons at the bottom
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.interval_slider.valueChanged.connect(self.update_interval_label)
        self.opacity_slider.valueChanged.connect(self.update_opacity_label)
        
        self.setLayout(main_layout)
    
    def update_interval_label(self, value):
        """Update interval label to show the actual value in seconds"""
        actual_seconds = value / 10  # Convert slider value to seconds
        self.interval_value_label.setText(f"{actual_seconds:.1f}s")
    
    def update_opacity_label(self, value):
        self.opacity_value_label.setText(f"{value}%")
        
    def get_settings(self):
        """Get the current settings"""
        # Determine overlay position
        overlay_position = "top-right"  # Default
        if self.position_top_left.isChecked():
            overlay_position = "top-left"
        elif self.position_top_right.isChecked():
            overlay_position = "top-right"
        elif self.position_bottom_left.isChecked():
            overlay_position = "bottom-left"
        elif self.position_bottom_right.isChecked():
            overlay_position = "bottom-right"
        elif self.position_custom.isChecked():
            overlay_position = "custom"
            
        # Get all settings
        return {
            # General settings
            'interval': self.interval_slider.value() / 10,  # Convert to actual seconds
            'opacity': self.opacity_slider.value(),
            'show_on_startup': self.startup_checkbox.isChecked(),
            'windows_startup': self.windows_startup_checkbox.isChecked(),
            'default_view_mode': self.view_mode_combo.currentText().lower(),
            
            # Display settings
            'show_battery_percent': self.show_battery_percent_checkbox.isChecked(),
            'show_fps': self.show_fps_checkbox.isChecked(),
            'theme': self.theme_combo.currentText().lower(),
            
            # Appearance settings
            'overlay_position': overlay_position,
            'custom_colors': self.custom_colors_checkbox.isChecked(),
            'font_size': self.font_size_spinner.value(),
            
            # Advanced settings
            'low_resource_mode': self.low_resource_checkbox.isChecked(),
            'advanced_metrics': self.advanced_metrics_checkbox.isChecked(),
            'gpu_monitoring': self.gpu_monitoring_checkbox.isChecked(),
            'disk_monitoring': self.disk_monitoring_checkbox.isChecked(),
            'process_monitoring': self.process_monitoring_checkbox.isChecked(),
            'battery_notifications': self.battery_notify_checkbox.isChecked(),
            'usage_notifications': self.usage_notify_checkbox.isChecked(),
            'network_adapter': self.network_adapter_combo.currentText()
        }
    
    def set_settings(self, settings):
        """Apply saved settings"""
        # General settings
        if 'interval' in settings:
            self.interval_slider.setValue(int(settings['interval'] * 10))  # Convert from seconds to slider value
        if 'opacity' in settings:
            self.opacity_slider.setValue(settings['opacity'])
        if 'show_on_startup' in settings:
            self.startup_checkbox.setChecked(settings['show_on_startup'])
        if 'windows_startup' in settings:
            self.windows_startup_checkbox.setChecked(settings['windows_startup'])
        if 'default_view_mode' in settings:
            index = self.view_mode_combo.findText(settings['default_view_mode'].capitalize())
            if index >= 0:
                self.view_mode_combo.setCurrentIndex(index)
                
        # Display settings
        if 'show_battery_percent' in settings:
            self.show_battery_percent_checkbox.setChecked(settings['show_battery_percent'])
        if 'show_fps' in settings:
            self.show_fps_checkbox.setChecked(settings['show_fps'])
        if 'theme' in settings:
            index = self.theme_combo.findText(settings['theme'].capitalize())
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)
                
        # Appearance settings
        if 'overlay_position' in settings:
            pos = settings['overlay_position']
            if pos == "top-left":
                self.position_top_left.setChecked(True)
            elif pos == "top-right":
                self.position_top_right.setChecked(True)
            elif pos == "bottom-left":
                self.position_bottom_left.setChecked(True)
            elif pos == "bottom-right":
                self.position_bottom_right.setChecked(True)
            elif pos == "custom":
                self.position_custom.setChecked(True)
                
        if 'custom_colors' in settings:
            self.custom_colors_checkbox.setChecked(settings['custom_colors'])
        if 'font_size' in settings:
            self.font_size_spinner.setValue(settings['font_size'])
                
        # Advanced settings
        if 'low_resource_mode' in settings:
            self.low_resource_checkbox.setChecked(settings['low_resource_mode'])
        if 'advanced_metrics' in settings:
            self.advanced_metrics_checkbox.setChecked(settings['advanced_metrics'])
        if 'gpu_monitoring' in settings:
            self.gpu_monitoring_checkbox.setChecked(settings['gpu_monitoring'])
        if 'disk_monitoring' in settings:
            self.disk_monitoring_checkbox.setChecked(settings['disk_monitoring'])
        if 'process_monitoring' in settings:
            self.process_monitoring_checkbox.setChecked(settings['process_monitoring'])
        if 'battery_notifications' in settings:
            self.battery_notify_checkbox.setChecked(settings['battery_notifications'])
        if 'usage_notifications' in settings:
            self.usage_notify_checkbox.setChecked(settings['usage_notifications'])
        if 'network_adapter' in settings and settings['network_adapter']:
            index = self.network_adapter_combo.findText(settings['network_adapter'])
            if index >= 0:
                self.network_adapter_combo.setCurrentIndex(index)


class SystemMonitorApp:
    """Main application class for the system monitor with enhanced taskbar and overlay displays"""
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Resources path
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.resource_path = os.path.join(self.base_path, 'resources')
        
        # Create resources directory if it doesn't exist
        if not os.path.exists(self.resource_path):
            os.makedirs(self.resource_path)
        
        # Create icons for the tray
        self.create_tray_icons()
        
        # Initialize system monitor thread
        self.monitor_thread = SystemMonitorThread()
        self.monitor_thread.update_signal.connect(self.update_system_info)
        
        # Initialize overlay window
        self.overlay = None
        self.overlay_visible = False
        
        # Create socket listener for inter-process communication
        self.setup_socket_listener()
        
        # Initialize settings with extended options
        self.settings = {
            # General settings
            'interval': 1.0,
            'opacity': 70,
            'show_on_startup': True,
            'windows_startup': False,
            'default_view_mode': 'compact',
            
            # Display settings
            'show_battery_percent': True,
            'show_fps': True,
            'theme': 'dark',
            
            # Appearance settings
            'overlay_position': 'top-right',
            'custom_colors': False,
            'font_size': 9,
            
            # Advanced settings
            'low_resource_mode': False,
            'advanced_metrics': True,
            'gpu_monitoring': True,
            'disk_monitoring': True,
            'process_monitoring': False,
            'battery_notifications': True,
            'usage_notifications': False,
            'network_adapter': 'Auto-detect'
        }
        
        # Initialize settings dialog
        self.settings_dialog = None
        
        # Create system tray icon
        self.setup_tray()
        
        # Apply settings to monitor thread
        self.monitor_thread.set_low_resource_mode(self.settings['low_resource_mode'])
        
        # If show on startup is enabled, show the overlay
        if self.settings['show_on_startup']:
            self.toggle_overlay()
            
        # Apply startup settings if enabled
        if self.settings['windows_startup']:
            self.setup_windows_startup()
    
    def create_tray_icons(self):
        """Create battery icons for different states"""
        self.battery_icons = {}
        
        # Define battery levels and their colors
        levels = [0, 25, 50, 75, 100]
        colors = {
            0: (255, 0, 0),      # Red for very low
            25: (255, 128, 0),   # Orange for low
            50: (255, 255, 0),   # Yellow for medium
            75: (128, 255, 0),   # Light green for good
            100: (0, 255, 0)     # Green for full
        }
        
        # Create battery icons for different levels (both charging and discharging)
        for level in levels:
            for charging in [True, False]:
                self.create_battery_icon(level, charging, colors[level])
    
    def create_battery_icon(self, level, charging, color):
        """Create a battery icon for a specific level and state with LARGE, clear percentage text"""
        # Create a larger image for more detail - 64x64 for maximum visibility then scale down
        icon_size = 64
        image = QImage(icon_size, icon_size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        
        # Create painter for the image
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        # EXTRA LARGE, SUPER BOLD font for maximum taskbar visibility
        percentage_font = QFont("Arial Black", 28, QFont.Weight.ExtraBold)
        painter.setFont(percentage_font)
        
        # Make a simpler, high-contrast design focused on readability
        if charging:
            # CHARGING STATE - Bold number with lightning indicator
            # Black background with slight transparency for contrast
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 210))
            painter.drawRoundedRect(2, 2, icon_size-4, icon_size-4, 8, 8)
            
            # Draw large percentage in bright yellow-green for charging
            painter.setPen(QPen(QColor(180, 255, 0)))
            
            # For single digits, make them even larger
            if level < 10:
                percentage_font.setPointSize(38)
                painter.setFont(percentage_font)
                painter.drawText(0, -5, icon_size, icon_size, 
                               Qt.AlignmentFlag.AlignCenter, f"{level}")
            else:
                painter.drawText(0, 0, icon_size, icon_size, 
                               Qt.AlignmentFlag.AlignCenter, f"{level}")
            
            # Draw small lightning bolt symbol at bottom
            painter.setPen(QPen(QColor(255, 255, 0), 4))
            painter.drawLine(int(int(icon_size/2)), int(icon_size-20), int(icon_size/2-8), int(icon_size-10))
            painter.drawLine(int(int(icon_size/2-8)), int(icon_size-10), int(icon_size/2+2), int(icon_size-10))
            painter.drawLine(int(int(icon_size/2+2)), int(icon_size-10), int(icon_size/2-6), int(icon_size-2))
        else:
            # DISCHARGING STATE - Just the large number with color-coding
            # Color background based on battery level
            if level <= 10:
                bg_color = QColor(220, 0, 0, 230)  # Bright red for critical
                text_color = QColor(255, 255, 255)  # White text
            elif level <= 20:
                bg_color = QColor(230, 120, 0, 220)  # Orange for low
                text_color = QColor(255, 255, 255)  # White text
            elif level <= 50:
                bg_color = QColor(220, 220, 0, 220)  # Yellow for medium
                text_color = QColor(0, 0, 0)  # Black text for contrast
            else:
                bg_color = QColor(0, 200, 0, 220)  # Green for good
                text_color = QColor(255, 255, 255)  # White text
            
            # Draw solid background for maximum readability
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(2, 2, icon_size-4, icon_size-4, 8, 8)
            
            # Draw the percentage number
            painter.setPen(QPen(text_color))
            
            # For single digits or 100%, adjust size and position for better fit
            if level < 10:
                percentage_font.setPointSize(38)
                painter.setFont(percentage_font)
                painter.drawText(0, -5, icon_size, icon_size, 
                               Qt.AlignmentFlag.AlignCenter, f"{level}")
            elif level == 100:
                percentage_font.setPointSize(22)
                painter.setFont(percentage_font)
                painter.drawText(0, 0, icon_size, icon_size, 
                               Qt.AlignmentFlag.AlignCenter, "100")
            else:
                painter.drawText(0, 0, icon_size, icon_size, 
                               Qt.AlignmentFlag.AlignCenter, f"{level}")
        
        painter.end()
        
        # Convert to pixmap and scale down if needed
        pixmap = QPixmap.fromImage(image)
        
        # Store icon
        key = f"{level}_{'charging' if charging else 'discharging'}"
        self.battery_icons[key] = QIcon(pixmap)
        
        # Save the icon file for system tray
        icon_path = os.path.join(self.resource_path, f"battery_{key}.png")
        pixmap.save(icon_path)
    
    def setup_tray(self):
        """Set up the system tray icon and menu"""
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self.battery_icons["100_charging"])  # Default icon
        
        # Create tray menu
        menu = QMenu()
        
        # Show/hide overlay action
        self.overlay_action = QAction("Show Overlay")
        self.overlay_action.triggered.connect(self.toggle_overlay)
        menu.addAction(self.overlay_action)
        
        # Settings action
        settings_action = QAction("Settings")
        settings_action.triggered.connect(self.show_settings)
        menu.addAction(settings_action)
        
        # Separator
        menu.addSeparator()
        
        # Exit action
        exit_action = QAction("Exit")
        exit_action.triggered.connect(self.quit_application)
        menu.addAction(exit_action)
        
        # Set tray menu
        self.tray_icon.setContextMenu(menu)
        
        # Make the tray icon visible
        self.tray_icon.show()
        
        # Set tooltip
        self.tray_icon.setToolTip("System Monitor")
        
        # Connect activate signal to toggle overlay on left click
        self.tray_icon.activated.connect(self.on_tray_activated)
    
    def on_tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Left-click shows the overlay
            self.toggle_overlay()
    
    def toggle_overlay(self):
        """Toggle the overlay window"""
        if not self.overlay_visible:
            if not self.overlay:
                self.overlay = OverlayWindow(opacity=self.settings['opacity'] / 100.0)
            self.overlay.show()
            self.overlay_visible = True
            self.overlay_action.setText("Hide Overlay")
        else:
            if self.overlay:
                self.overlay.hide()
            self.overlay_visible = False
            self.overlay_action.setText("Show Overlay")
    
    def show_settings(self):
        """Show the settings dialog"""
        if not self.settings_dialog:
            self.settings_dialog = SettingsDialog()
        
        # Apply current settings
        self.settings_dialog.set_settings(self.settings)
        
        # Show dialog
        if self.settings_dialog.exec() == QDialog.DialogCode.Accepted:
            # Store old settings for comparison
            old_settings = dict(self.settings)
            
            # Update settings
            self.settings = self.settings_dialog.get_settings()
            
            # Apply new settings
            self.monitor_thread.set_update_interval(self.settings['interval'])
            
            # Apply low resource mode setting
            if old_settings.get('low_resource_mode', False) != self.settings['low_resource_mode']:
                self.monitor_thread.set_low_resource_mode(self.settings['low_resource_mode'])
            
            if self.overlay:
                self.overlay.set_opacity(self.settings['opacity'])
                
                # Update overlay view mode if it changed
                if old_settings.get('default_view_mode') != self.settings['default_view_mode']:
                    self.overlay.set_view_mode(self.settings['default_view_mode'])
            
            # Handle Windows startup setting changes
            if old_settings.get('windows_startup', False) != self.settings['windows_startup']:
                if self.settings['windows_startup']:
                    self.setup_windows_startup()
                else:
                    self.remove_windows_startup()
                    
            # Recreate tray icons if battery percentage setting changed
            if old_settings.get('show_battery_percent', True) != self.settings['show_battery_percent']:
                self.create_tray_icons()
                
            # Apply theme changes
            if old_settings.get('theme') != self.settings['theme']:
                self.apply_theme(self.settings['theme'])
            
            # Apply performance mode settings
            if old_settings.get('low_resource_mode') != self.settings['low_resource_mode']:
                if self.settings['low_resource_mode']:
                    # Increase update interval to reduce resource usage
                    self.monitor_thread.set_update_interval(max(2.0, self.settings['interval']))
                else:
                    # Use configured update interval
                    self.monitor_thread.set_update_interval(self.settings['interval'])
    
    def apply_theme(self, theme):
        """Apply the selected theme to the application"""
        # Implement theme changes here if needed
        if self.overlay:
            self.overlay.update()  # Force redraw with new theme
    
    def setup_windows_startup(self):
        """Set up the application to start with Windows"""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_path = os.path.abspath(sys.argv[0])
            
            # Use batch file path if this is frozen executable or script
            if app_path.endswith('.py'):
                # Get the batch file path
                batch_path = os.path.join(os.path.dirname(app_path), "Run_System_Monitor.bat")
                if os.path.exists(batch_path):
                    app_path = batch_path
                    
            # Open registry key
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            # Set the value
            winreg.SetValueEx(reg_key, "WindowsSystemMonitor", 0, winreg.REG_SZ, f'"{app_path}"')
            
            winreg.CloseKey(reg_key)
        except Exception as e:
            print(f"Failed to set up Windows startup: {e}")
    
    def remove_windows_startup(self):
        """Remove the application from Windows startup"""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            # Open registry key
            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            # Delete the value
            try:
                winreg.DeleteValue(reg_key, "WindowsSystemMonitor")
            except FileNotFoundError:
                pass  # Value doesn't exist
                
            winreg.CloseKey(reg_key)
        except Exception as e:
            print(f"Failed to remove Windows startup: {e}")
            
    def update_system_info(self, info):
        """Update system information"""
        # Update overlay if visible
        if self.overlay_visible and self.overlay:
            self.overlay.set_system_info(info)
        
        # Update tray icon
        if 'battery' in info:
            battery = info['battery']
            level = battery['percent']
            # Round to nearest level in our icon set
            if level < 12:
                icon_level = 0
            elif level < 37:
                icon_level = 25
            elif level < 62:
                icon_level = 50
            elif level < 87:
                icon_level = 75
            else:
                icon_level = 100
            
            charging = battery['power_plugged']
            icon_key = f"{icon_level}_{'charging' if charging else 'discharging'}"
            
            if icon_key in self.battery_icons:
                self.tray_icon.setIcon(self.battery_icons[icon_key])
            
            # Construct detailed tooltip with more information
            tooltip = f"Windows System Monitor\n\n"
            tooltip += f"Battery: {level}% ({battery['status']})\n"
            tooltip += f"Time left: {battery['time_left']}\n"
            
            # Add CPU info
            if 'cpu' in info:
                if isinstance(info['cpu'], dict):
                    cpu_value = info['cpu']['usage']
                    tooltip += f"CPU: {cpu_value:.1f}%"
                    if 'frequency' in info['cpu']:
                        tooltip += f" | {info['cpu']['frequency']:.0f} MHz"
                    tooltip += "\n"
                else:
                    tooltip += f"CPU: {info['cpu']:.1f}%\n"
            
            # Add memory info
            if 'memory' in info:
                memory = info['memory']
                tooltip += f"RAM: {memory['percent']}% ({memory['used']}/{memory['total']})\n"
            
            # Add network speed info
            if 'network' in info and 'speed_up' in info['network'] and 'speed_down' in info['network']:
                network = info['network']
                tooltip += f"Network: ↑{network['speed_up']} ↓{network['speed_down']}\n"
            
            # Add FPS info if enabled
            if self.settings.get('show_fps', True) and 'fps' in info:
                fps = info['fps']
                tooltip += f"FPS: {fps['fps']:.1f} | Frame Time: {fps['frame_time']:.1f}ms\n"
            
            # Add instructions
            tooltip += "\nLeft-click: Toggle overlay\nRight-click: Menu"
            
            self.tray_icon.setToolTip(tooltip)
    
    def setup_socket_listener(self):
        """Set up a socket to listen for commands from other instances"""
        # Create a socket for receiving commands
        self.socket_thread = threading.Thread(target=self.listen_for_commands, daemon=True)
        self.socket_thread.start()
    
    def listen_for_commands(self):
        """Listen for commands from other instances on a socket"""
        try:
            socket_listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            socket_listener.bind(('localhost', 47190))
            socket_listener.settimeout(1.0)  # 1 second timeout
            
            while True:
                try:
                    data, _ = socket_listener.recvfrom(1024)
                    command = data.decode('utf-8')
                    
                    # Process commands
                    if command == "SHOW_OVERLAY":
                        # Use signal to safely call UI methods from the main thread
                        QApplication.instance().postEvent(
                            self.app, 
                            QApplication.instance().event(QApplication.Type.ApplicationActivate)
                        )
                        # Toggle overlay visibility
                        if not self.overlay_visible:
                            self.toggle_overlay()
                except socket.timeout:
                    # This is normal, just continue
                    continue
                except Exception as e:
                    print(f"Socket error: {e}")
                    # Sleep briefly to avoid high CPU usage if something goes wrong
                    time.sleep(0.1)
        except Exception as e:
            print(f"Failed to start socket listener: {e}")

    def run(self):
        """Run the application"""
        try:
            # Start monitoring thread
            self.monitor_thread.start()
            
            # Run application
            exit_code = self.app.exec()
            
            # Stop monitoring thread
            self.monitor_thread.stop()
            
            return exit_code
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            print("\nApplication terminated by user (Ctrl+C)")
            self.quit_application()
            return 0
        except Exception as e:
            print(f"\nApplication error: {e}")
            self.quit_application()
            return 1
    
    def quit_application(self):
        """Quit the application properly releasing all resources"""
        print("Shutting down system monitor...")
        
        # Stop monitoring thread first
        if hasattr(self, 'monitor_thread'):
            try:
                self.monitor_thread.stop()
                print("- Monitoring thread stopped")
            except Exception as e:
                print(f"- Error stopping monitoring thread: {e}")
        
        # Close overlay window if it exists
        if hasattr(self, 'overlay') and self.overlay:
            try:
                self.overlay.close()
                print("- Overlay window closed")
            except Exception as e:
                print(f"- Error closing overlay: {e}")
        
        # Hide the tray icon
        if hasattr(self, 'tray_icon'):
            try:
                self.tray_icon.hide()
                print("- System tray icon removed")
            except Exception as e:
                print(f"- Error hiding tray icon: {e}")
        
        # Clean up socket resources
        if hasattr(self, 'socket_thread'):
            try:
                # Socket will be closed when thread terminates
                print("- Socket resources released")
            except Exception as e:
                print(f"- Error cleaning up sockets: {e}")
        
        # Finally quit the application
        print("- Exiting application")
        self.app.quit()


if __name__ == "__main__":
    try:
        app = SystemMonitorApp()
        sys.exit(app.run())
    except KeyboardInterrupt:
        print("\nApplication terminated by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnhandled exception: {e}")
        sys.exit(1)