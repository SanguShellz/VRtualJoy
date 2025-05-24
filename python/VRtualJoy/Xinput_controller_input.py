# Xinput_controller_input.py

# === Standard library imports ===
import asyncio
import argparse
import logging
import os
import sys
import time
import json

# === Third-party imports ===
import vgamepad as vg

# === Logger setup ===
logger = logging.getLogger("Xinput")

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

# === Constants ===
BUTTON_NAME_MAP = {
    "a": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    "b": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    "x": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    "y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "back": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    "start": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
    "left_thumb": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    "right_thumb": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
    "left_shoulder": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "right_shoulder": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "left_trigger": "left_trigger",
    "right_trigger": "right_trigger"
}

# === Input helpers ===
def extract_input_value(left_controller_state, right_controller_state, remap_key):
    if ':' in remap_key:
        controller, input_key = remap_key.split(':', 1)
        if controller == "left_controller":
            return left_controller_state.get(input_key, 0.0)
        elif controller == "right_controller":
            return right_controller_state.get(input_key, 0.0)
        return 0.0
    return left_controller_state.get(remap_key, right_controller_state.get(remap_key, 0.0))

def apply_deadzone_axis(value, threshold):
    return 0.0 if abs(value) < threshold else value

def remap_float_axis(val):
    return max(min(val, 1.0), -1.0)

# === Controller polling ===
async def poll_controller_inputs(left_controller, right_controller):
    return (
        left_controller.get_controller_inputs() if left_controller else {},
        right_controller.get_controller_inputs() if right_controller else {}
    )

# === Left joystick + D-pad handling ===
async def process_left_joystick(left_controller_state, right_controller_state, left_grip, gamepad, config):
    l_joystick_x = apply_deadzone_axis(
        extract_input_value(left_controller_state, right_controller_state, config["LEFT_X_REMAP"]), config["LEFT_X_DEADZONE"]
    ) if config["LEFT_X_ENABLED"] else 0.0

    l_joystick_y = apply_deadzone_axis(
        extract_input_value(left_controller_state, right_controller_state, config["LEFT_Y_REMAP"]), config["LEFT_Y_DEADZONE"]
    ) if config["LEFT_Y_ENABLED"] else 0.0

    if left_grip:
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT) if l_joystick_x > 0.7 else gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT) if l_joystick_x < -0.7 else gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP) if l_joystick_y > 0.7 else gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN) if l_joystick_y < -0.7 else gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
        gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
    else:
        gamepad.left_joystick_float(x_value_float=l_joystick_x, y_value_float=l_joystick_y)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
        gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)

# === Trigger and button handling ===
async def process_triggers_and_buttons(left_controller_state, right_controller_state, left_controller_state_old, right_controller_state_old, gamepad, shift_active, config):
    mappings_set = config["SHIFT_BUTTON_MAPPINGS"] if shift_active else config["BUTTON_MAPPINGS"]

    for side, state, state_old in [
        ("left_controller", left_controller_state, left_controller_state_old),
        ("right_controller", right_controller_state, right_controller_state_old)
    ]:
        mappings = mappings_set.get(side, {})
        for input_name, conf in mappings.items():
            if not conf.get("enabled", True):
                continue

            target = conf.get("target")
            button = BUTTON_NAME_MAP.get(target)

            # Analog trigger
            if input_name == "trigger":
                val = state.get("trigger", 0.0)
                if target == "right_trigger":
                    gamepad.right_trigger_float(value_float=val)
                elif target == "left_trigger":
                    gamepad.left_trigger_float(value_float=val)

            # Digital grip
            elif input_name == "grip_button":
                was_pressed = state_old.get("grip_button", False)
                is_pressed = state.get("grip_button", False)
                if is_pressed != was_pressed and isinstance(button, int):
                    if is_pressed:
                        gamepad.press_button(button=button)
                    else:
                        gamepad.release_button(button=button)

            # Joystick click (formerly "trackpad_pressed")
            elif input_name == "joystick_pressed":
                was_pressed = state_old.get("joystick_pressed", False)
                is_pressed = state.get("joystick_pressed", False)
                if is_pressed != was_pressed and isinstance(button, int):
                    if is_pressed:
                        gamepad.press_button(button=button)
                    else:
                        gamepad.release_button(button=button)

            # Bitmask buttons
            elif input_name.startswith("ButtonPressed_"):
                bit_name = input_name.split("_")[-1]
                bit = {"Y": 1 << 1, "X": 1 << 7, "B": 1 << 1, "A": 1 << 7}.get(bit_name, 0)
                was = state_old.get("ulButtonPressed", 0)
                now = state.get("ulButtonPressed", 0)
                if (now & bit) != (was & bit) and isinstance(button, int):
                    if now & bit:
                        gamepad.press_button(button=button)
                    else:
                        gamepad.release_button(button=button)
