#!/usr/bin/env python3

import cv2

try:
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        print("Cascade not loaded")
    else:
        print("Cascade loaded successfully")
except Exception as e:
    print(f"Error: {e}")