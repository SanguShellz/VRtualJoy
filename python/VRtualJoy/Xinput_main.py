# === Xinput_main.py (now inside /vrtualjoy) ===

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

# Base directory is now the parent of this script's folder
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VRTUALJOY_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, VRTUALJOY_DIR)

# Import from vrtualjoy
from Xinput_motion_tracking import (
    load_calibration, handle_calibration, apply_headtracking_to_right_stick,
    Smoother
)
from Xinput_controller_input import (
    poll_controller_inputs, process_left_joystick,
    process_triggers_and_buttons, extract_input_value, apply_deadzone_axis
)

# Argument parsing
parser = argparse.ArgumentParser(description="XInput VR bridge")
parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
parser.add_argument("--hz", type=float, default=70.0, help="Update frequency (Hz)")
args = parser.parse_args()
VERBOSE = args.verbose
HZ = args.hz

# Logging setup
log_path = os.path.join(VRTUALJOY_DIR, "Xinput.log")
logger = logging.getLogger("Xinput")
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

CONFIG_FILE = os.path.abspath(os.path.join(VRTUALJOY_DIR, '..', '..', 'main_config.json'))

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                full_config = json.load(f)
                log_and_print("Config loaded from main_config.json.")

                # Extract XINPUT mappings only
                mappings = full_config.get("MAPPINGS", {}).get("XINPUT", {})

                # Add "enabled" flag automatically based on "target"
                def process_mapping_set(mapping_set):
                    processed = {}
                    for controller, buttons in mapping_set.items():
                        processed[controller] = {}
                        for button_name, config in buttons.items():
                            config["enabled"] = bool(config.get("target"))
                            processed[controller][button_name] = config
                    return processed

                mappings["BUTTON_MAPPINGS"] = process_mapping_set(mappings.get("BUTTON_MAPPINGS", {}))
                mappings["SHIFT_BUTTON_MAPPINGS"] = process_mapping_set(mappings.get("SHIFT_BUTTON_MAPPINGS", {}))

                # Combine base config with processed mappings
                xinput_config = {
                    **{k: v for k, v in full_config.items() if k != "MAPPINGS"},
                    **mappings
                }

                return xinput_config
        except Exception as e:
            log_and_print(f"Failed to load config file: {e}", level="error")
    log_and_print("No config file found. Using defaults.", level="warning")
    return {}

def initialize_gamepad():
    try:
        gamepad = vg.VX360Gamepad()
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        gamepad.update()
        time.sleep(0.5)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
        gamepad.update()
        time.sleep(0.5)
        return gamepad
    except Exception as e:
        log_and_print(f"Error initializing gamepad: {e}", level="error")
        raise

def safe_gamepad_update(gamepad):
    try:
        gamepad.update()
        return gamepad
    except:
        return initialize_gamepad()

def get_controller_role_index(device_index):
    role = openvr.VRSystem().getControllerRoleForTrackedDeviceIndex(device_index)
    return "left" if role == openvr.TrackedControllerRole_LeftHand else "right" if role == openvr.TrackedControllerRole_RightHand else "unknown"

def initialize_vr_devices():
    openvr.init(openvr.VRApplication_Other)
    v = triad_openvr.triad_openvr()
    left_controller = right_controller = hmd = None

    for dev in v.devices.values():
        index = dev.index
        try:
            cls = dev.device_class.lower()
            if cls == "controller":
                role = get_controller_role_index(index)
                if role == "left" and not left_controller:
                    left_controller = dev
                    log_and_print(f"Controller at index {index} has role: left")
                elif role == "right" and not right_controller:
                    right_controller = dev
                    log_and_print(f"Controller at index {index} has role: right")
                elif not left_controller:
                    left_controller = dev
                    log_and_print(f"Controller at index {index} assigned as fallback left_controller")
                elif not right_controller:
                    right_controller = dev
                    log_and_print(f"Controller at index {index} assigned as fallback right_controller")
            elif cls == "hmd":
                hmd = dev
        except Exception as e:
            log_and_print(f"Device error: {e}", level="error")

    if not hmd:
        log_and_print("Error: No HMD detected.", level="error")
        raise RuntimeError("No HMD detected")

    return v, left_controller, right_controller, hmd

def validate_interval():
    return 1 / HZ

async def main_loop(left_controller, right_controller, hmd, gamepad, interval, config):
    yaw_smoother = Smoother(alpha=config.get("HEADTRACKING_SMOOTHING_YAW", 0.2))
    pitch_smoother = Smoother(alpha=config.get("HEADTRACKING_SMOOTHING_PITCH", 0.2))
    left_controller_state_old = {}
    right_controller_state_old = {}
    last_shift_active = None

    while True:
        start = time.perf_counter()
        left_controller_state, right_controller_state = await poll_controller_inputs(left_controller, right_controller)
        left_grip = left_controller_state.get("grip_button", False)
        await handle_calibration(left_controller, right_controller, hmd, left_grip)
        await process_left_joystick(left_controller_state, right_controller_state, left_grip, gamepad, config)

        shift_active = left_grip
        if shift_active != last_shift_active:
            log_and_print(f"Shift mode: {'ON' if shift_active else 'OFF'}", level="debug")
            last_shift_active = shift_active

        await process_triggers_and_buttons(
            left_controller_state, right_controller_state,
            left_controller_state_old, right_controller_state_old,
            gamepad, shift_active, config
        )

        raw_r_x = apply_deadzone_axis(
            extract_input_value(left_controller_state, right_controller_state, config["RIGHT_X_REMAP"]),
            config["RIGHT_X_DEADZONE"]
        ) if config["RIGHT_X_ENABLED"] else 0.0

        raw_r_y = apply_deadzone_axis(
            extract_input_value(left_controller_state, right_controller_state, config["RIGHT_Y_REMAP"]),
            config["RIGHT_Y_DEADZONE"]
        ) if config["RIGHT_Y_ENABLED"] else 0.0

        apply_headtracking_to_right_stick(hmd, gamepad, raw_r_x, raw_r_y, yaw_smoother, pitch_smoother, config)

        gamepad = safe_gamepad_update(gamepad)
        left_controller_state_old = left_controller_state
        right_controller_state_old = right_controller_state

        await asyncio.sleep(max(0, interval - (time.perf_counter() - start)))

async def main():
    try:
        log_and_print("Starting VRtualJoy Xinput Mode...", level="info")
        v, left_controller, right_controller, hmd = initialize_vr_devices()
        gamepad = initialize_gamepad()
        interval = validate_interval()
        config = load_config()
        load_calibration()
        log_and_print("Calibration loaded from file.")
        await main_loop(left_controller, right_controller, hmd, gamepad, interval, config)
    except Exception as e:
        log_and_print(f"Fatal error: {e}", level="error")
        raise

if __name__ == "__main__":
    asyncio.run(main())
