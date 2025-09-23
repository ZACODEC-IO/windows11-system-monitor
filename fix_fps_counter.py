"""
Fix the KeyboardInterrupt issue in FPSCounter's register_frame method
"""

import os
import re
import sys

def fix_fps_counter_register_frame():
    file_path = 'system_monitor.py'
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return False
    
    print(f"Reading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the FPSCounter class definition
    fps_counter_class_match = re.search(r'class FPSCounter:.*?def register_frame\(self\):(.*?)def _update_loop\(self\):', 
                                       content, re.DOTALL)
    
    if not fps_counter_class_match:
        print("Could not find FPSCounter.register_frame method.")
        return False
    
    register_frame_code = fps_counter_class_match.group(1)
    
    # Add try-except block to handle KeyboardInterrupt
    new_register_frame_code = """
    def register_frame(self):
        '''Register a new frame - call this as frequently as possible'''
        try:
            current_time = time.time()
            frame_time = current_time - self.last_frame_time
            self.last_frame_time = current_time
            
            with self.lock:
                self.frame_count += 1
                # Add frame time to list (for frame time calculation)
                self.frame_times.append(frame_time)
                if len(self.frame_times) > self.max_frame_times:
                    self.frame_times.pop(0)
        except KeyboardInterrupt:
            print("Keyboard interrupt caught in register_frame")
            pass
        except Exception as e:
            print(f"Error in register_frame: {e}")
            pass
    
    """
    
    # Replace the original register_frame method with the new one
    modified_content = content.replace(
        f"def register_frame(self):{register_frame_code}",
        new_register_frame_code
    )
    
    if modified_content != content:
        print("Writing modified file...")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        print("Successfully fixed FPSCounter.register_frame method.")
        return True
    else:
        print("No changes were made.")
        return False

if __name__ == "__main__":
    fix_fps_counter_register_frame()