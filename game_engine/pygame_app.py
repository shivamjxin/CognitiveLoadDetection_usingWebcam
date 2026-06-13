import pygame
import time
import os
import json

class CognitiveStimulusApp:
    """
     THE UI & STIMULUS HUB (60Hz FRAMEWORK)
    
    Architecture:
    This application acts as the "Frontend" of the Decoupled Dual-Process Architecture. 
    It operates on a strict 60Hz loop, completely isolated from the OpenCV camera engine. 
    
    Responsibilities:
    1. Visual Rendering: Draw calibration targets and cognitive tasks at 60 Frames Per Second.
    2. Finite State Machine (FSM): Strictly control the timeline of the assessment (Menu -> Calibrate -> Task).
    3. Telemetry Sync: Log every single state change and UI event to a JSONL database 
       stamped with absolute UNIX epoch milliseconds so the Machine Learning pipeline 
       can perfectly align this data with the OpenCV 30Hz camera stream later.
    
    """
    
    def __init__(self):
        
        #  HARDWARE & DISPLAY INITIALIZATION
        
        pygame.init() # Boot all underlying C-level audio/video bindings
        
        # Monitor Detection: Dynamically read the user's physical screen size.
        # This guarantees our screen-percentage math (0.0 to 1.0) works on any laptop or monitor.
        screen_info = pygame.display.Info()
        self.width = screen_info.current_w
        self.height = screen_info.current_h
        
        # Canvas Creation: Launch borderless fullscreen to prevent OS distractions.
        # Note: Pygame's grid origin (X:0, Y:0) is the absolute TOP-LEFT of the monitor.
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
        pygame.display.set_caption("Golden Hybrid: Cognitive Load Assessment")
        
        # Throttling: The Clock object mathematically prevents the while-loop below 
        # from running wild and maxing out the CPU, which would crash the camera engine.
        self.clock = pygame.time.Clock()
        self.fps = 60 
        
        
        #  FINITE STATE MACHINE (FSM) MEMORY
        
        # ID 0 = STATE_MENU (Awaiting start command)
        # ID 1 = STATE_CALIBRATE_EXTREMES (4-Corner boundary mapping)
        # ID 2 = STATE_RESTING_BASELINE (TO DO)
        self.current_state = 0  
        
        # Anchor Time: We record the exact millisecond a state begins to calculate duration.
        self.state_start_time = time.time() 
        
        # State 1 Variables: Tracking the 4-corner multi-pass calibration loop
        self.calibration_targets = ["TOP_LEFT", "BOTTOM_RIGHT", "TOP_RIGHT", "BOTTOM_LEFT"]
        self.current_target_label = "NONE"
        
        
        #  TELEMETRY DATABASE CONNECTION (CROSS-PROCESS SYNC)
        
        # We open the log file ONCE during boot and hold it open in 'append' ("a") mode.
        # If we opened and closed this file 60 times a second inside the loop, 
        # the Hard Drive I/O bottleneck would instantly destroy our frame rate.
        log_path = os.path.join("..", "data_logs", "ui_events.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True) # Prevent crash if folder is missing
        self.log_file = open(log_path, "a")
        
        print(f"System initialized. Logging to: {log_path}")

    def run(self):
        """
        The Infinite Main Loop. Every iteration represents exactly 1/60th of a second.
        Pipeline order strictly follows: Input -> Math -> Database -> Render -> Wait.
        """
        running = True
        
        while running:
            
            #  EVENT PROCESSING 
            # event.get() clears the OS input buffer. Failure to call this freezes the app.
            for event in pygame.event.get():
                
                # Safety Valve: Allow ESC key to break the infinite loop in Fullscreen mode.
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False 
                    
                # State 0 -> 1 Transition: Press SPACEBAR to begin the experiment.
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    if self.current_state == 0:
                        self.current_state = 1
                        self.state_start_time = time.time() # Reset stopwatch for State 1
                        print("Transitioned to STATE 1: Calibrating Extremes")

            
            #  LOGIC & STATE UPDATES i.e FSM
            # Calculate exactly how many seconds have passed since the current state began.
            current_time = time.time()
            time_in_state = current_time - self.state_start_time 
            
            # STATE 1 ALGORITHM (4-Corner Calibration)
            if self.current_state == 1:
                # The state lasts exactly 8.0 seconds total.
                if time_in_state >= 8.0:
                    self.current_state = 2 # Advance to next state
                    self.current_target_label = "NONE"
                    self.state_start_time = time.time() # Reset stopwatch for State 2
                    print("Transitioned to STATE 2: Resting Baseline")
                else:
                    # 0.0s to 1.9s // 2.0 = Index 0 (TOP_LEFT)
                    # 2.0s to 3.9s // 2.0 = Index 1 (BOTTOM_RIGHT)
                    # 4.0s to 5.9s // 2.0 = Index 2 (TOP_RIGHT)
                    # 6.0s to 7.9s // 2.0 = Index 3 (BOTTOM_LEFT)
                    target_index = int(time_in_state // 2.0)
                    self.current_target_label = self.calibration_targets[target_index]

            #  STATE 2 ALGORITHM: 15-Second Resting Baseline
            elif self.current_state == 2:
                if time_in_state >= 15.0:
                    self.current_state = 3 
                    self.state_start_time = time.time()
                    print("Transitioned to STATE 3: Max Flex")
            
            #  TELEMETRY LOGGING 
            # Construct the JSON packet matching the Phase 2 Blueprint specifications.
            log_packet = {
                "epoch_time_ms": int(current_time * 1000), # UNIX Sync Anchor
                "state_id": self.current_state,
                "calibration_flag": self.current_target_label if self.current_state == 1 else ("REST_BASE" if self.current_state == 2 else "MENU"),
                "task_shift_active": False # Default False, only True during the Shock Event
            }
            
            # Write row to file.
            self.log_file.write(json.dumps(log_packet) + "\n")
            
            # CRITICAL: .flush() forces the OS to physically write the data to the SSD immediately. 
            # If the app crashes, we don't lose the data sitting in temporary RAM.
            self.log_file.flush()

            
            #  VISUAL RENDERING (The Canvas Paint)
            
            # Wipe the frame clean with a dark, non-fatiguing gray (RGB: 30, 30, 30)
            self.screen.fill((30, 30, 30))  # wipes the screen clean before drawing
            radius = 30 # Pixel size of the target
            color = (0, 255, 0) # High-visibility Neon Green 
            
            #  STATE 1 RENDERING: Dynamic Corner Targets 
            if self.current_state == 1:
                
                # To keep the circle fully on-screen, we offset the center coordinate
                # inward by exactly the length of the radius.
                if self.current_target_label == "TOP_LEFT":
                    target_pos = (radius, radius)
                elif self.current_target_label == "BOTTOM_RIGHT":
                    target_pos = (self.width - radius, self.height - radius)
                elif self.current_target_label == "TOP_RIGHT":
                    target_pos = (self.width - radius, radius)
                elif self.current_target_label == "BOTTOM_LEFT":
                    target_pos = (radius, self.height - radius)

                pygame.draw.circle(self.screen, color, target_pos, radius)
                pygame.draw.circle(self.screen, (255, 0, 0), target_pos, 5)

            elif self.current_state == 2:
                # Calculate Dead-Center Coordinates
                center_x = self.width // 2
                center_y = self.height // 2
                target_pos = (center_x, center_y)
                
                # Paint State 2 Targets
                pygame.draw.circle(self.screen, color, target_pos, radius)
                pygame.draw.circle(self.screen, (255, 0, 0), target_pos, 5)

            
            #  HARDWARE FLUSH & FRAME THROTTLE
            # Swap the hidden memory buffer with the physical monitor screen
            pygame.display.flip()
            
            # Pause the script for ~16 milliseconds to strictly lock the loop at 60 FPS
            self.clock.tick(self.fps) 

        
        # SYSTEM SHUTDOWN 
        self.log_file.close() # Safely sever the database connection
        pygame.quit() # Unload C-level bindings
        print("Application closed safely.")

if __name__ == "__main__":
    app = CognitiveStimulusApp()
    app.run()