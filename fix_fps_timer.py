"""
Fix the FPS timer connection in the SystemMonitor class
"""

import os
import re
import sys

def fix_fps_timer_connection():
    file_path = 'system_monitor.py'
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return False
    
    print(f"Reading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the SystemMonitor __init__ method where the timer is set up
    fps_timer_pattern = r'self\.fps_update_timer = QTimer\(\).*?self\.fps_update_timer\.timeout\.connect\(self\.fps_counter\.register_frame\).*?self\.fps_update_timer\.start\(16\)'
    
    match = re.search(fps_timer_pattern, content, re.DOTALL)
    if not match:
        print("Could not find fps_update_timer setup in SystemMonitor class.")
        return False
    
    fps_timer_code = match.group(0)
    
    # Add a wrapper function to handle exceptions
    new_code = """
    def safe_register_frame(self):
        try:
            self.fps_counter.register_frame()
        except KeyboardInterrupt:
            print("Caught KeyboardInterrupt in fps timer")
        except Exception as e:
            print(f"Error in fps timer: {e}")
    
    self.fps_update_timer = QTimer()
    self.fps_update_timer.timeout.connect(self.safe_register_frame)
    self.fps_update_timer.start(16)  # approximately 60 fps
    """
    
    # Find the SystemMonitor class definition to insert the new method
    system_monitor_class_match = re.search(r'class SystemMonitor:.*?def __init__\(self\):(.*?)def _init_gpu_monitoring', 
                                         content, re.DOTALL)
    
    if not system_monitor_class_match:
        print("Could not find SystemMonitor class __init__ method.")
        return False
    
    init_method = system_monitor_class_match.group(1)
    
    # Replace the fps_timer_code with nothing (we'll add the new method)
    modified_init = init_method.replace(fps_timer_code, "")
    
    # Add our new safe_register_frame method and timer setup
    modified_init += new_code
    
    # Replace the entire __init__ method
    modified_content = content.replace(
        f"def __init__(self):{init_method}",
        f"def __init__(self):{modified_init}"
    )
    
    if modified_content != content:
        print("Writing modified file...")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        print("Successfully fixed fps_update_timer connection in SystemMonitor class.")
        return True
    else:
        print("No changes were made.")
        return False

if __name__ == "__main__":
    fix_fps_timer_connection()