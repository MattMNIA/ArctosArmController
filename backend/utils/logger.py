# utils/logger.py
import logging
import sys

def setup_logging(level=logging.DEBUG, component_levels=None):
    """
    Set up logging configuration for the entire application.
    This configures the root logger with a formatter that includes the logger name.
    
    :param level: Default logging level for the root logger.
    :param component_levels: Dict of component names to their logging levels, e.g., {'api': logging.DEBUG}
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout
    )
    
    # Set specific levels for components
    if component_levels:
        for component, comp_level in component_levels.items():
            logging.getLogger(component).setLevel(comp_level)


component_levels = {
    'api': logging.DEBUG,
    'core.drivers.can_driver': logging.DEBUG,
    'core.motion_service': logging.DEBUG, 
    'core.drivers.mks_servo_can.mks_servo': logging.INFO,
    'backend.core.drivers.mks_servo_can.mks_servo': logging.INFO,
}
setup_logging(component_levels=component_levels)

# Create a logger instance for import
logger = logging.getLogger()
