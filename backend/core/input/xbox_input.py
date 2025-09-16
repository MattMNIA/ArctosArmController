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

        # Axis mapping:
        # 0 = left stick X, 1 = left stick Y
        # 2 = right stick X, 3 = right stick Y
        # 4 = left trigger, 5 = right trigger
        # Button mapping depends on controller; here we assume Xbox standard
        self.axis_map = {
            0: (0, 0.5),   # left stick X → joint 0
            1: (1, -0.5),  # left stick Y → joint 1
            2: (2, 0.5),   # right stick X → joint 2
            3: (3, -0.5),  # right stick Y → joint 3
        }

        self.trigger_map = {
            4: (4, -0.5),  # left trigger → joint 4 CCW
            5: (4, 0.5),   # right trigger → joint 4 CW
        }

        self.button_map = {
            4: ([5, 6], -0.5),  # left bumper → joints 5+6 CCW
            5: ([5, 6], 0.5),   # right bumper → joints 5+6 CW
            0: ("gripper", -1.0),  # A → close gripper
            1: ("gripper", 1.0),   # B → open gripper
        }

    def get_commands(self):
        """Return a dict of {joint: delta} or {'gripper': delta}"""
        pygame.event.pump()
        commands = {}

        # Process axes (sticks)
        for axis, (joint, scale) in self.axis_map.items():
            val = self.joystick.get_axis(axis)
            if abs(val) > 0.1:  # deadzone
                if isinstance(joint, int):
                    commands[joint] = commands.get(joint, 0.0) + val * scale
                elif isinstance(joint, list):
                    joint_list = cast(List[int], joint)
                    for j in joint_list:
                        commands[j] = commands.get(j, 0.0) + val * scale

        # Process triggers
        for axis, (joint, scale) in self.trigger_map.items():
            val = self.joystick.get_axis(axis)
            if val > 0.1:  # triggers range [0,1] on some controllers
                commands[joint] = commands.get(joint, 0.0) + val * scale

        # Process buttons
        for btn, (joint, scale) in self.button_map.items():
            if self.joystick.get_button(btn):
                if isinstance(joint, list):
                    joint_list = cast(List[int], joint)
                    for j in joint_list:
                        commands[j] = commands.get(j, 0.0) + scale
                elif isinstance(joint, int):
                    commands[joint] = commands.get(joint, 0.0) + scale
                elif joint == "gripper":
                    commands["gripper"] = commands.get("gripper", 0.0) + scale

        return commands

    def get_events(self):
        """Return a list of events: ('press' or 'release', joint, scale)"""
        pygame.event.pump()
        events = []
        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                btn = event.button
                if btn in self.button_map:
                    joint, scale = self.button_map[btn]
                    if isinstance(joint, list):
                        joint_list = cast(List[int], joint)
                        for j in joint_list:
                            events.append(('press', j, scale))
                    else:
                        events.append(('press', joint, scale))
            elif event.type == pygame.JOYBUTTONUP:
                btn = event.button
                if btn in self.button_map:
                    joint, scale = self.button_map[btn]
                    if isinstance(joint, list):
                        joint_list = cast(List[int], joint)
                        for j in joint_list:
                            events.append(('release', j, scale))
                    else:
                        events.append(('release', joint, scale))
        return events
