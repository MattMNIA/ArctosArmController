import cv2
import numpy as np
import os
from PIL import Image

# === Configuration ===
CALIBRATION_ROOT = os.path.dirname(__file__)
save_dir = os.path.join(CALIBRATION_ROOT, "images")
os.makedirs(save_dir, exist_ok=True)

dpi = 300  # for high-quality print
square_size_m = 0.025  # 25mm
px_per_m = dpi / 0.0254
square_size_px = int(square_size_m * px_per_m)

# Helper: Save as PNG and optionally PDF
def save_image(name, img):
    path = os.path.join(save_dir, name + ".png")
    cv2.imwrite(path, img)
    # Also make printable PDF
    Image.fromarray(img).save(os.path.join(save_dir, name + ".pdf"))
    print(f"✅ Saved {name} ({img.shape[1]}x{img.shape[0]})")


# === 1. Checkerboard ===
def generate_checkerboard(cols=9, rows=6, square_px=100):
    width = cols * square_px
    height = rows * square_px
    board = np.zeros((height, width), np.uint8)
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                cv2.rectangle(board, (c * square_px, r * square_px),
                              ((c + 1) * square_px, (r + 1) * square_px),
                              255, -1)
    return board

checkerboard = generate_checkerboard(9, 6, 120)
save_image("checkerboard_9x6_25mm", checkerboard)


# === 2. Asymmetric circles grid ===
def generate_asymmetric_circles(cols=4, rows=11, spacing_px=80, radius_px=20):
    width = int((cols + 0.5) * spacing_px)
    height = rows * spacing_px
    board = np.ones((height + spacing_px, width + spacing_px), np.uint8) * 255
    for i in range(rows):
        for j in range(cols):
            x = int((2 * j + i % 2) * spacing_px / 2 + spacing_px)
            y = int(i * spacing_px + spacing_px / 2)
            cv2.circle(board, (x, y), radius_px, 0, -1)
    return board

circles = generate_asymmetric_circles()
save_image("asymmetric_circles_4x11_25mm", circles)


# === 3. Charuco board ===

def generate_CharucoBoard():
    ARUCO_DICT = cv2.aruco.DICT_6X6_250
    SQUARES_VERTICALLY = 7
    SQUARES_HORIZONTALLY = 5
    SQUARE_LENGTH = 0.03
    MARKER_LENGTH = 0.015
    LENGTH_PX = 640   # total length of the page in pixels
    MARGIN_PX = 20    # size of the margin in pixels

    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    board = cv2.aruco.CharucoBoard((SQUARES_VERTICALLY, SQUARES_HORIZONTALLY), SQUARE_LENGTH, MARKER_LENGTH, dictionary)
    size_ratio = SQUARES_HORIZONTALLY / SQUARES_VERTICALLY
    img = cv2.aruco.CharucoBoard.generateImage(board, (LENGTH_PX, int(LENGTH_PX*size_ratio)), marginSize=MARGIN_PX)
    return img

charuco_board = generate_CharucoBoard()
save_image("charuco_board_7x5_25mm", charuco_board)



print("\n🎯 All calibration patterns generated in:", os.path.abspath(save_dir))
