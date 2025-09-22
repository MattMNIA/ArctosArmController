import pygame
import sys

def main():
    pygame.init()
    pygame.joystick.init()

    # Set up display
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Xbox Controller Debug")
    font = pygame.font.Font(None, 24)
    clock = pygame.time.Clock()

    # Check for controller
    if pygame.joystick.get_count() == 0:
        print("No controller detected!")
        sys.exit(1)

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"Controller: {joystick.get_name()}")

    running = True
    while running:
        screen.fill((0, 0, 0))  # Black background

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # Get controller state
        y_pos = 10

        # Display axes (sticks and triggers) - range: -1.0 to 1.0
        axis_names = [
            "Left Stick X (-1.0 to 1.0)", "Left Stick Y (-1.0 to 1.0)", 
            "Right Stick X (-1.0 to 1.0)", "Right Stick Y (-1.0 to 1.0)",
            "Left Trigger (-1.0 to 1.0)", "Right Trigger (-1.0 to 1.0)"
        ]

        for i, name in enumerate(axis_names):
            value = joystick.get_axis(i)
            # Show if axis is active (outside deadzone)
            if i in [4, 5]:  # Triggers
                active = value > 0.5
            else:  # Sticks
                active = abs(value) > 0.15
            color = (0, 255, 0) if active else (255, 255, 255)
            status = "ACTIVE" if active else "inactive"
            text = font.render(f"{name}: {value:.3f} [{status}]", True, color)
            screen.blit(text, (10, y_pos))
            y_pos += 30

        y_pos += 20  # Space

        # Display buttons - boolean: pressed/released
        button_names = [
            "A (boolean)", "B (boolean)", "X (boolean)", "Y (boolean)", 
            "LB (boolean)", "RB (boolean)", "Back (boolean)", "Start (boolean)",
            "Left Stick Click (boolean)", "Right Stick Click (boolean)"
        ]

        for i, name in enumerate(button_names):
            if i < joystick.get_numbuttons():
                pressed = joystick.get_button(i)
                color = (0, 255, 0) if pressed else (255, 0, 0)
                status = "PRESSED" if pressed else "released"
                text = font.render(f"{name}: {status}", True, color)
                screen.blit(text, (10, y_pos))
                y_pos += 30

        # Display hat (D-pad)
        if joystick.get_numhats() > 0:
            hat = joystick.get_hat(0)
            text = font.render(f"D-Pad: {hat}", True, (255, 255, 255))
            screen.blit(text, (10, y_pos))
            y_pos += 30

        # Instructions
        instructions = [
            "Press ESC to quit",
            f"Controller: {joystick.get_name()}",
            f"Buttons: {joystick.get_numbuttons()} (boolean: pressed/released)",
            f"Axes: {joystick.get_numaxes()} (range: -1.0 to 1.0)",
            f"Hats: {joystick.get_numhats()}",
            "",
            "ACTIVE = outside deadzone (sticks: >0.15 from center, triggers: >0.5)",
            "Calibration happens automatically on controller init"
        ]

        y_pos = 500
        for instruction in instructions:
            text = font.render(instruction, True, (200, 200, 200))
            screen.blit(text, (10, y_pos))
            y_pos += 25

        pygame.display.flip()
        clock.tick(60)  # 60 FPS

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()