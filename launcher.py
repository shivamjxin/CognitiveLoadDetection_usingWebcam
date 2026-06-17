import subprocess
import sys
import time
import os

def install_requirements():
    """
    Iterates through the root and all subdirectories to find and install
    every requirements.txt file required for the dual-process architecture.
    """
    print("Checking System Dependencies")
    
    
    requirement_paths = [
        "requirements.txt",                                
        os.path.join("cv-backend", "requirements.txt"),    
        os.path.join("game_engine", "requirements.txt")    
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

def boot_system():
    print("Cognitive Load Assessment Initialization")
    
    print("[SYSTEM] Starting Camera Engine (30Hz)...")
    camera_process = subprocess.Popen(
        [sys.executable, "camera_engine.py"], 
        cwd="cv-backend"
    )
    
    
    time.sleep(2.0)
    
    print("[SYSTEM] Starting Pygame UI Hub (60Hz)...")
    ui_process = subprocess.Popen(
        [sys.executable, "pygame_app.py"], 
        cwd="game_engine"
    )
    
    try:
        camera_process.wait()
        ui_process.wait()
        
    except KeyboardInterrupt:
        print("\n[SYSTEM] Emergency Shutdown Initiated...")
        camera_process.terminate()
        ui_process.terminate()
        print("[SYSTEM] All processes terminated safely.")

if __name__ == "__main__":
    install_requirements()
    boot_system()