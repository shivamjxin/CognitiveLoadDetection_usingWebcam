# Cognitive Load Detection using Webcams
 
An autonomous, dual-process biometric data collection architecture designed to capture, synchronize, and analyze physiological indicators of cognitive stress using standard commercial webcams.
 
---
 
## The Vision: What We Are Trying to Prove
 
Historically, detecting cognitive load and acute stress required invasive hardware: EEG caps, galvanic skin response monitors, or chest-strap heart rate sensors.
 
**This project attempts to prove that high-fidelity cognitive load detection can be achieved purely through computer vision.** By subjecting a user to an automated Finite State Machine (FSM) that forces sudden shifts in cognitive demand, we can capture micro-expressions, blink rate variability, and facial muscle tension (e.g., jaw clenching). The ultimate goal is to generate a time-synced `.xdf` dataset that will train a Machine Learning model to recognize the physical "tells" of psychological stress in real-time.
 
### The Scientific Methodology
 
Our experimental protocol is designed to capture specific psychological deltas:
 
1. **The True Baseline:** Capturing the face before any anticipation or task rules are introduced.
2. **The Stress Delta:** Measuring the physical reaction to a sudden, high-stress task interruption (Task-Shift Shock).
3. **The Recovery Baseline:** Capturing the immediate physical "exhale" (shoulder drop, jaw unclench) the millisecond the brain registers the assessment is complete.
---
 
## Architecture Overview
 
To prevent UI rendering from bottlenecking the computer vision pipeline, this system utilizes a strict **Decoupled Dual-Process Architecture** synchronized over a local network using the Lab Streaming Layer (LSL).
 
- **The Camera Engine (`camera_engine.py`):** Runs strictly at **30Hz**. Utilizes OpenCV and MediaPipe to extract facial landmarks and broadcast spatial telemetry.
- **The UI Hub (`pygame_app.py`):** Runs strictly at **60Hz**. Controls the visual stimuli, handles the 6-stage Finite State Machine, and broadcasts timestamped event markers.
- **The Orchestrator (`launcher.py`):** A robust OS-level script that auto-installs exact dependencies, locates the hardware recording software, boots both engines, handles thread polling, and executes a graceful `sys.exit(0)` shutdown to protect data integrity.
---
 
## Prerequisites & System Setup
 
### Linux / Ubuntu Setup
 
This project is built for **Ubuntu/Linux** environments.
 
#### 1. LabRecorder Hardware Installation
 
Because this architecture relies on LSL synchronization, you must have the **LabRecorder** binary installed on your OS to write the data to `.xdf` files.
 
1. Download **LabRecorder v1.16.4** (Avoid 1.17.0+ on Ubuntu 22.04 Jammy due to Qt6.8 dependency clashes).
2. Install the necessary Qt6 rendering libraries:
```bash
   sudo apt update
   sudo apt install libqt6widgets6 libqt6network6 libqt6svg6
```
3. Install the LabRecorder package natively:
```bash
   sudo apt install ./LabRecorder-1.16.4-jammy_amd64.deb
```
 
*(Note: The `launcher.py` script will automatically locate `/usr/bin/LabRecorder` during the boot sequence).*
 
#### 2. Project Installation
 
Clone the repository and let the orchestrator handle the virtual environment and pip dependencies automatically.
 
```bash
git clone https://github.com/shivamjxin/CognitiveLoadDetection_usingWebcam.git
cd CognitiveLoadDetection_usingWebcam
```
 
---
 
### Windows Installation & Setup Guide
 
#### 1. Prerequisites
 
Before beginning, ensure you have the following installed:
 
- **Git for Windows**
- **Python 3.11 or 3.12** (Highly Recommended)
> **Crucial Note:** Do *not* use beta/pre-release versions of Python (like 3.14). The computer vision dependencies require pre-compiled Windows binaries ("wheels") that are only available for stable Python releases. Using a stable version prevents massive C++ compilation errors. *We highly recommend downloading Python 3.12 directly from the Microsoft Store, as it automatically configures your system PATH.*
 
#### 2. LabRecorder Hardware Installation
 
This architecture relies on LabStreamingLayer (LSL) synchronization. You must have the LabRecorder binary on your local machine to write data to `.xdf` files.
 
1. Download the Windows release of **LabRecorder** from the official LabStreamingLayer GitHub releases page.
2. Extract the downloaded folder to a permanent location on your drive (e.g., `D:\Downloads\LabRecorder`).
3. Keep track of where the actual application file (`LabRecorder.exe`) is located inside that folder.
#### 3. Project Installation
 
