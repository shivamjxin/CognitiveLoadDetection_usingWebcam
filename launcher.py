import os
import sys
import time
import subprocess
import json
import platform
from pathlib import Path

def install_requirements():
    """
    Iterates through the root and all subdirectories to find and install
    every requirements.txt file required for the dual-process architecture.
    """
    print("Checking System Dependencies")
    
    # Use absolute paths for requirements to prevent terminal-location crashes
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    requirement_paths = [
        os.path.join(root_dir, "requirements.txt"),                                
        os.path.join(root_dir, "cv-backend", "requirements.txt"),    
        os.path.join(root_dir, "game_engine", "requirements.txt")    
    ]
    
    for req_path in requirement_paths:
        if os.path.exists(req_path):
            print(f"[SYSTEM] Found {req_path}. Verifying packages...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
                print(f"[SYSTEM] Dependencies for {req_path} verified.\n")
            except subprocess.CalledProcessError:
                print(f"[ERROR] Failed to install dependencies in {req_path}.")
                print("[ERROR] Please check your internet connection or the syntax of that file.")
                sys.exit(1) 
        else:
            print(f"[WARNING] {req_path} not found. Skipping.\n")



def auto_locate_labrecorder():
    """
    Universally attempts to find the LabRecorder executable with high-speed pruning.
    Features OS-detection, blacklisted directory skipping, and an I/O throttled UI.
    """
    os_name = platform.system()
    home_dir = str(Path.home())
    
    target_file = "LabRecorder.exe" if os_name == "Windows" else "LabRecorder"
    
    # Instant Check in common folders
    common_paths = [
        os.path.join(home_dir, "LabRecorder", target_file),
        os.path.join(home_dir, "Downloads", "LabRecorder", target_file),
        os.path.join(home_dir, "Desktop", "LabRecorder", target_file),
    ]
    
    if os_name == "Windows":
        common_paths.extend([
            os.path.join(os.environ.get("ProgramW6432", "C:\\Program Files"), "LabRecorder", target_file),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "LabRecorder", target_file)
        ])
    elif os_name == "Darwin":
        common_paths.extend([
            f"/Applications/LabRecorder.app/Contents/MacOS/{target_file}",
            os.path.join(home_dir, "Applications", "LabRecorder.app", "Contents", "MacOS", target_file)
        ])
    else:
        common_paths.extend([
            f"/usr/local/LabRecorder/{target_file}",
            f"/opt/LabRecorder/{target_file}"
        ])
    
    for path in common_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
            
    #  Deep Scan with Pruning
    print(f"[SYSTEM] {target_file} not found in default {os_name} paths. Initiating deep system scan...")
    
    directories_scanned = 0
    
    # to skip searching inside these massive system/dev folders
    ignore_dirs = {
        'node_modules', '.git', '.venv', 'venv', 'AppData', 
        'Library', '.npm', '.cache', '.rustup', '.cargo', 'snap'
    }
    
    for root, dirs, files in os.walk(home_dir):
        #  Remove blacklisted directories or hidden folders (starting with '.') from the search queue
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
        
        directories_scanned += 1
        
        if directories_scanned % 500 == 0:
            sys.stdout.write(f"\r[SYSTEM] Scanning... Checked {directories_scanned:,} directories so far.")
            sys.stdout.flush()

        if target_file in files:
            full_path = os.path.join(root, target_file)
            if os.access(full_path, os.X_OK):
                sys.stdout.write(f"\r[SYSTEM] Scan complete. Found in {directories_scanned:,} directories.    \n")
                sys.stdout.flush()
                return full_path
                
    sys.stdout.write(f"\r[SYSTEM] Deep scan failed after checking {directories_scanned:,} directories.    \n")
    sys.stdout.flush()
    return None



def get_or_setup_labrecorder():
    """
    Handles the consent gate, auto-search, manual fallback, and caching of the LabRecorder path.
    """
    root_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(root_dir, "local_config.json")
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            return config.get("lr_path", "")

    print("\n" + "="*50)
    print(" LABRECORDER HARDWARE SETUP")
    print("="*50)
    print("To sync your data streams, the system needs to launch LabRecorder.")
    print("We can automatically scan your Home directory to locate the software.")
    
    consent = input("\nDo you consent to an automated local hard drive scan? (Y/N): ").strip().upper()
    
    lr_path = None
    if consent == 'Y':
        lr_path = auto_locate_labrecorder()
        
    if not lr_path:
        if consent == 'Y':
            print("\n[SYSTEM] Automated scan could not find the executable.")
        else:
            print("\n[SYSTEM] Automated scan bypassed.")
            
        print("Please manually enter the absolute file path to the LabRecorder executable.")
        
        while True:
            lr_path = input("\nFile Path: ").strip().strip("'\"")
            if os.path.isfile(lr_path) and os.access(lr_path, os.X_OK):
                print("[SYSTEM] Executable verified.")
                break
            else:
                print("[ERROR] Invalid path, or the file lacks execution permissions. Please try again.")

    with open(config_path, "w") as f:
        json.dump({"lr_path": lr_path}, f)
        
    print(f"[SYSTEM] Hardware path cached successfully.")
    return lr_path



def boot_system():
    print("\n=== Cognitive Load Assessment Initialization ===")
    
    # Ensure the data directory exists before LabRecorder tries to use it
    root_dir = os.path.dirname(os.path.abspath(__file__))
    data_logs_path = os.path.join(root_dir, "data_logs")
    os.makedirs(data_logs_path, exist_ok=True)
    
    #  Fetch LabRecorder path
    lab_recorder_path = get_or_setup_labrecorder()
    
    #  Define absolute paths for the working directories
    cv_backend_dir = os.path.join(root_dir, "cv-backend")
    game_engine_dir = os.path.join(root_dir, "game_engine")
    
    #  Boot Camera
    print("\n[SYSTEM] Starting Camera Engine (30Hz)...")
    camera_process = subprocess.Popen(
        [sys.executable, "camera_engine.py"], 
        cwd=cv_backend_dir
    )
    
    time.sleep(2.0)
    
    #  Boot LabRecorder GUI
    print("[SYSTEM] Launching LabRecorder...")
    lr_process = subprocess.Popen([lab_recorder_path])
    
    time.sleep(1.0)
    
    #  Boot Pygame UI
    print("[SYSTEM] Starting Pygame UI Hub (60Hz)...")
    ui_process = subprocess.Popen(
        [sys.executable, "pygame_app.py"], 
        cwd=game_engine_dir
    )
    
    # prevent phantom tests etc
    try:
        while True:
            # Check if Pygame was closed by the user
            if ui_process.poll() is not None:
                print("\n[SYSTEM] Pygame UI closed. Ending trial phase...")
                break
                
            # Check if Camera crashed
            if camera_process.poll() is not None:
                print("\n[ERROR] Camera Engine crashed! Halting experiment to protect data integrity...")
                break
                
            # heck if LabRecorder was accidentally closed
            if lr_process.poll() is not None:
                print("\n[ERROR] LabRecorder was closed! Halting experiment to prevent unrecorded ghost trials...")
                break
                
            time.sleep(0.5) # Throttle the while loop
            
    except KeyboardInterrupt:
        print("\n[SYSTEM] Emergency Shutdown Initiated via Terminal...")
        
    finally:
        if camera_process.poll() is None:
            camera_process.terminate()
        if ui_process.poll() is None:
            ui_process.terminate()
        if lr_process.poll() is None:
            lr_process.terminate()
            
        print("[SYSTEM] All hardware hooks disconnected safely.")

if __name__ == "__main__":
    install_requirements()
    boot_system()