"""
System Monitor Launcher
Starts the Windows 11 System Monitor application
Prevents multiple instances from running simultaneously
Implements robust instance management with file and socket locking
"""

import subprocess
import os
import sys
import pythoncom
import socket
import time
import ctypes
import tempfile
import atexit
import psutil

# Constants
SOCKET_PORT = 47189
SIGNAL_PORT = 47190
LOCK_FILE_NAME = "win11_sys_monitor.lock"

# Global variables
lock_socket = None
lock_file = None
lock_file_path = None

def is_admin():
    """Check if the script is running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def cleanup_resources():
    """Clean up resources on exit"""
    global lock_socket, lock_file
    
    # Close socket if it exists
    if lock_socket:
        try:
            lock_socket.close()
        except:
            pass
    
    # Close and remove lock file if it exists
    if lock_file:
        try:
            lock_file.close()
            # Try to remove the lock file
            if lock_file_path and os.path.exists(lock_file_path):
                os.unlink(lock_file_path)
        except:
            pass

def is_process_running(process_name="system_monitor.py"):
    """Check if a process with the given name is running"""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            # Check process command line for our script name
            if proc.info['cmdline'] and any(process_name in cmd for cmd in proc.info['cmdline']):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def is_already_running():
    """Check if the application is already running using multiple lock mechanisms"""
    global lock_socket, lock_file, lock_file_path
    
    # First check: Try to create a socket on a specific port
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Set socket to non-blocking and reuse address
        lock_socket.setblocking(False)
        lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lock_socket.bind(('localhost', SOCKET_PORT))
    except socket.error:
        return True
        
    # Second check: Try to create and lock a file in temp directory
    try:
        lock_file_path = os.path.join(tempfile.gettempdir(), LOCK_FILE_NAME)
        
        # Check if lock file exists and is stale (from crashed process)
        if os.path.exists(lock_file_path):
            # If the system monitor is not actually running, the lock is stale
            if not is_process_running():
                try:
                    os.unlink(lock_file_path)
                except:
                    pass
            else:
                return True
                
        # Create and lock the file
        lock_file = open(lock_file_path, 'w')
        lock_file.write(str(os.getpid()))
        lock_file.flush()
    except:
        # If we can't create/lock the file, another instance might be running
        return True
        
    # Register cleanup function to remove resources on exit
    atexit.register(cleanup_resources)
    
    return False

def main():
    """Main entry point for the launcher"""
    # Initialize COM for WMI
    pythoncom.CoInitialize()
    
    # Get the directory of this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(base_dir, 'system_monitor.py')
    
    # Get the path to the Python executable
    python_exe = os.path.join(base_dir, '.venv', 'Scripts', 'python.exe')
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    
    # Check if another instance is already running
    if is_already_running():
        # Send a signal to the existing instance to show the overlay
        try:
            print("System Monitor is already running. Sending signal to show overlay...")
            signal_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Try multiple times in case the other process is still starting up
            for _ in range(3):
                signal_socket.sendto(b"SHOW_OVERLAY", ('localhost', SIGNAL_PORT))
                time.sleep(0.2)
            signal_socket.close()
        except Exception as e:
            print(f"Error sending signal: {e}")
        finally:
            # Clean up and exit
            cleanup_resources()
            sys.exit(0)
    else:
        # Start the application
        try:
            print("Starting System Monitor...")
            # Use subprocess.Popen for non-blocking execution
            process = subprocess.Popen(
                [python_exe, script_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait briefly to see if the process crashes immediately
            time.sleep(1.5)
            if process.poll() is not None:
                # Process ended prematurely
                stdout, stderr = process.communicate()
                print(f"Error: System Monitor failed to start.")
                print(f"Exit code: {process.returncode}")
                print(f"Error: {stderr.decode('utf-8', errors='ignore')}")
                input("Press Enter to exit...")
        except Exception as e:
            print(f"Error launching System Monitor: {e}")
            input("Press Enter to exit...")
            sys.exit(1)

# Run the main function
if __name__ == "__main__":
    main()