Open Command Prompt or PowerShell and run the following command to download the project:
 
```cmd
git clone https://github.com/shivamjxin/CognitiveLoadDetection_usingWebcam.git
```
 
> **Note on GitHub Authentication:** If a "Connect to GitHub" window pops up, click **"Sign in with your browser"**. If the browser throws an `ERR_CONNECTION_REFUSED` (127.0.0.1) error due to your Windows Firewall, cancel the process (`Ctrl + C`), run the clone command again, and select **"Sign in with a code"** instead.
 
Navigate into the downloaded project folder:
 
```cmd
cd CognitiveLoadDetection_usingWebcam
```
 
#### 4. Python Environment Setup
 
The project's orchestrator script handles downloading all required dependencies automatically, but you must manually create an isolated virtual environment first.
 
Create the virtual environment:
 
```cmd
python -m venv venv
```
 
Activate the virtual environment. *(Note: You must do this every time you open a new terminal to run the project)*:
 
```cmd
venv\Scripts\activate
```
 
*(Ensure you see `(venv)` at the start of your command prompt before proceeding).*
 
#### 5. Running the Application & Hardware Setup
 
Once the environment is activated, launch the orchestrator script:
 
```cmd
python launcher.py
```
 
**First-Time Boot Sequence:**
 
1. The script will automatically verify and install all background dependencies via pip.
2. Once complete, it will prompt you regarding the LabRecorder hardware: `Do you consent to an automated local hard drive scan? (Y/N):`
3. Type **Y** and press Enter. The script will scan common Windows directories to locate LabRecorder.
4. **If the scan fails**, the terminal will ask you to manually enter the file path.
   - Open Windows File Explorer and find your `LabRecorder.exe` application file.
   - Right-click the `.exe` file and select **"Copy as path"**.
   - Right-click in your Command Prompt to paste the exact path and press Enter.
The system will cache this path for future use and immediately boot the Camera Engine and Pygame UI hubs!
 
---
 
## How to Perform an Experiment (Dry Run Protocol)
 
To collect a valid `.xdf` dataset for the Machine Learning pipeline, adhere to the following sequence:
 
1. **Boot the System:**
```bash
   python3 launcher.py
```
2. **Consent to Hardware Scan:** Type `Y` to allow the script to locate LabRecorder.
3. **Target the Streams:** Once LabRecorder opens, click **Update**. Check the boxes next to both the `PygameGameEvents` and the `CameraEngine` streams.
4. **Set Storage:** Ensure the "Storage Location" is pointing to the `data_logs` folder within this repository.
5. **Start Recording:** Click **Start** in the LabRecorder GUI.
6. **Initiate Trial:** Click into the Pygame window and press **SPACEBAR**.
---
 
## The 6-Phase Experimental State Machine
 
Once the spacebar is pressed, the automated UI takes over. The subject must follow the on-screen prompts through 6 distinct states:
 
- **STATE 1: Calibration (13s)**
  - *Purpose:* Maps the extreme 4-corner boundaries of the subject's screen to normalize eye-tracking data.
- **STATE 2: Resting Baseline (20s)**
  - *Purpose:* Establishes standard blink-rate and neutral facial posture.
- **STATE 3: Stress Test / Max Flex (15s)**
  - *Purpose:* The subject is instructed to physically clench their jaw and tense their face. This maps the absolute upper limit of muscle contraction for the ML normalizer.
- **STATE 4: Visual Search & Task-Shift Shock (30s)**
  - *Purpose:* The subject scans a 5x5 grid for a specific target (`Q`). At a random, hidden interval, a Red Alert interruption screen triggers, requiring the subject to type an emergency override code (`67FSM2169L`). Captures the reaction time and typo error rate under acute stress.
- **STATE 5: Memory Recall**
  - *Purpose:* A multiple-choice prompt testing short-term memory retention of the grid task.
- **STATE 6: Assessment Complete (3s Auto-Shutdown)**
  - *Purpose:* Displays the final score. Captures the crucial 3-second physical "exhale" as cognitive load drops to zero, before safely terminating the Camera, UI, and LabRecorder processes.
---
 
## Next Steps: The Data Science Pipeline
 
Upon successful completion of an experiment, a unified `.xdf` file is generated in the `data_logs/` directory.
 
The next phase of this project (currently in development) involves building an extraction engine using `pyxdf` to crack open this file, merge the 30Hz physical telemetry with the 60Hz psychological event markers, and format them into a unified Pandas DataFrame for model training.
 
