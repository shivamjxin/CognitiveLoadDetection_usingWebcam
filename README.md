<h1> Cognitive Load Detection using Webcams</h1>
<p>An autonomous, dual-process biometric data collection architecture designed to capture, synchronize, and analyze physiological indicators of cognitive stress using standard commercial webcams.</p>

<h2> The Vision: What We Are Trying to Prove</h2>
<p>Historically, detecting cognitive load and acute stress required invasive hardware: EEG caps, galvanic skin response monitors, or chest-strap heart rate sensors.</p>
<p><strong>This project attempts to prove that high-fidelity cognitive load detection can be achieved purely through computer vision.</strong> By subjecting a user to an automated Finite State Machine (FSM) that forces sudden shifts in cognitive demand, we can capture micro-expressions, blink rate variability, and facial muscle tension (e.g., jaw clenching). The ultimate goal is to generate a time-synced <code>.xdf</code> dataset that will train a Machine Learning model to recognize the physical "tells" of psychological stress in real-time.</p>

<h3>The Scientific Methodology</h3>
<p>Our experimental protocol is designed to capture specific psychological deltas:</p>
<ol>
  <li><strong>The True Baseline:</strong> Capturing the face before any anticipation or task rules are introduced.</li>
  <li><strong>The Stress Delta:</strong> Measuring the physical reaction to a sudden, high-stress task interruption (Task-Shift Shock).</li>
  <li><strong>The Recovery Baseline:</strong> Capturing the immediate physical "exhale" (shoulder drop, jaw unclench) the millisecond the brain registers the assessment is complete.</li>
</ol>

<hr>

<h2> Architecture Overview</h2>
<p>To prevent UI rendering from bottlenecking the computer vision pipeline, this system utilizes a strict <strong>Decoupled Dual-Process Architecture</strong> synchronized over a local network using the Lab Streaming Layer (LSL).</p>
<ul>
  <li><strong>The Camera Engine (<code>camera_engine.py</code>):</strong> Runs strictly at <strong>30Hz</strong>. Utilizes OpenCV and MediaPipe to extract facial landmarks and broadcast spatial telemetry.</li>
  <li><strong>The UI Hub (<code>pygame_app.py</code>):</strong> Runs strictly at <strong>60Hz</strong>. Controls the visual stimuli, handles the 6-stage Finite State Machine, and broadcasts timestamped event markers.</li>
  <li><strong>The Orchestrator (<code>launcher.py</code>):</strong> A robust OS-level script that auto-installs exact dependencies, locates the hardware recording software, boots both engines, handles thread polling, and executes a graceful <code>sys.exit(0)</code> shutdown to protect data integrity.</li>
</ul>

<hr>

<h2>Prerequisites &amp; System Setup</h2>
<p>This project is built for <strong>Ubuntu/Linux</strong> environments.</p>

<h3>1. LabRecorder Hardware Installation</h3>
<p>Because this architecture relies on LSL synchronization, you must have the <strong>LabRecorder</strong> binary installed on your OS to write the data to <code>.xdf</code> files.</p>
<ol>
  <li>Download <strong>LabRecorder v1.16.4</strong> (Avoid 1.17.0+ on Ubuntu 22.04 Jammy due to Qt6.8 dependency clashes).</li>
  <li>Install the necessary Qt6 rendering libraries:
    <pre><code>sudo apt update
sudo apt install libqt6widgets6 libqt6network6 libqt6svg6</code></pre>
  </li>
  <li>Install the LabRecorder package natively:
    <pre><code>sudo apt install ./LabRecorder-1.16.4-jammy_amd64.deb</code></pre>
  </li>
</ol>
<p><em>(Note: The <code>launcher.py</code> script will automatically locate <code>/usr/bin/LabRecorder</code> during the boot sequence).</em></p>

<h3>2. Project Installation</h3>
<p>Clone the repository and let the orchestrator handle the virtual environment and pip dependencies automatically.</p>
<pre><code>git clone https://github.com/yourusername/CognitiveLoadDetection_usingWebcam.git
cd CognitiveLoadDetection_usingWebcam</code></pre>

<hr>

<h2> How to Perform an Experiment (Dry Run Protocol)</h2>
<p>To collect a valid <code>.xdf</code> dataset for the Machine Learning pipeline, adhere to the following sequence:</p>
<ol>
  <li><strong>Boot the System:</strong>
    <pre><code>python3 launcher.py</code></pre>
  </li>
  <li><strong>Consent to Hardware Scan:</strong> Type <code>Y</code> to allow the script to locate LabRecorder.</li>
  <li><strong>Target the Streams:</strong> Once LabRecorder opens, click <strong>Update</strong>. Check the boxes next to both the <code>PygameGameEvents</code> and the <code>CameraEngine</code> streams.</li>
  <li><strong>Set Storage:</strong> Ensure the "Storage Location" is pointing to the <code>data_logs</code> folder within this repository.</li>
  <li><strong>Start Recording:</strong> Click <strong>Start</strong> in the LabRecorder GUI.</li>
  <li><strong>Initiate Trial:</strong> Click into the Pygame window and press <strong>SPACEBAR</strong>.</li>
</ol>

<hr>

<h2>The 6-Phase Experimental State Machine</h2>
<p>Once the spacebar is pressed, the automated UI takes over. The subject must follow the on-screen prompts through 6 distinct states:</p>
<ul>
  <li><strong>STATE 1: Calibration (13s)</strong>
    <ul><li><em>Purpose:</em> Maps the extreme 4-corner boundaries of the subject's screen to normalize eye-tracking data.</li></ul>
  </li>
  <li><strong>STATE 2: Resting Baseline (20s)</strong>
    <ul><li><em>Purpose:</em> Establishes standard blink-rate and neutral facial posture.</li></ul>
  </li>
  <li><strong>STATE 3: Stress Test / Max Flex (15s)</strong>
    <ul><li><em>Purpose:</em> The subject is instructed to physically clench their jaw and tense their face. This maps the absolute upper limit of muscle contraction for the ML normalizer.</li></ul>
  </li>
  <li><strong>STATE 4: Visual Search &amp; Task-Shift Shock (30s)</strong>
    <ul><li><em>Purpose:</em> The subject scans a 5x5 grid for a specific target ('Q'). At a random, hidden interval, a Red Alert interruption screen triggers, requiring the subject to type an emergency override code (<code>67FSM2169L</code>). Captures the reaction time and typo error rate under acute stress.</li></ul>
  </li>
  <li><strong>STATE 5: Memory Recall</strong>
    <ul><li><em>Purpose:</em> A multiple-choice prompt testing short-term memory retention of the grid task.</li></ul>
  </li>
  <li><strong>STATE 6: Assessment Complete (3s Auto-Shutdown)</strong>
    <ul><li><em>Purpose:</em> Displays the final score. Captures the crucial 3-second physical "exhale" as cognitive load drops to zero, before safely terminating the Camera, UI, and LabRecorder processes.</li></ul>
  </li>
</ul>

<hr>

<h2> Next Steps: The Data Science Pipeline</h2>
<p>Upon successful completion of an experiment, a unified <code>.xdf</code> file is generated in the <code>data_logs/</code> directory.</p>
<p>The next phase of this project (currently in development) involves building an extraction engine using <code>pyxdf</code> to crack open this file, merge the 30Hz physical telemetry with the 60Hz psychological event markers, and format them into a unified Pandas DataFrame for model training.</p>
