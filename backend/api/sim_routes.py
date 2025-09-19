from flask import Blueprint, Response, current_app
import cv2
import time
import numpy as np
import logging

sim_bp = Blueprint('sim', __name__)
logger = logging.getLogger(__name__)

def gen(motion_service):
    driver = motion_service.driver

    logger.debug("Accessed gen() for video feed.")
    # Assuming CompositeDriver, get PyBulletDriver (second in list)
    if hasattr(driver, 'drivers') and len(driver.drivers) >= 1:
        logger.debug("Driver has 'drivers' attribute with length %d.", len(driver.drivers))
        # Find the PyBulletDriver in the list of drivers
        pybullet_driver = None
        for d in driver.drivers:
            logger.debug("Checking driver: %s", d.__class__.__name__)
            if d.__class__.__name__ == "PyBulletDriver":
                pybullet_driver = d
                logger.info("Found PyBulletDriver.")
                break
        if pybullet_driver is None:
            logger.warning("PyBulletDriver not found in drivers list.")
    else:
        pybullet_driver = driver  # If single driver
        logger.debug("Single driver detected: %s", driver.__class__.__name__)

    if pybullet_driver is None or not hasattr(pybullet_driver, 'get_camera_frame'):
        logger.error("Simulation not running or PyBulletDriver missing 'get_camera_frame'.")
        # Create error frame
        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(error_frame, "Simulation not running", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        _, jpeg = cv2.imencode('.jpg', error_frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               jpeg.tobytes() +
               b'\r\n')
        return

    logger.info("Starting video frame generation loop.")
    while True:
        frame = pybullet_driver.get_camera_frame()
        if frame is None:
            logger.warning("Received None frame from get_camera_frame().")
            continue
        _, jpeg = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               jpeg.tobytes() +
               b'\r\n')
        time.sleep(0.1)  # Control frame rate

@sim_bp.route('/video_feed')
def video_feed():
    motion_service = current_app.config['motion_service']
    return Response(gen(motion_service),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@sim_bp.route('/status')
def sim_status():
    logger.debug("Accessed sim_status() endpoint.")
    motion_service = current_app.config['motion_service']
    driver = motion_service.driver
    logger.debug("Retrieved driver: %s", driver.__class__.__name__)

    # Check if PyBulletDriver is available
    if hasattr(driver, 'drivers') and len(driver.drivers) >= 1:
        logger.debug("Driver has 'drivers' attribute with length %d.", len(driver.drivers))
        pybullet_driver = None
        for d in driver.drivers:
            logger.debug("Checking driver: %s", d.__class__.__name__)
            if d.__class__.__name__ == "PyBulletDriver":
                pybullet_driver = d
                logger.info("Found PyBulletDriver.")
                break
        if pybullet_driver is None:
            logger.warning("PyBulletDriver not found in drivers list.")
    else:
        pybullet_driver = driver  # If single driver
        logger.debug("Single driver detected: %s", driver.__class__.__name__)

    simulation_active = pybullet_driver is not None and hasattr(pybullet_driver, 'get_camera_frame')
    logger.info("Simulation active: %s", simulation_active)
    return {'simulation_active': simulation_active}
