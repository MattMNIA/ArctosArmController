import pygame
from core.input.base_input import InputController
import logging
from typing import cast, List
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KeyboardController(InputController):
    def __init__(self):
        pygame.init()
        pygame.display.set_mode((400, 300))  # Create a window for keyboard input capture
        self.all_scale = 10
        self.keymap = {

            # Joint 0
            pygame.K_a: (0, -0.5),
            pygame.K_d: (0, 0.5),
            # Joint 1
            pygame.K_w: (1, 0.5),
            pygame.K_s: (1, -0.5),
            # Joint 2
            pygame.K_j: (2, -0.5),
            pygame.K_l: (2, 0.5),
            # Joint 3
            pygame.K_i: (3, 0.5),
            pygame.K_k: (3, -0.5),
            # Joint 4
            pygame.K_u: (4, -0.5),
            pygame.K_o: (4, 0.5),
            # Joints 5 & 6 (move together)
            pygame.K_q: ([5, 6], -1),
            pygame.K_e: ([5, 6], 1),
            # Gripper open/close
            pygame.K_z: ("gripper", -.05),
            pygame.K_x: ("gripper", .05),
        }
        self.last_pressed = set()

    def get_commands(self):
        """Return a dict of {joint: delta} or {'gripper': delta} for all currently pressed keys"""
        pygame.event.pump()
        current_pressed = set(k for k in self.keymap if pygame.key.get_pressed()[k])
        if current_pressed:
            logger.info(f"Current pressed keys: {current_pressed}")
        commands = {}

        for key in current_pressed:
            joint, scale = self.keymap[key]
            if isinstance(joint, list):  # multiple joints (5+6)
                joint_list = cast(List[int], joint)
                for j in joint_list:
                    commands[j] = commands.get(j, 0.0) + scale * self.all_scale
            elif isinstance(joint, int):  # single joint
                commands[joint] = commands.get(joint, 0.0) + scale * self.all_scale
            elif joint == "gripper":  # gripper open/close
                commands["gripper"] = commands.get("gripper", 0.0) + scale * self.all_scale

        self.last_pressed = current_pressed
        return commands

    def get_events(self):
        """Return a list of events: ('press' or 'release', joint, scale)"""
        pygame.event.pump()
        events = []
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN and event.key in self.keymap:
                joint, scale = self.keymap[event.key]
                scaled_scale = scale * self.all_scale
                if isinstance(joint, list):
                    joint_list = cast(List[int], joint)
                    for j in joint_list:
                        events.append(('press', j, scaled_scale))
                else:
                    events.append(('press', joint, scaled_scale))
            elif event.type == pygame.KEYUP and event.key in self.keymap:
                joint, scale = self.keymap[event.key]
                scaled_scale = scale * self.all_scale
                if isinstance(joint, list):
                    joint_list = cast(List[int], joint)
                    for j in joint_list:
                        events.append(('release', j, scaled_scale))
                else:
                    events.append(('release', joint, scaled_scale))
        return events
