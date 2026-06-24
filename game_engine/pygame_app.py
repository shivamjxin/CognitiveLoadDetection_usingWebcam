import pygame
import time
import os
import json
import random
import string
from pylsl import StreamInfo, StreamOutlet

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
            # TASK 1 RESULTS
            self.task1_correct_count = 0
            self.task1_user_answer = ""

            # TASK 2 RESULTS
            self.task2_correct_count = 0
            self.task2_user_answer = ""

            # Current active task
            self.current_task = 1
            self.user_count_answer = ""
            self.count_accuracy = 0

            # Shock display timing
            self.shock_display_start = None

            # True once the code has been shown
            self.code_presented = False
            self.code_flash_done = False

            # MEMORY CODE TASK
            self.memory_code = ""
            self.memory_code_options = []
            self.memory_code_answer = ""
            self.memory_code_accuracy = 0

            # Generic text input buffer
            self.user_input = ""

            # STATE 4: TASK SHIFT SHOCK ENGINE

            # Random trigger point (generated once when State 4 starts)
            self.shock_trigger_time = None

            # True while interruption screen is active
            self.shock_active = False
            self.shock_completed = False

            self.just_entered_state9 = False

            # Override challenge
            self.safety_code = ''.join(
                random.choices(
                    string.ascii_uppercase + string.digits,
                    k=4
                )
            )
            self.override_input = ""

            # Performance metrics
            self.shock_start_ms = None
            self.shock_resolved_ms = None
            self.reaction_time_ms = None
            self.override_errors = 0 

            # State 5 Memory Recall
            self.memory_answer = ""
            self.memory_score = 0
            # Task timers
            self.task_timer_start = None
            self.task_timer_pause_start = None
            self.total_pause_time = 0

            #  EVENT GATE MEMORY (Prevents 60Hz LSL Spam)
            self.previous_state = -1
            self.previous_calib_flag = ""
            self.previous_shock_active = False

            #  LSL TELEMETRY CONNECTION (CROSS-PROCESS SYNC)
            print("Initializing UI LSL Stream...")
            ui_info = StreamInfo(
                'PygameGameEvents', 
                'Markers', 
                1,                     # 1 channel for a single string payload
                0,                     # 0 signifies event-driven/irregular sampling
                'string', 
                'mit_game_engine_002'
            )
            self.ui_outlet = StreamOutlet(ui_info)
            
            print("System initialized. UI Event Marker Stream Online.")

    def _generate_task_grid(self):
        """
        PRE-COMPUTATION ENGINE FOR STATE 4
        Calculates the (X, Y) pixel coordinates and generates random characters 
        for a 5x5 search grid. This is called exactly ONCE before entering State 4 
        to prevent math calculations from lagging the 60Hz render loop.
        """
        self.search_grid = [] # Clear any previous memory
        if self.current_task == 1:
            grid_size = 5
            cell_size = 100
        else:
            grid_size = 8
            cell_size = 70
        
        # Total size of the physical grid on screen
        total_width = grid_size * cell_size
        total_height = grid_size * cell_size

        # Math: Find the absolute center of the user's specific monitor, 
        # then subtract half the grid's width/height to find the top-left starting anchor.
        start_x = (self.width - total_width) // 2
        start_y = (self.height - total_height) // 2

        # Create a pool of random letters (A-Z), making sure the target character is removed from the distractor pool
        if self.current_task == 1:
            allowed_chars = list(
                string.ascii_uppercase.replace(
                    self.target_character,
                    ""
                )
            )
        else:
            allowed_chars = [
                "Q", "Q", "Q",
                "C",
                "D",
                "G"
            ]

        self.correct_count = 0

        # Determine how many target characters should be placed based on task
        if self.current_task == 1:
            target_count = 5
        else:
            target_count = 12

        total_cells = grid_size * grid_size
        target_positions = random.sample(range(total_cells), target_count)

        for row in range(grid_size):
            for col in range(grid_size):
                cell_index = row * grid_size + col
                # Calculate the exact pixel center for this specific cell
                center_x = start_x + (col * cell_size) + (cell_size // 2)
                center_y = start_y + (row * cell_size) + (cell_size // 2)


                if cell_index in target_positions:
                    char = self.target_character
                    color = (255, 255, 255)
                    self.correct_count += 1
                else:
                    char = random.choice(allowed_chars)
                    color = (200, 200, 200)

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
                    if self.shock_active and event.type == pygame.KEYDOWN:
                        print("KEY DETECTED")

                        if event.key == pygame.K_BACKSPACE:

                            self.override_input = self.override_input[:-1]

                        elif event.key == pygame.K_RETURN:

                            if self.override_input == self.safety_code:

                                self.shock_resolved_ms = int(time.time() * 1000)

                                self.reaction_time_ms = (
                                    self.shock_resolved_ms
                                    - self.shock_start_ms
                                )

                                self.shock_active = False
                                self.shock_completed = True

                                print(
                                    f"Shock resolved in "
                                    f"{self.reaction_time_ms} ms"
                                )

                            else:
                                self.override_errors += 1
                                self.override_input = ""

                        else:
                            self.override_input += event.unicode.upper()

                    if self.current_state == 5 and event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            self.user_count_answer = self.user_count_answer[:-1]

                        elif event.key == pygame.K_RETURN:
                            if self.user_count_answer.isdigit():
                                if int(self.user_count_answer) == self.correct_count:
                                    self.count_accuracy = 1
                                else:
                                    self.count_accuracy = 0

                                print(
                                    f"User Answer = {self.user_count_answer}, "
                                    f"Correct = {self.correct_count}"
                                )

                                self.current_state = 6

                        elif event.unicode.isdigit():
                            self.user_count_answer += event.unicode

                    if self.current_state == 8 and event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            self.task2_user_answer = self.task2_user_answer[:-1]

                        elif event.key == pygame.K_RETURN:
                            if self.task2_user_answer.isdigit():
                                if int(self.task2_user_answer) == self.correct_count:
                                    self.count_accuracy = 1
                                else:
                                    self.count_accuracy = 0

                                print(
                                    f"Task 2 Answer = {self.task2_user_answer}, "
                                    f"Correct = {self.correct_count}"
                                )

                                
                                self.current_state = 9
                                self.state_start_time = time.time()
                                self.just_entered_state9 = True

                        elif event.unicode.isdigit():
                            self.task2_user_answer += event.unicode

                    if self.current_state == 9 and event.type == pygame.KEYDOWN:
                        if self.just_entered_state9:
                            self.just_entered_state9 = False
                            continue

                        if event.key == pygame.K_BACKSPACE:
                            self.memory_code_answer = self.memory_code_answer[:-1]

                        elif event.key == pygame.K_RETURN:
                            if self.memory_code_answer.upper() == self.memory_code:
                                self.memory_code_accuracy = 1
                            else:
                                self.memory_code_accuracy = 0

                            print(
                                f"Code Answer = {self.memory_code_answer}, "
                                f"Correct Code = {self.memory_code}"
                            )

                            self.current_state = 10
                            self.state_start_time = time.time()

                        else:
                            self.memory_code_answer += event.unicode.upper()

                    # Safety Valve: Allow ESC key to break the infinite loop in Fullscreen mode.
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        running = False 
                        
                    # State 0 -> 1 Transition: Press SPACEBAR to begin the experiment.
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        if self.current_state == 0:
                            self.current_state = 1
                            self.state_start_time = time.time() # Reset stopwatch for State 1
                            print("Transitioned to STATE 1: Calibrating Extremes")

                    # Transition from STATE 6 -> 7: Move to Task 2 when SPACE is pressed in state 6
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        if self.current_state == 6:
                            self.current_state = 7
                            self.state_start_time = time.time()
                            self.task_timer_start = time.time()
                            self.total_pause_time = 0

                            self.current_task = 2
                            self.target_character = "O"

                            self.memory_code = ''.join(
                                 random.choices(
                                      string.ascii_uppercase + string.digits,
                                      k=4
                                 )
                            )
                            self.code_presented = False
                            self.code_flash_done = False

                            self._generate_task_grid()

                            print("Transitioned to TASK 2")
                
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
                    if time_in_state >= 10.0:

                        self.current_state = 4
                        self.state_start_time = time.time()
                        self.task_timer_start = time.time() + 5
                        self.total_pause_time = 0

                        # Task 1 Configuration
                        self.current_task = 1
                        self.target_character = "Q"

                        # Build search grid once
                        self._generate_task_grid()
                        
                        # # Schedule shock event once
                        #self.shock_trigger_time = random.uniform(17.0, 23.0)

                        #print(
                            #f"Shock scheduled at "
                            #f"{self.shock_trigger_time:.2f}s"
                        #)

                        print("Transitioned to STATE 4: Task Active")
                
                #  TELEMETRY LOGGING 
                # STATE 4 ALGORITHM: Shock Trigger Logic
                elif self.current_state == 4:

                    # TASK 1 VISUAL SEARCH
                    if time_in_state >= 15.0:
                        self.current_state = 5
                        self.state_start_time = time.time()
                        print("Task 1 Complete")

                elif self.current_state == 7:

                    # Show code once at 9 seconds
                    if (
                        time_in_state >= 9.0
                        and not self.code_flash_done
                    ):
                        self.code_presented = True
                        self.code_flash_done = True
                        self.shock_display_start = time.time()

                        self.task_timer_pause_start = time.time()

                    # Hide code after 3 seconds
                    if (
                        self.code_presented
                        and time.time() - self.shock_display_start >= 2.5
                    ):
                        self.code_presented = False
                        self.total_pause_time += (
                            time.time()
                            - self.task_timer_pause_start
                        )

                    if (
                        self.code_flash_done
                        and not self.code_presented
                        and time.time() - self.shock_display_start >= 9.0
                    ):
                        self.current_state = 8
                        self.state_start_time = time.time()

                elif self.current_state == 10:

                    if time_in_state >= 3.0:
                        running = False

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

                #  LSL EVENT GATE
                # Construct the JSON packet (the epoch time handled by LSL natively)
                log_packet = {
                    "state_id": self.current_state,
                    "calibration_flag": calib_flag,
                    "task_shift_active": self.shock_active,
                    "reaction_time_ms": self.reaction_time_ms,
                    "override_errors": self.override_errors,
                    "memory_answer": self.memory_answer,
                    "memory_score": self.memory_score
                }
                
                # Only push to LSL if a variable actually changed
                if (self.current_state != self.previous_state or 
                    calib_flag != self.previous_calib_flag or 
                    self.shock_active != self.previous_shock_active):
                    
                    self.ui_outlet.push_sample([json.dumps(log_packet)])
                    
                    # Update memory block
                    self.previous_state = self.current_state
                    self.previous_calib_flag = calib_flag
                    self.previous_shock_active = self.shock_active
                
                #  VISUAL RENDERING
                
                # Wipe the frame clean with a dark, non-fatiguing gray (RGB: 30, 30, 30)
                self.screen.fill((30, 30, 30))  # wipes the screen clean before drawing
                # TASK TIMER DISPLAY
                if self.current_state in [4, 7]:
                    elapsed = (
                        time.time()
                        - self.task_timer_start
                        - self.total_pause_time
                    )

                    # Task 1 countdown
                    if self.current_state == 4:
                        remaining = max(0, int(10 - elapsed))

                    # Task 2 countdown
                    else:
                        remaining = max(0, int(18 - elapsed))

                    minutes = remaining // 60
                    seconds = remaining % 60

                    timer_img = self.font.render(
                        f"TIME LEFT: {minutes:02}:{seconds:02}",
                        True,
                        (255, 80, 80)
                    )

                    self.screen.blit(
                        timer_img,
                        (self.width - 300, 20)
                    )
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
                    
                    elif self.shock_active:
                         print("RENDERING SHOCK SCREEN", self.shock_active)
                         # ==================================================
                         # RED ALERT SCREEN
                         # ==================================================

                         self.screen.fill((180, 0, 0))

                         title_img = self.font.render(
                             "TASK INTERRUPTED",
                             True,
                             (255, 255, 255)
                         )

                         code_img = self.font.render(
                             f"ENTER CODE: {self.safety_code}",
                             True,
                             (255, 255, 255)
                         ) 

                         input_img = self.font.render(
                             self.override_input,
                             True,
                             (255, 255, 0)
                         )

                         debug_img = self.font.render(
                              f"INPUT: {self.override_input}",
                              True,
                              (255, 255, 0)
                        )

                         self.screen.blit(
                             debug_img,
                             debug_img.get_rect(center=(self.width // 2,
                                                        self.height // 2 + 140)
                            )
                        )

                         self.screen.blit(
                             title_img,
                             title_img.get_rect(
                                 center=(self.width // 2,
                                         self.height // 2 - 80)
                             )
                         )

                         self.screen.blit(
                             code_img,
                             code_img.get_rect(
                                 center=(self.width // 2,
                                         self.height // 2)
                             )
                         )

                         self.screen.blit(
                             input_img,
                             input_img.get_rect(
                                 center=(self.width // 2,
                                         self.height // 2 + 80)
                             )
                         )

                    else:

                        # Normal search grid
                        for cell in self.search_grid:
                            self.screen.blit(
                                cell["img"],
                                cell["rect"]
                             )

                elif self.current_state == 5:
                    title_img = self.font.render(
                        "TASK 1 COMPLETE",
                        True,
                        (0,255,255)
                    )

                    q_img = self.font.render(
                        "How many Q's did you count?",
                        True,
                        (255,255,255)
                    )

                    answer_img = self.font.render(
                        self.user_count_answer,
                        True,
                        (255,255,0)
                    )

                    hint_img = self.font.render(
                        "Type number and press ENTER",
                        True,
                        (180,180,180)
                    )

                    self.screen.blit(
                        title_img,
                        title_img.get_rect(center=(self.width//2,150))
                    )

                    self.screen.blit(
                        q_img,
                        q_img.get_rect(center=(self.width//2,280))
                    )

                    self.screen.blit(
                        answer_img,
                        answer_img.get_rect(center=(self.width//2,380))
                    )

                    self.screen.blit(
                        hint_img,
                        hint_img.get_rect(center=(self.width//2,480))
                    )
                
                #  STATE 6 RENDERING: Assessment Complete
                elif self.current_state == 6:
                    title_img = self.font.render(
                        "TASK 2-HARD",
                        True,
                        (0,255,255)
                    )

                    line1 = self.font.render(
                        "Count how many times 'O' appears.",
                        True,
                        (255,255,255)
                    )

                    
                    line2 = self.font.render(
                        "Press SPACEBAR to begin.",
                        True,
                        (255,255,0)
                    )

                    self.screen.blit(
                        title_img,
                        title_img.get_rect(center=(self.width//2,150))
                    )

                    self.screen.blit(
                        line1,
                        line1.get_rect(center=(self.width//2,250))
                    )

                    self.screen.blit(
                        line2,
                        line2.get_rect(center=(self.width//2,320))
                    )

                    

                # STATE 7 RENDERING: Task 2 Visual Search Grid
                elif self.current_state == 7:

                    if self.code_presented:

                        title_img = self.font.render(
                            "MEMORIZE THIS CODE",
                            True,
                            (255,255,255)
                        )

                        code_img = self.font.render(
                            self.memory_code,
                            True,
                            (255,255,0)
                        )

                        self.screen.blit(
                            title_img,
                            title_img.get_rect(
                                center=(self.width//2,
                                        self.height//2 - 60)
                            )
                        )

                        self.screen.blit(
                            code_img,
                            code_img.get_rect(
                                center=(self.width//2,
                                        self.height//2 + 20)
                            )
                        )

                    else:

                        for cell in self.search_grid:
                            self.screen.blit(
                                cell["img"],
                                cell["rect"]
                            )

                elif self.current_state == 8:

                    title_img = self.font.render(
                        "TASK 2 COMPLETE",
                        True,
                        (0,255,255)
                    )

                    q_img = self.font.render(
                        "How many O's did you count?",
                        True,
                        (255,255,255)
                    )

                    answer_img = self.font.render(
                        self.task2_user_answer,
                        True,
                        (255,255,0)
                    )

                    hint_img = self.font.render(
                        "Type number and press ENTER",
                        True,
                        (180,180,180)
                    )

                    self.screen.blit(
                        title_img,
                        title_img.get_rect(center=(self.width//2,150))
                    )

                    self.screen.blit(
                        q_img,
                        q_img.get_rect(center=(self.width//2,280))
                    )

                    self.screen.blit(
                        answer_img,
                        answer_img.get_rect(center=(self.width//2,380))
                    )

                    self.screen.blit(
                        hint_img,
                        hint_img.get_rect(center=(self.width//2,480))
                    )

                elif self.current_state == 9:
                    
                    title_img = self.font.render(
                        "MEMORY RECALL",
                        True,
                        (0,255,255)
                    )

                    q_img = self.font.render(
                        "What was the code?",
                        True,
                        (255,255,255)
                    )

                    answer_img = self.font.render(
                        self.memory_code_answer,
                        True,
                        (255,255,0)
                    )

                    hint_img = self.font.render(
                        "Type code and press ENTER",
                        True,
                        (180,180,180)
                    )

                    self.screen.blit(
                        title_img,
                        title_img.get_rect(center=(self.width//2,150))
                    )

                    self.screen.blit(
                        q_img,
                        q_img.get_rect(center=(self.width//2,280))
                    )

                    self.screen.blit(
                        answer_img,
                        answer_img.get_rect(center=(self.width//2,380))
                    )

                    self.screen.blit(
                        hint_img,
                        hint_img.get_rect(center=(self.width//2,480))
                    )

                elif self.current_state == 10:

                    title_img = self.font.render(
                        "ASSESSMENT COMPLETE",
                        True,
                        (0,255,0)
                    )

                    thanks_img = self.font.render(
                        "Thank You For Participating",
                        True,
                        (255,255,255)
                    )

                    self.screen.blit(
                        title_img,
                        title_img.get_rect(
                            center=(self.width//2,
                                    self.height//2 - 40)
                        )
                    )

                    self.screen.blit(
                        thanks_img,
                        thanks_img.get_rect(
                            center=(self.width//2,
                                    self.height//2 + 40)
                        )
                    )

                #  HARDWARE FLUSH & FRAME THROTTLE
                # Swap the hidden memory buffer with the physical monitor screen
                pygame.display.flip()
                
                # Pause the script for ~16 milliseconds to strictly lock the loop at 60 FPS
                self.clock.tick(self.fps)
            
            # SYSTEM SHUTDOWN 
            pygame.quit() # Unload C-level bindings
            print("Application closed safely.")

if __name__ == "__main__":
    app = CognitiveStimulusApp()
    app.run()