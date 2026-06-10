import pygame
import time
import os

class CognitiveStimulusApp:
    """
    The main UI and state-management hub.
    
    This class handles the 60Hz visual rendering pipeline and tracks the user's 
    progression through the exact sequence of assessment states. It operates 
    completely independently from the OpenCV camera engine.
    """
    
    def __init__(self):
        # INITIALIZATION: Engine Boot
        # pygame.init() compiles all the necessary C-level bindings (audio, video, hardware) 
        # that Pygame needs to interface with the operating system.
        pygame.init()
        
        # Grab the native resolution of whatever monitor the user is currently using
        screen_info = pygame.display.Info()
        self.width = screen_info.current_w
        self.height = screen_info.current_h
        # Note: In Pygame, the origin coordinate (0, 0) is the TOP-LEFT corner of the screen.
        
        # set_mode() actually asks the OS to open the application window.
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Golden Hybrid: Cognitive Load Assessment")
        
        # TIMING & THROTTLING 
        # The Clock object is crucial. Without it, the while-loop below would run 
        # as fast as the CPU allows (thousands of times per second), crashing the system.
        self.clock = pygame.time.Clock()
        self.fps = 60 # Strict 60Hz limit to ensure smooth visual pursuit for the user
        
        # FINITE STATE MACHINE VARIABLES 
        # We use an integer system to lock the application into specific phases.
        # 0 = STATE_MENU | 1 = STATE_CALIBRATE_WINDOW_EXTREMES | 2 = STATE_RESTING_BASELINE
        self.current_state = 0  
        
        # time.time() grabs the absolute operating system epoch time.
        # This acts as our "stopwatch" to calculate how long we have been in a specific state.
        self.state_start_time = time.time() 
        
        print(f"System initialized. Awaiting start command.")

    def run(self):
        """
        The core application loop. Every single iteration of this loop represents 
        one single "frame" (1/60th of a second) in our application.
        """
        running = True
        
        while running:
            
            #  EVENT PROCESSING
            
            # event.get() pulls a list of everything the user did with their mouse/keyboard 
            # since the exact last frame. We must empty this queue every frame, or the app freezes.
            for event in pygame.event.get():
                
                # Intercept the OS 'close window' 'X' button to shut down safely
                if event.type == pygame.QUIT:
                    running = False 
                    
                # Listen for specific keydown triggers
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    # Only allow transition to State 1 if we are currently sitting in State 0
                    if self.current_state == 0:
                        self.current_state = 1
                        self.state_start_time = time.time() # Reset the stopwatch for the new state
                        print("Transitioned to STATE 1: Calibrating Extremes")

            
            #  LOGIC & STATE UPDATES
            
            # Calculate 'Delta Time': The exact physical time that has passed 
            # since we entered the current state.
            current_time = time.time()
            time_in_state = current_time - self.state_start_time 
            
            # FSM Rule for State 1: 
            # If we are in State 1 AND exactly 8.0 seconds have elapsed, automatically move forward.
            if self.current_state == 1 and time_in_state >= 8.0:
                self.current_state = 2
                self.state_start_time = time.time() # Reset the stopwatch for State 2
                print("Transitioned to STATE 2: Resting Baseline")

            
            #  RENDERING
            
            # Erase the entire screen from the previous frame by painting it dark gray.
            # RGB Format: (Red, Green, Blue). (30, 30, 30) is a soft, non-glaring dark background.
            self.screen.fill((30, 30, 30)) 
            
            # Future rendering logic will go here (drawing circles, text, menus)

            
            #  HARDWARE FLUSH & FRAME THROTTLE
            
            # Pygame uses "Double Buffering". We do all our drawing on a hidden screen in memory.
            # display.flip() instantly swaps the hidden screen with the visible monitor screen.
            pygame.display.flip()
            
            # This line pauses the entire Python script for just a few milliseconds.
            # It mathematically ensures the loop never cycles faster than 60 times per second.
            self.clock.tick(self.fps) 

        # SYSTEM SHUTDOWN 
        # This code only executes once the `running = True` loop is broken.
        pygame.quit()
        print("Application closed safely.")


# Standard execution block: Only run the app if this specific file is executed directly.
if __name__ == "__main__":
    app = CognitiveStimulusApp()
    app.run()