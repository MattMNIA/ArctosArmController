import pygame
from core.input.base_input import InputController
from typing import cast, List


class XboxController(InputController):
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            raise RuntimeError("No Xbox controller detected!")

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        self.global_scale = 1  # Scale factor for joint movements
        # Axis mapping:
        # 0 = left stick X, 1 = left stick Y
        # 2 = right stick X, 3 = right stick Y
        # 4 = left trigger, 5 = right trigger
        # Button mapping depends on controller; here we assume Xbox standard
        self.axis_map = {
            0: (0, 1),   # left stick X → joint 0
            1: (1, 1),  # left stick Y → joint 1
            3: (2, 1),   # right stick X → joint 3
            2: (3, 1),  # right stick Y → joint 2
        }

        self.trigger_map = {
            4: (4, -1),  # left trigger → joint 4 CCW
            5: (4, 1),   # right trigger → joint 4 CW
        }

        self.button_map = {
            4: ([5], -1),  # left bumper → joints 5+6 CCW
            5: ([5], 1),   # right bumper → joints 5+6 CW
            0: ("gripper", -1.0),  # A → close gripper
            1: ("gripper", 1.0),   # B → open gripper
        }
        self.last_pressed = set()  # Track previously pressed buttons for transition detection
        self.last_axis_pressed = set()  # Track previously "pressed" axes for transition detection
        self.axis_threshold = 0.15  # Deadzone radius around center position
        
        # Calibrate center positions for each axis to handle stick drift
        self.axis_centers = {}
        self.calibrate_centers()

    def calibrate_centers(self):
        """Calibrate the center position for each axis to account for stick drift."""
        print("Calibrating controller centers... Please don't touch the sticks for 2 seconds.")
        import time
        
        # Take multiple samples to get average center position
        samples = []
        for _ in range(20):  # Sample for ~2 seconds at 10Hz
            pygame.event.pump()
            sample = {}
            for axis in range(self.joystick.get_numaxes()):
                sample[axis] = self.joystick.get_axis(axis)
            samples.append(sample)
            time.sleep(0.1)
        
        # Calculate average center position for each axis
        for axis in range(self.joystick.get_numaxes()):
            values = [sample[axis] for sample in samples]
            self.axis_centers[axis] = sum(values) / len(values)
            print(f"Axis {axis} center calibrated to: {self.axis_centers[axis]:.4f}")
        
        print("Calibration complete!")

    def is_axis_active(self, axis, value):
        """Check if axis value is outside the deadzone around its calibrated center."""
        if axis in [4, 5]:  # Triggers (typically 0-1 range)
            return value > 0.5  # Higher threshold for triggers to prevent sticking
        else:  # Sticks (-1 to 1 range)
            center = self.axis_centers.get(axis, 0.0)
            return abs(value - center) > self.axis_threshold

    def get_commands(self):
        """Return a dict of {joint: delta} or {'gripper': delta}"""
        pygame.event.pump()
        commands = {}

        # Process axes (sticks)
        for axis, (joint, scale) in self.axis_map.items():
            val = self.joystick.get_axis(axis)
            if self.is_axis_active(axis, val):  # Use calibrated deadzone
                center = self.axis_centers.get(axis, 0.0)
                # Normalize value relative to center
                normalized_val = (val - center) / (1.0 - abs(center)) if abs(center) < 0.8 else (val - center)
                if isinstance(joint, int):
                    commands[joint] = commands.get(joint, 0.0) + normalized_val * scale
                elif isinstance(joint, list):
                    joint_list = cast(List[int], joint)
                    for j in joint_list:
                        commands[j] = commands.get(joint, 0.0) + normalized_val * scale

        # Process triggers
        for axis, (joint, scale) in self.trigger_map.items():
            val = self.joystick.get_axis(axis)
            if self.is_axis_active(axis, val):  # Use trigger-specific threshold
                # For triggers, normalize from 0-1 range
                normalized_val = val  # Already 0-1, no need to adjust for center
                commands[joint] = commands.get(joint, 0.0) + normalized_val * scale

        # Process buttons
        for btn, (joint, scale) in self.button_map.items():
            if self.joystick.get_button(btn):
                scaled_value = scale * self.global_scale
                if isinstance(joint, list):
                    joint_list = cast(List[int], joint)
                    for j in joint_list:
                        commands[j] = commands.get(joint, 0.0) + scaled_value
                elif isinstance(joint, int):
                    commands[joint] = commands.get(joint, 0.0) + scaled_value
                elif joint == "gripper":
                    commands["gripper"] = commands.get("gripper", 0.0) + scaled_value

        return commands

    def get_events(self):
        """Return a list of events: ('press' or 'release', joint, scale) based on button and axis state transitions"""
        pygame.event.pump()  # Process events to keep pygame responsive
        pygame.event.clear()  # Clear any accumulated events to prevent buffering
        
        # Get current button states
        current_pressed = set(btn for btn in self.button_map if self.joystick.get_button(btn))
        
        # Get current axis states (consider "pressed" if above threshold)
        current_axis_pressed = set()
        for axis, (joint, scale) in {**self.axis_map, **self.trigger_map}.items():
            val = self.joystick.get_axis(axis)
            if self.is_axis_active(axis, val):
                if axis in [4, 5]:  # Triggers
                    scaled_value = scale * val * self.global_scale
                else:  # Sticks
                    center = self.axis_centers.get(axis, 0.0)
                    normalized_val = (val - center) / (1.0 - abs(center)) if abs(center) < 0.8 else (val - center)
                    scaled_value = scale * normalized_val * self.global_scale
                current_axis_pressed.add((axis, joint, scaled_value))
        
        events = []
        
        # Prioritize release events for faster response
        releases = []
        presses = []
        
        # Buttons that were pressed last time but not now = release
        for btn in self.last_pressed - current_pressed:
            joint, scale = self.button_map[btn]
            scaled_value = scale * self.global_scale
            if isinstance(joint, list):
                joint_list = cast(List[int], joint)
                for j in joint_list:
                    releases.append(('release', j, scaled_value))
            else:
                releases.append(('release', joint, scaled_value))
        
        # Buttons that are pressed now but weren't last time = press
        for btn in current_pressed - self.last_pressed:
            joint, scale = self.button_map[btn]
            scaled_value = scale * self.global_scale
            if isinstance(joint, list):
                joint_list = cast(List[int], joint)
                for j in joint_list:
                    presses.append(('press', j, scaled_value))
            else:
                presses.append(('press', joint, scaled_value))
        
        # Axes that were "pressed" last time but not now = release
        for axis_item in self.last_axis_pressed - current_axis_pressed:
            axis, joint, scale = axis_item
            if isinstance(joint, list):
                joint_list = cast(List[int], joint)
                for j in joint_list:
                    releases.append(('release', j, scale))
            else:
                releases.append(('release', joint, scale))
        
        # Axes that are "pressed" now but weren't last time = press
        for axis_item in current_axis_pressed - self.last_axis_pressed:
            axis, joint, scale = axis_item
            if isinstance(joint, list):
                joint_list = cast(List[int], joint)
                for j in joint_list:
                    presses.append(('press', j, scale))
            else:
                presses.append(('press', joint, scale))
        
        # Process releases first for higher priority
        events.extend(releases)
        events.extend(presses)
        
        self.last_pressed = current_pressed
        self.last_axis_pressed = current_axis_pressed
        return events