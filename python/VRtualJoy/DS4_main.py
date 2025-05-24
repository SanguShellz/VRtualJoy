# === DS4_main.py ===

# === Standard library imports ===
import asyncio
import argparse
import logging
import os
import sys
import time
import json

# === Third-party imports ===
import openvr
import vgamepad as vg
import triad_openvr

# === Path setup for local module imports ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.insert(0, current_dir)
sys.path.insert(0, project_root)

# === Local project imports ===
from DS4_controller_input import (
    initialize_gamepad, safe_gamepad_update,  
    poll_controller_inputs, process_triggers_and_buttons,
    process_left_joystick, extract_input_value,
    apply_deadzone_axis, remap_float_axis
)
from DS4_motion_tracking import (
    load_calibration, handle_calibration,
    apply_headtracking_to_right_stick, initialize_vr_devices,
    Smoother
)

# === Argument parsing ===
parser = argparse.ArgumentParser(description="DS4 VR bridge")
parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
parser.add_argument("--hz", type=float, default=72.0, help="Update frequency (Hz)")
args = parser.parse_args()
VERBOSE = args.verbose
HZ = args.hz

# === Logger setup ===
log_path = os.path.join(current_dir, "DS4.log")
logger = logging.getLogger("DS4")
logger.setLevel(logging.DEBUG if VERBOSE else logging.INFO)
handler = logging.FileHandler(log_path, encoding="utf-8")
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.handlers.clear()
logger.addHandler(handler)

def log_and_print(message, level='info'):
    print(message)
    if level == 'info':
        logger.info(message)
    elif level == 'warning':
        logger.warning(message)
    elif level == 'error':
        logger.error(message)
    elif level == 'debug':
        logger.debug(message)

# === Global Mappings ===
BUTTON_MAPPINGS = {}
SHIFT_BUTTON_MAPPINGS = {}

# === Config Loading ===
def load_config():
    global BUTTON_MAPPINGS, SHIFT_BUTTON_MAPPINGS

    config_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'main_config.json'))

    with open(config_path, 'r') as f:
        raw = json.load(f)

    controller_type = raw.get("CONTROLLER_TYPE", "DS4").upper()
    mappings = raw.get("MAPPINGS", {}).get(controller_type, {})

    def process_mapping(mapping_data):
        processed = {}
        for controller, buttons in mapping_data.items():
            processed[controller] = {}
            for button, config_item in buttons.items():
                target = config_item.get("target")
                config_item["enabled"] = bool(target)
                processed[controller][button] = config_item
        return processed

    BUTTON_MAPPINGS.update(process_mapping(mappings.get("BUTTON_MAPPINGS", {})))
    SHIFT_BUTTON_MAPPINGS.update(process_mapping(mappings.get("SHIFT_BUTTON_MAPPINGS", {})))

    log_and_print(f"{controller_type} config loaded from main_config.json.")
    return raw

# === Main loop ===
async def main_loop(left_controller, right_controller, hmd, gamepad, config_data):
    yaw_smoother = Smoother(alpha=config_data.get("HEADTRACKING_SMOOTHING_YAW", 0.2))
    pitch_smoother = Smoother(alpha=config_data.get("HEADTRACKING_SMOOTHING_PITCH", 0.2))
    left_controller_state_old = {}
    right_controller_state_old = {}

    while True:
        left_controller_state, right_controller_state = await poll_controller_inputs(left_controller, right_controller)
        shift_active = left_controller_state.get("grip_button", False)

        await handle_calibration(left_controller, right_controller, hmd, shift_active)

        if shift_active != getattr(main_loop, '_last_shift', None):
            log_and_print(f"Shift mode: {'ON' if shift_active else 'OFF'}", level="debug")
            main_loop._last_shift = shift_active

        await process_left_joystick(left_controller_state, right_controller_state, shift_active, gamepad, config_data)

        await process_triggers_and_buttons(
            left_controller_state, right_controller_state,
            left_controller_state_old, right_controller_state_old,
            gamepad, shift_active,
            BUTTON_MAPPINGS, SHIFT_BUTTON_MAPPINGS
        )

        await apply_headtracking_to_right_stick(
            hmd, left_controller_state, right_controller_state,
            gamepad, yaw_smoother, pitch_smoother, config_data
        )

        gamepad = safe_gamepad_update(gamepad)
        left_controller_state_old = left_controller_state
        right_controller_state_old = right_controller_state
        await asyncio.sleep(1 / HZ)

# === Entry point ===
async def main():
    try:
        log_and_print("Starting VRtualJoy DS4 Mode...", level="info")
        config_data = load_config()
        load_calibration()
        _, left_controller, right_controller, hmd = initialize_vr_devices()
        gamepad = initialize_gamepad()
        await main_loop(left_controller, right_controller, hmd, gamepad, config_data)
    except Exception as e:
        log_and_print(f"Fatal error: {e}", level="error")
        raise

if __name__ == "__main__":
    asyncio.run(main())
