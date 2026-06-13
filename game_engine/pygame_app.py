import pygame
import time
import os
import json
import random
import string

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
        self.font = pygame.font.SysFont(None, 48)

        # Canvas Creation: Launch borderless fullscreen to prevent OS distractions.
        # Note: Pygame's grid origin (X:0, Y:0) is the absolute TOP-LEFT of the monitor.
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN)
        pygame.display.set_caption("Cognitive Load Assessment")
        
        # Throttling: The Clock object mathematically prevents the while-loop below 
        # from running wild and maxing out the CPU, which would crash the camera engine.
        self.clock = pygame.time.Clock()
        self.fps = 60 
        
        
        #  FINITE STATE MACHINE (FSM) MEMORY
        
        # ID 0 = STATE_MENU (Awaiting start command)
        # ID 1 = STATE_CALIBRATE_EXTREMES (4-Corner boundary mapping)
        # ID 2 = STATE_RESTING_BASELINE 
        self.current_state = 0  
        
        # Anchor Time: We record the exact millisecond a state begins to calculate duration.
        self.state_start_time = time.time() 
        
        # State 1 Variables: Tracking the 4-corner multi-pass calibration loop
        self.calibration_targets = ["TOP_LEFT", "BOTTOM_RIGHT", "TOP_RIGHT", "BOTTOM_LEFT"]
        self.current_target_label = "NONE"
        
        # State 4 Variables: Task Grid Memory
        self.search_grid = [] # Will hold the pre-calculated 5x5 board
        self.target_character = "Q" # The specific item the user is hunting for

        #  TELEMETRY DATABASE CONNECTION (CROSS-PROCESS SYNC)
        # We open the log file ONCE during boot and hold it open in 'append' ("a") mode.
        # If we opened and closed this file 60 times a second inside the loop, 
        # the Hard Drive I/O bottleneck would instantly destroy our frame rate.
        log_path = os.path.join("..", "data_logs", "ui_events.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True) # Prevent crash if folder is missing
        self.log_file = open(log_path, "a")
        
        print(f"System initialized. Logging to: {log_path}")

    def _generate_task_grid(self):
            """
            PRE-COMPUTATION ENGINE FOR STATE 4
            Calculates the (X, Y) pixel coordinates and generates random characters 
            for a 5x5 search grid. This is called exactly ONCE before entering State 4 
            to prevent math calculations from lagging the 60Hz render loop.
            """
            self.search_grid = [] # Clear any previous memory
            grid_size = 5
            cell_size = 100 # 100x100 pixel boundary per letter
            
            # Total size of the physical grid on screen
            total_width = grid_size * cell_size
            total_height = grid_size * cell_size

            # Math: Find the absolute center of the user's specific monitor, 
            # then subtract half the grid's width/height to find the top-left starting anchor.
            start_x = (self.width - total_width) // 2
            start_y = (self.height - total_height) // 2

            # Create a pool of random letters (A-Z), making sure 'Q' is removed from the random pool
            allowed_chars = list(string.ascii_uppercase.replace(self.target_character, ""))

            for row in range(grid_size):
                for col in range(grid_size):
                    # Calculate the exact pixel center for this specific cell
                    center_x = start_x + (col * cell_size) + (cell_size // 2)
                    center_y = start_y + (row * cell_size) + (cell_size // 2)

                    # 10% chance to spawn our target 'Q', otherwise pick a random letter
                    if random.random() < 0.10:
                        char = self.target_character
                        color = (255, 255, 255) # White
                    else:
                        char = random.choice(allowed_chars)
                        color = (200, 200, 200) # Slightly dimmed white for distractor letters

                    #  Render the text into an image surface NOW, 
                    # so the 60Hz loop only has to paste a picture, not render a font.
                    char_img = self.font.render(char, True, color)
                    char_rect = char_img.get_rect(center=(center_x, center_y))

                    # Store the fully prepared package in memory
                    self.search_grid.append({
                        "img": char_img,
                        "rect": char_rect,
                        "char": char
                    })

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
                # The state lasts exactly 13.0 seconds total (5s instructions + 8s calibration).
                if time_in_state >= 13.0:
                    self.current_state = 2 # Advance to next state
                    self.current_target_label = "NONE"
                    self.state_start_time = time.time() # Reset stopwatch for State 2
                    print("Transitioned to STATE 2: Resting Baseline")
                elif time_in_state < 5.0:
                    # Buffer phase: Hold the instruction flag
                    self.current_target_label = "INSTRUCTION"
                else:
                    # Math trick offset by 5.0 seconds
                    # 5.0s to 6.9s // 2.0 = Index 0 (TOP_LEFT)
                    # 7.0s to 8.9s // 2.0 = Index 1 (BOTTOM_RIGHT)
                    # 9.0s to 10.9s // 2.0 = Index 2 (TOP_RIGHT)
                    # 11.0s to 12.9s // 2.0 = Index 3 (BOTTOM_LEFT)
                    target_index = int((time_in_state - 5.0) // 2.0)
                    self.current_target_label = self.calibration_targets[target_index]

            #  STATE 2 ALGORITHM: 15-Second Resting Baseline
            elif self.current_state == 2:
                # 5s instructions + 15s task = 20.0s total
                if time_in_state >= 20.0:
                    self.current_state = 3 
                    self.state_start_time = time.time()
                    print("Transitioned to STATE 3: Max Flex")

            #  STATE 3 ALGORITHM: 5-Second Max Flex 
            elif self.current_state == 3:
                # 5s instructions + 5s task = 10.0s total
                if time_in_state >= 10.0:
                    self.current_state = 4 
                    self.state_start_time = time.time()
                    self._generate_task_grid() # Generate the memory grid exactly once before starting
                    print("Transitioned to STATE 4: Task Active")
            
            #  TELEMETRY LOGGING 
            # Determine the correct flag string based on state
            if self.current_state == 1:
                calib_flag = self.current_target_label # Will be "INSTRUCTION" for first 5s
            elif self.current_state == 2:
                calib_flag = "INSTRUCTION" if time_in_state < 5.0 else "REST_BASE"
            elif self.current_state == 3:
                calib_flag = "INSTRUCTION" if time_in_state < 5.0 else "MAX_FLEX"
            elif self.current_state == 4:
                calib_flag = "INSTRUCTION" if time_in_state < 5.0 else "RUNNING"
            else:
                calib_flag = "MENU"

            # Construct the JSON packet matching the Phase 2 Blueprint specifications.
            log_packet = {
                "epoch_time_ms": int(current_time * 1000), 
                "state_id": self.current_state,
                "calibration_flag": calib_flag,
                "task_shift_active": False 
            }
            
            # Write row to file.
            self.log_file.write(json.dumps(log_packet) + "\n")
            
            # CRITICAL: .flush() forces the OS to physically write the data to the SSD immediately. 
            # If the app crashes, we don't lose the data sitting in temporary RAM.
            self.log_file.flush()

            
            #  VISUAL RENDERING
            
            # Wipe the frame clean with a dark, non-fatiguing gray (RGB: 30, 30, 30)
            self.screen.fill((30, 30, 30))  # wipes the screen clean before drawing
            radius = 30 # Pixel size of the target
            color = (0, 255, 0) # High-visibility Neon Green 
            
            #  STATE 0 RENDERING: The Welcome Menu 
            if self.current_state == 0:
                title_img = self.font.render("COGNITIVE LOAD ASSESSMENT", True, (0, 255, 255))
                sub_img = self.font.render("Press SPACEBAR to begin...", True, (255, 255, 255))
                self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 30)))
                self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 30)))

            #  STATE 1 RENDERING: Dynamic Corner Targets 
            elif self.current_state == 1:
                if time_in_state < 5.0:
                    # --- State 1: 5-Second Instruction Phase ---
                    title_img = self.font.render("PHASE 1: CALIBRATION", True, (0, 255, 255))
                    sub_img = self.font.render("Focus strictly on the red dot inside the green circles.", True, (255, 255, 255))
                    timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                    
                    self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                    self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                    self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                
                else:
                    # --- State 1: Target Rendering Phase ---
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
                if time_in_state < 5.0:
                    # --- State 2: 5-Second Instruction Phase ---
                    title_img = self.font.render("PHASE 2: RESTING BASELINE", True, (0, 255, 255))
                    sub_img = self.font.render("Stare at the center target and completely relax your face.", True, (255, 255, 255))
                    timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                    
                    self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                    self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                    self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                
                else:
                    # --- State 2: Target Rendering Phase ---
                    # Calculate Dead-Center Coordinates
                    center_x = self.width // 2
                    center_y = self.height // 2
                    target_pos = (center_x, center_y)
                    
                    # Paint State 2 Targets
                    pygame.draw.circle(self.screen, color, target_pos, radius)
                    pygame.draw.circle(self.screen, (255, 0, 0), target_pos, 5)

            # STATE 3 RENDERING: Max Flex Instructions
            elif self.current_state == 3:
                if time_in_state < 5.0:
                    # --- State 3: 5-Second Instruction Phase ---
                    title_img = self.font.render("PHASE 3: STRESS TEST", True, (0, 255, 255))
                    sub_img = self.font.render("Get ready to bite down and tense your face", True, (255, 200, 50))
                    timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                    
                    self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                    self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                    self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                
                else:
                    # --- State 3: Active Flex Phase ---
                    #  Render the text strings into images (Text, Anti-Alias True, RGB Color)
                    prompt_img = self.font.render("CLENCH JAW AND TENSE YOUR FACE AS HARD AS POSSIBLE!", True, (255, 50, 50))
                    
                    # Dynamic countdown math (offset by the 5 instruction seconds)
                    seconds_left = 5 - int(time_in_state - 5.0)
                    timer_img = self.font.render(f"Hold for {seconds_left} seconds...", True, (200, 200, 200))
                    
                    #  Get the geometric center of those text images
                    prompt_rect = prompt_img.get_rect(center=(self.width // 2, self.height // 2 - 40))
                    timer_rect = timer_img.get_rect(center=(self.width // 2, self.height // 2 + 40))
                    
                    #  Blit (stamp) the images onto the screen
                    self.screen.blit(prompt_img, prompt_rect)
                    self.screen.blit(timer_img, timer_rect)
                    
            # --- STATE 4 RENDERING: The Visual Search Task ---
            elif self.current_state == 4:
                if time_in_state < 5.0:
                    # --- State 4: 5-Second Instruction Phase ---
                    title_img = self.font.render("PHASE 4: VISUAL SEARCH", True, (0, 255, 255))
                    sub_img = self.font.render(f"Scan the grid and count how many times '{self.target_character}' appears.", True, (255, 255, 255))
                    timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                    
                    self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                    self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                    self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                
                else:
                    # --- State 4: Active Task Phase ---
                    # Instantly stamp all 25 letters onto the screen using our pre-calculated memory
                    for cell in self.search_grid:
                        self.screen.blit(cell["img"], cell["rect"])
            
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