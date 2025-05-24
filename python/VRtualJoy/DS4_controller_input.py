# === DS4_controller_input.py ===

import asyncio
import logging
import sys
import time
import vgamepad as vg

logger = logging.getLogger("DS4")

def log_and_print(message, level='info'):
    print(message)
    getattr(logger, level, logger.info)(message)

def remap_float_axis(val):
    return max(min(val, 1.0), -1.0)

def apply_deadzone_axis(value, threshold):
    return 0.0 if abs(value) < threshold else value

def extract_input_value(left_controller_state, right_controller_state, remap_key):
    if ':' in remap_key:
        controller, input_key = remap_key.split(':', 1)
        return (left_controller_state if controller == "left_controller" else right_controller_state).get(input_key, 0.0)
    return left_controller_state.get(remap_key, right_controller_state.get(remap_key, 0.0))

def initialize_gamepad():
    try:
        gamepad = vg.VDS4Gamepad()
        gamepad.press_special_button(vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_TOUCHPAD)
        gamepad.release_special_button(vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_TOUCHPAD)
        gamepad.directional_pad(vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)
        gamepad.left_joystick_float(0.0, 0.0)
        gamepad.right_joystick_float(0.0, 0.0)
        gamepad.update()
        time.sleep(0.1)
        return gamepad
    except Exception as e:
        log_and_print(f"Error initializing DS4 gamepad: {e}", level="error")
        sys.exit(1)

def safe_gamepad_update(gamepad):
    try:
        gamepad.update()
        return gamepad
    except Exception as e:
        log_and_print(f"Gamepad update failed: {e}. Reinitializing...", level="warning")
        return initialize_gamepad()

async def poll_controller_inputs(left_controller, right_controller):
    return (
        left_controller.get_controller_inputs() if left_controller else {},
        right_controller.get_controller_inputs() if right_controller else {}
    )

async def process_triggers_and_buttons(left_controller_state, right_controller_state, left_controller_state_old, right_controller_state_old, gamepad, shift_active, button_mappings, shift_button_mappings):
    mappings_set = shift_button_mappings if shift_active else button_mappings

    for side, state, state_old in [("left_controller", left_controller_state, left_controller_state_old), ("right_controller", right_controller_state, right_controller_state_old)]:
        for input_name, conf in mappings_set.get(side, {}).items():
            if not conf.get("enabled", True): continue
            target = conf["target"]

            if input_name == "trigger":
                val = state.get("trigger", 0.0)
                (gamepad.right_trigger if target == "right_trigger" else gamepad.left_trigger)(value=int(val * 255))

            elif input_name == "grip_button":
                if (pressed := state.get("grip_button", False)) != state_old.get("grip_button", False):
                    btn = {"right_shoulder": vg.DS4_BUTTONS.DS4_BUTTON_SHOULDER_RIGHT,
                           "left_shoulder": vg.DS4_BUTTONS.DS4_BUTTON_SHOULDER_LEFT}.get(target)
                    if btn: (gamepad.press_button if pressed else gamepad.release_button)(button=btn)

            elif input_name.startswith("ButtonPressed_"):
                bit = {"A": 1 << 1, "B": 1 << 7, "X": 1 << 1, "Y": 1 << 7}.get(input_name[-1].upper(), 0)
                now, was = state.get("ulButtonPressed", 0), state_old.get("ulButtonPressed", 0)
                if (now & bit) != (was & bit):
                    btn = {"A": vg.DS4_BUTTONS.DS4_BUTTON_CROSS,
                           "B": vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE,
                           "X": vg.DS4_BUTTONS.DS4_BUTTON_SQUARE,
                           "Y": vg.DS4_BUTTONS.DS4_BUTTON_TRIANGLE}.get(input_name[-1].upper())
                    if btn: (gamepad.press_button if now & bit else gamepad.release_button)(button=btn)

            elif input_name.startswith("button_"):
                if (pressed := state.get(input_name, False)) != state_old.get(input_name, False):
                    btn = {"triangle": vg.DS4_BUTTONS.DS4_BUTTON_TRIANGLE,
                           "circle": vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE,
                           "cross": vg.DS4_BUTTONS.DS4_BUTTON_CROSS,
                           "square": vg.DS4_BUTTONS.DS4_BUTTON_SQUARE}.get(target)
                    if btn: (gamepad.press_button if pressed else gamepad.release_button)(button=btn)

            elif input_name == "joystick_pressed":
                if (pressed := state.get("joystick_pressed", False)) != state_old.get("joystick_pressed", False):
                    btn = {"right_thumb": vg.DS4_BUTTONS.DS4_BUTTON_THUMB_RIGHT,
                           "left_thumb": vg.DS4_BUTTONS.DS4_BUTTON_THUMB_LEFT,
                           "share": vg.DS4_BUTTONS.DS4_BUTTON_SHARE,
                           "options": vg.DS4_BUTTONS.DS4_BUTTON_OPTIONS}.get(target)
                    if btn: (gamepad.press_button if pressed else gamepad.release_button)(button=btn)

async def process_left_joystick(left_controller_state, right_controller_state, shift_active, gamepad, config):
    lx = apply_deadzone_axis(
        extract_input_value(left_controller_state, right_controller_state, config.get("LEFT_X_REMAP", "left_controller:trackpad_x")),
        config.get("LEFT_X_DEADZONE", 0.1)
    ) if config.get("LEFT_X_ENABLED", True) else 0.0

    ly = apply_deadzone_axis(
        extract_input_value(left_controller_state, right_controller_state, config.get("LEFT_Y_REMAP", "left_controller:trackpad_y")),
        config.get("LEFT_Y_DEADZONE", 0.1)
    ) if config.get("LEFT_Y_ENABLED", True) else 0.0

    lx, ly = remap_float_axis(lx), remap_float_axis(ly)

    if shift_active:
        direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE
        threshold = 0.7
        if ly > threshold:
            direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTH
            if lx > threshold: direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTHEAST
            elif lx < -threshold: direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NORTHWEST
        elif ly < -threshold:
            direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTH
            if lx > threshold: direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTHEAST
            elif lx < -threshold: direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_SOUTHWEST
        elif lx > threshold: direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_EAST
        elif lx < -threshold: direction = vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_WEST

        gamepad.directional_pad(direction)
        gamepad.left_joystick_float(0.0, 0.0)
    else:
        gamepad.left_joystick_float(x_value_float=lx, y_value_float=-ly)
        gamepad.directional_pad(vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)
