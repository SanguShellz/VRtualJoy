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
sys.path.insert(0, current_dir)      # for local vrtualjoy modules
sys.path.insert(0, project_root)     # to import from ../python if needed

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

# === Global Mappings (populated by load_config) ===
BUTTON_MAPPINGS = {}
SHIFT_BUTTON_MAPPINGS = {}

# === Config Loading ===
def load_config():
    global BUTTON_MAPPINGS, SHIFT_BUTTON_MAPPINGS

    config_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'main_config.json'))

    with open(config_path, 'r') as f:
        raw = json.load(f)

    mappings_ds4 = raw.get("MAPPINGS", {}).get("DS4", {})

    def process_mapping(mapping_data):
        processed = {}
        for controller, buttons in mapping_data.items():
            processed[controller] = {}
            for button, config_item in buttons.items():
                target = config_item.get("target")
                config_item["enabled"] = bool(target)
                processed[controller][button] = config_item
        return processed

    BUTTON_MAPPINGS.update(process_mapping(mappings_ds4.get("BUTTON_MAPPINGS", {})))
    SHIFT_BUTTON_MAPPINGS.update(process_mapping(mappings_ds4.get("SHIFT_BUTTON_MAPPINGS", {})))

    # Remove old aliases
    # No need to set raw["LX_DEADZONE"] = raw.get("L_DEADZONE_X", 0.1) anymore

    log_and_print("DS4 config loaded from main_config.json.")
    return raw

# === Main loop and entry point ===
async def main_loop(controller1, controller2, hmd, gamepad, config_data):
    yaw_smoother = Smoother(alpha=config_data.get("HEADTRACKING_SMOOTHING_YAW", 0.2))
    pitch_smoother = Smoother(alpha=config_data.get("HEADTRACKING_SMOOTHING_PITCH", 0.2))
    controller1_state_old = {}
    controller2_state_old = {}

    while True:
        controller1_state, controller2_state = await poll_controller_inputs(controller1, controller2)
        shift_active = controller1_state.get("grip_button", False)

        await handle_calibration(controller1, controller2, hmd, shift_active)

        if shift_active != getattr(main_loop, '_last_shift', None):
            log_and_print(f"Shift mode: {'ON' if shift_active else 'OFF'}", level="debug")
            main_loop._last_shift = shift_active

        await process_left_joystick(controller1_state, controller2_state, shift_active, gamepad, config_data)

        await process_triggers_and_buttons(
            controller1_state, controller2_state,
            controller1_state_old, controller2_state_old,
            gamepad, shift_active,
            BUTTON_MAPPINGS, SHIFT_BUTTON_MAPPINGS
        )

        await apply_headtracking_to_right_stick(
            hmd, controller1_state, controller2_state,
            gamepad, yaw_smoother, pitch_smoother, config_data
        )

        gamepad = safe_gamepad_update(gamepad)
        controller1_state_old = controller1_state
        controller2_state_old = controller2_state
        await asyncio.sleep(1 / HZ)

async def main():
    try:
        log_and_print("Starting VRtualJoy DS4 Mode...", level="info")
        config_data = load_config()
        load_calibration()
        _, controller1, controller2, hmd = initialize_vr_devices()
        gamepad = initialize_gamepad()
        await main_loop(controller1, controller2, hmd, gamepad, config_data)
    except Exception as e:
        log_and_print(f"Fatal error: {e}", level="error")
        raise

if __name__ == "__main__":
    asyncio.run(main())
