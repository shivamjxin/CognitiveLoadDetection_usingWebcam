import pygame
import math
import time
import os
import json
import random
import string
import sys
from pylsl import StreamInfo, StreamOutlet

class CognitiveStimulusApp:
    """
        THE UI & STIMULUS HUB (60Hz FRAMEWORK)
        
        Architecture:
        This application acts as the "Frontend" of the Decoupled Dual-Process Architecture. 
        It operates on a strict 60Hz loop, completely isolated from the OpenCV camera engine. 
        
        Responsibilities:
        1. Visual Rendering: Draw calibration targets and cognitive tasks at 60 FPS.
        2. Finite State Machine (FSM): Strictly control the timeline of the assessment.
        3. Telemetry Sync: Log state changes and UI events to an LSL stream.
    """
        
    def __init__(self):
            
            # HARDWARE & DISPLAY INITIALIZATION
            pygame.init()
            
            # Monitor Detection
            screen_info = pygame.display.Info()
            self.native_width = screen_info.current_w
            self.native_height = screen_info.current_h
            self.font = pygame.font.SysFont(None, 48)
            self.timer_font = pygame.font.SysFont(None, 60)

            # Boot into a movable window to access LabRecorder
            self.screen = pygame.display.set_mode((800, 600))
            pygame.display.set_caption("Cognitive Load Assessment")

            # Set active dimensions
            self.width = 800
            self.height = 600
            
            self.clock = pygame.time.Clock()
            self.fps = 60 
            
            # FINITE STATE MACHINE (FSM) MEMORY
            self.current_state = 0  
            self.state_start_time = time.time() 
            
            # State 1 Variables
            self.calibration_targets = ["TOP_LEFT", "BOTTOM_RIGHT", "TOP_RIGHT", "BOTTOM_LEFT"]
            self.current_target_label = "NONE"
            
            # Task Grid Memory
            self.search_grid = []
            self.target_character = "Q" 
            self.correct_count = 0

            # TASK RESULTS MEMORY
            self.current_task = 1
            self.user_count_answer = ""
            self.task2_user_answer = ""
            self.count_accuracy = 0

            # Shock display timing
            self.shock_display_start = None
            self.code_presented = False
            self.code_flash_done = False

            # MEMORY CODE TASK
            self.memory_code = ""
            self.memory_code_answer = ""
            self.memory_code_accuracy = 0

            # STATE 4: TASK SHIFT SHOCK ENGINE
            self.shock_trigger_time = None
            self.shock_active = False
            self.shock_completed = False
            self.just_entered_state9 = False

            # Override challenge
            self.safety_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
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
            self.red_warning_triggered = False
            self.red_warning_start = 0

            # EVENT GATE MEMORY (Prevents 60Hz LSL Spam while tracking keystrokes)
            self.previous_state = -1
            self.previous_calib_flag = ""
            self.previous_shock_active = False
            self.previous_override_errors = 0
            self.previous_override_input = ""
            self.previous_user_count_answer = ""
            self.previous_task2_user_answer = ""
            self.previous_memory_code_answer = ""

            # LSL TELEMETRY CONNECTION (CROSS-PROCESS SYNC)
            print("Initializing UI LSL Stream...")
            ui_info = StreamInfo(
                'PygameGameEvents', 
                'Markers', 
                1,                     
                0,                     
                'string', 
                'mit_game_engine_002'
            )
            self.ui_outlet = StreamOutlet(ui_info)
            print("System initialized. UI Event Marker Stream Online.")

    def _generate_task_grid(self):
        """ PRE-COMPUTATION ENGINE FOR SEARCH GRIDS """
        self.search_grid = [] 
        if self.current_task == 1:
            grid_size = 5
            cell_size = 100
        else:
            grid_size = 10
            cell_size = 60
        
        total_width = grid_size * cell_size
        total_height = grid_size * cell_size

        start_x = (self.width - total_width) // 2
        start_y = (self.height - total_height) // 2
        self.grid_start_y = start_y
        self.grid_start_x = start_x

        if self.current_task == 1:
            allowed_chars = list(string.ascii_uppercase.replace(self.target_character, ""))
        else:
            allowed_chars = ["Q", "Q", "Q", "C", "D", "G"]

        self.correct_count = 0

        # Determine how many target characters should be placed based on task
        if self.current_task == 1:
            target_count = 5
        else:
            target_count = 13

        total_cells = grid_size * grid_size
        target_positions = random.sample(range(total_cells), target_count)

        for row in range(grid_size):
            for col in range(grid_size):
                cell_index = row * grid_size + col

                center_x = start_x + (col * cell_size) + (cell_size // 2)
                center_y = start_y + (row * cell_size) + (cell_size // 2)

                if cell_index in target_positions:
                    char = self.target_character
                    self.correct_count += 1
                else:
                    char = random.choice(allowed_chars)

                color = (255,255,255)

                char_img = self.font.render(char, True, color)
                char_rect = char_img.get_rect(center=(center_x, center_y))

                self.search_grid.append({
                    "img": char_img,
                    "rect": char_rect,
                    "char": char
                })

    def run(self):
            """ Infinite Main Loop """
            running = True
            
            while running:
                
                # EVENT PROCESSING 
                for event in pygame.event.get():
                    if self.shock_active and event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            self.override_input = self.override_input[:-1]
                        elif event.key == pygame.K_RETURN:
                            if self.override_input == self.safety_code:
                                self.shock_resolved_ms = int(time.time() * 1000)
                                self.reaction_time_ms = (self.shock_resolved_ms - self.shock_start_ms)
                                self.shock_active = False
                                self.shock_completed = True
                                print(f"Shock resolved in {self.reaction_time_ms} ms")
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
                                print(f"Task 1 Answer = {self.user_count_answer}, Correct = {self.correct_count}")
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
                                print(f"Task 2 Answer = {self.task2_user_answer}, Correct = {self.correct_count}")
                                
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
                            print(f"Code Answer = {self.memory_code_answer}, Correct Code = {self.memory_code}")
                            self.current_state = 10
                            self.state_start_time = time.time()
                        else:
                            self.memory_code_answer += event.unicode.upper()

                    # Safety Valve
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        running = False 
                        
                    # State 0 -> 1 Transition
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        if self.current_state == 0:
                            self.current_state = 1
                            self.state_start_time = time.time() 
                            # Convert to Fullscreen and update dimensions
                            self.screen = pygame.display.set_mode((self.native_width, self.native_height), pygame.FULLSCREEN)
                            self.width = self.native_width
                            self.height = self.native_height
                            print("Transitioned to STATE 1: Calibrating Extremes")

                    # Transition from STATE 6 -> 7
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        if self.current_state == 6:
                            self.current_state = 7
                            self.state_start_time = time.time()

                            self.task_timer_start = time.time()
                            self.total_pause_time = 0

                            self.current_task = 2
                            self.target_character = "O"
                            self.memory_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
                            self.code_presented = False
                            self.code_flash_done = False
                            self._generate_task_grid()
                            print("Transitioned to TASK 2")
                
                # LOGIC & STATE UPDATES i.e FSM
                current_time = time.time()
                time_in_state = current_time - self.state_start_time 
                
                if self.current_state == 1:
                    if time_in_state >= 13.0:
                        self.current_state = 2 
                        self.current_target_label = "NONE"
                        self.state_start_time = time.time() 
                        print("Transitioned to STATE 2: Resting Baseline")
                    elif time_in_state < 5.0:
                        self.current_target_label = "INSTRUCTION"
                    else:
                        target_index = int((time_in_state - 5.0) // 2.0)
                        self.current_target_label = self.calibration_targets[target_index]

                elif self.current_state == 2:
                    if time_in_state >= 20.0:
                        self.current_state = 3 
                        self.state_start_time = time.time()
                        print("Transitioned to STATE 3: Max Flex")

                elif self.current_state == 3:
                    if time_in_state >= 10.0:
                        self.current_state = 4
                        self.state_start_time = time.time()

                        self.task_timer_start = time.time() + 5
                        self.total_pause_time = 0
                        # Task 1 Configuration

                        self.current_task = 1
                        self.target_character = "Q"
                        self._generate_task_grid()
                        print("Transitioned to STATE 4: Task Active")
                
                elif self.current_state == 4:
                    if time_in_state >= 15.0:
                        self.current_state = 5
                        self.state_start_time = time.time()
                        print("Task 1 Complete")

                elif self.current_state == 7:
                    if time_in_state >= 10.0 and not self.code_flash_done:
                        self.code_presented = True
                        self.code_flash_done = True
                        self.shock_display_start = time.time()
                        self.task_timer_pause_start = time.time()

                    # Hide code after 2.5 seconds
                    if (
                        self.code_presented
                        and time.time() - self.shock_display_start >= 2.5
                    ):
                        self.code_presented = False
                        self.total_pause_time += (
                            time.time()
                            - self.task_timer_pause_start
                        )

                    # Transition to next state after 9 seconds since code presentation
                    if (
                        self.code_flash_done
                        and not self.code_presented
                        and time.time() - self.shock_display_start >= 10.0
                    ):
                        self.current_state = 8
                        self.state_start_time = time.time()

                elif self.current_state == 10:
                    if time_in_state >= 3.0:
                        running = False

                # LSL Event Gate Validation
                if self.current_state == 1:
                    calib_flag = self.current_target_label 
                elif self.current_state == 2:
                    calib_flag = "INSTRUCTION" if time_in_state < 5.0 else "REST_BASE"
                elif self.current_state == 3:
                    calib_flag = "INSTRUCTION" if time_in_state < 5.0 else "MAX_FLEX"
                elif self.current_state == 4:
                    calib_flag = "INSTRUCTION" if time_in_state < 5.0 else "RUNNING"
                else:
                    calib_flag = "MENU"

                # LSL EVENT GATE (High-Fidelity Machine Learning Payload)
                log_packet = {
                    "time_in_state": round(time_in_state, 3), # Precise FSM clock
                    "state_id": self.current_state,
                    "calibration_flag": calib_flag,
                    
                    "active_task": self.current_task,
                    "target_character": self.target_character,
                    
                    "task_shift_active": self.shock_active,
                    "safety_code_target": self.safety_code,
                    "override_input_current": self.override_input,
                    "reaction_time_ms": self.reaction_time_ms,
                    "override_errors": self.override_errors,
                    
                    "ground_truth_count": self.correct_count,
                    "user_count_answer": self.user_count_answer, 
                    "task2_user_answer": self.task2_user_answer, 
                    "count_accuracy": self.count_accuracy,       
                    
                    "memory_code_target": self.memory_code,
                    "memory_code_answer": self.memory_code_answer,
                    "memory_code_accuracy": self.memory_code_accuracy
                }
                
                # Push if ANY tracked variable changes (Logs keystrokes instantly)
                if (self.current_state != self.previous_state or 
                    calib_flag != self.previous_calib_flag or 
                    self.shock_active != self.previous_shock_active or
                    self.override_errors != self.previous_override_errors or
                    self.override_input != self.previous_override_input or
                    self.user_count_answer != self.previous_user_count_answer or
                    self.task2_user_answer != self.previous_task2_user_answer or
                    self.memory_code_answer != self.previous_memory_code_answer):
                    
                    self.ui_outlet.push_sample([json.dumps(log_packet)])
                    
                    # Update memory block
                    self.previous_state = self.current_state
                    self.previous_calib_flag = calib_flag
                    self.previous_shock_active = self.shock_active
                    self.previous_override_errors = self.override_errors
                    self.previous_override_input = self.override_input
                    self.previous_user_count_answer = self.user_count_answer
                    self.previous_task2_user_answer = self.task2_user_answer
                    self.previous_memory_code_answer = self.memory_code_answer
                
                # VISUAL RENDERING
                self.screen.fill((30, 30, 30))  
                radius = 30 
                color = (0, 255, 0) 
                
                # TASK TIMER DISPLAY
                # TASK 2 TIMER DISPLAY ONLY
                if self.current_state == 7:

                    elapsed = (
                        time.time()
                        - self.task_timer_start
                        - self.total_pause_time
                    )

                    remaining = max(0, int(20 - elapsed))
                    if remaining <= 5 and not self.red_warning_triggered:
                          self.red_warning_triggered = True
                          self.red_warning_start = time.time()

                    minutes = remaining // 60
                    seconds = remaining % 60

                    if remaining <= 5:

                          timer_color = (255, 0, 0)

                          if time.time() - self.red_warning_start < 0.35:
                                timer_font = pygame.font.SysFont(None, 80)
                          else:
                                timer_font = self.timer_font

                    else:
                          timer_color = (255, 255, 0)
                          timer_font = self.timer_font

                    timer_img = timer_font.render(
                        f"TIME LEFT: {minutes:02}:{seconds:02}", True, timer_color
                    )

                    timer_rect = timer_img.get_rect(center=(self.width // 2, self.grid_start_y - 70))
                    self.screen.blit(timer_img, timer_rect)

                if self.current_state == 0:
                    title_img = self.font.render("COGNITIVE LOAD ASSESSMENT", True, (0, 255, 255))
                    sub_img = self.font.render("Press SPACEBAR to begin...", True, (255, 255, 255))
                    self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 30)))
                    self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 30)))

                elif self.current_state == 1:
                    if time_in_state < 5.0:
                        title_img = self.font.render("PHASE 1: CALIBRATION", True, (0, 255, 255))
                        sub_img = self.font.render("Focus strictly on the red dot inside the green circles.", True, (255, 255, 255))
                        timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                        
                        self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                        self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                        self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                    else:
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
                        title_img = self.font.render("PHASE 2: RESTING BASELINE", True, (0, 255, 255))
                        sub_img = self.font.render("Stare at the center target and completely relax your face.", True, (255, 255, 255))
                        timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                        
                        self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                        self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                        self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                    else:
                        center_x = self.width // 2
                        center_y = self.height // 2
                        target_pos = (center_x, center_y)
                        
                        pygame.draw.circle(self.screen, color, target_pos, radius)
                        pygame.draw.circle(self.screen, (255, 0, 0), target_pos, 5)

                elif self.current_state == 3:
                    if time_in_state < 5.0:
                        title_img = self.font.render("PHASE 3: STRESS TEST", True, (0, 255, 255))
                        sub_img = self.font.render("Get ready to bite down and tense your face", True, (255, 200, 50))
                        timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                        
                        self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                        self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                        self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                    else:
                        prompt_img = self.font.render("CLENCH JAW AND TENSE YOUR FACE AS HARD AS POSSIBLE!", True, (255, 50, 50))
                        seconds_left = 5 - int(time_in_state - 5.0)
                        timer_img = self.font.render(f"Hold for {seconds_left} seconds...", True, (200, 200, 200))
                        
                        prompt_rect = prompt_img.get_rect(center=(self.width // 2, self.height // 2 - 40))
                        timer_rect = timer_img.get_rect(center=(self.width // 2, self.height // 2 + 40))
                        
                        self.screen.blit(prompt_img, prompt_rect)
                        self.screen.blit(timer_img, timer_rect)
                        
                elif self.current_state == 4:
                    if time_in_state < 5.0:
                        title_img = self.font.render("PHASE 4: VISUAL SEARCH", True, (0, 255, 255))
                        sub_img = self.font.render(f"Scan the grid and count how many times '{self.target_character}' appears.", True, (255, 255, 255))
                        timer_img = self.font.render(f"Starting in {5 - int(time_in_state)}...", True, (150, 150, 150))
                        
                        self.screen.blit(title_img, title_img.get_rect(center=(self.width // 2, self.height // 2 - 50)))
                        self.screen.blit(sub_img, sub_img.get_rect(center=(self.width // 2, self.height // 2 + 10)))
                        self.screen.blit(timer_img, timer_img.get_rect(center=(self.width // 2, self.height // 2 + 70)))
                    
                    else:
                        for cell in self.search_grid:
                            self.screen.blit(
                                cell["img"],
                                cell["rect"]
                            )

                elif self.current_state == 5:
                    title_img = self.font.render("TASK 1 COMPLETE", True, (0,255,255))
                    q_img = self.font.render("How many Q's did you count?", True, (255,255,255))
                    answer_img = self.font.render(self.user_count_answer, True, (255,255,0))
                    hint_img = self.font.render("Type number and press ENTER", True, (180,180,180))

                    self.screen.blit(title_img, title_img.get_rect(center=(self.width//2,150)))
                    self.screen.blit(q_img, q_img.get_rect(center=(self.width//2,280)))
                    self.screen.blit(answer_img, answer_img.get_rect(center=(self.width//2,380)))
                    self.screen.blit(hint_img, hint_img.get_rect(center=(self.width//2,480)))
                
                elif self.current_state == 6:
                    title_img = self.font.render("TASK 2-HARD", True, (0,255,255))
                    line1 = self.font.render("Count how many times 'O' appears.", True, (255,255,255))
                    line2 = self.font.render("Press SPACEBAR to begin.", True, (255,255,0))

                    self.screen.blit(title_img, title_img.get_rect(center=(self.width//2,150)))
                    self.screen.blit(line1, line1.get_rect(center=(self.width//2,250)))
                    self.screen.blit(line2, line2.get_rect(center=(self.width//2,320)))

                elif self.current_state == 7:
                    if self.code_presented:
                        title_img = self.font.render("MEMORIZE THIS CODE", True, (255,255,255))
                        code_img = self.font.render(self.memory_code, True, (255,255,0))
                        self.screen.blit(title_img, title_img.get_rect(center=(self.width//2, self.height//2 - 60)))
                        self.screen.blit(code_img, code_img.get_rect(center=(self.width//2, self.height//2 + 20)))
                    else:
                        for cell in self.search_grid:
                            self.screen.blit(cell["img"], cell["rect"])

                elif self.current_state == 8:
                    title_img = self.font.render("TASK 2 COMPLETE", True, (0,255,255))
                    q_img = self.font.render("How many O's did you count?", True, (255,255,255))
                    answer_img = self.font.render(self.task2_user_answer, True, (255,255,0))
                    hint_img = self.font.render("Type number and press ENTER", True, (180,180,180))

                    self.screen.blit(title_img, title_img.get_rect(center=(self.width//2,150)))
                    self.screen.blit(q_img, q_img.get_rect(center=(self.width//2,280)))
                    self.screen.blit(answer_img, answer_img.get_rect(center=(self.width//2,380)))
                    self.screen.blit(hint_img, hint_img.get_rect(center=(self.width//2,480)))

                elif self.current_state == 9:
                    title_img = self.font.render("MEMORY RECALL", True, (0,255,255))
                    q_img = self.font.render("What was the code?", True, (255,255,255))
                    answer_img = self.font.render(self.memory_code_answer, True, (255,255,0))
                    hint_img = self.font.render("Type code and press ENTER", True, (180,180,180))

                    self.screen.blit(title_img, title_img.get_rect(center=(self.width//2,150)))
                    self.screen.blit(q_img, q_img.get_rect(center=(self.width//2,280)))
                    self.screen.blit(answer_img, answer_img.get_rect(center=(self.width//2,380)))
                    self.screen.blit(hint_img, hint_img.get_rect(center=(self.width//2,480)))

                elif self.current_state == 10:
                    title_img = self.font.render("ASSESSMENT COMPLETE", True, (0,255,0))
                    thanks_img = self.font.render("Thank You For Participating", True, (255,255,255))
                    self.screen.blit(title_img, title_img.get_rect(center=(self.width//2, self.height//2 - 40)))
                    self.screen.blit(thanks_img, thanks_img.get_rect(center=(self.width//2, self.height//2 + 40)))

                # HARDWARE FLUSH & FRAME THROTTLE
                pygame.display.flip()
                self.clock.tick(self.fps)
            
            # SYSTEM SHUTDOWN 
            pygame.quit() 
            print("Application closed safely.")
            sys.exit(0) # Critical System Fix: Explicit OS shutdown signal

if __name__ == "__main__":
    app = CognitiveStimulusApp()
    app.run()