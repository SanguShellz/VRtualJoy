# Xinput_motion_tracking.py

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
import triad_openvr

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

# === Globals ===
initial_yaw = 0.0
initial_pitch = 0.0
is_calibrated = False
last_calibration_time = 0

CALIBRATION_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "xinput_calibration.json")

HEADTRACKING_DEADZONE_X = 0.1
HEADTRACKING_DEADZONE_Y = 0.1
HEADTRACKING_SENSITIVITY_YAW = 1.5
HEADTRACKING_SENSITIVITY_PITCH = 1.5
HEADTRACKING_SMOOTHING_YAW = 0.2
HEADTRACKING_SMOOTHING_PITCH = 0.2
HEADTRACKING_RANGE_DEGREES = 45.0
HEADTRACKING_ENABLED = True

JOYSTICK_BLEND_HMD = 0.7
JOYSTICK_BLEND_CONTROLLER = 0.3

# === Smoother class ===
class Smoother:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.last = 0.0

    def smooth(self, value):
        self.last = (self.alpha * value) + ((1 - self.alpha) * self.last)
        return self.last

# === Calibration I/O ===
def save_calibration(yaw, pitch):
    global initial_yaw, initial_pitch, is_calibrated
    initial_yaw = yaw
    initial_pitch = pitch
    with open(CALIBRATION_FILE, 'w') as f:
        json.dump({"yaw": yaw, "pitch": pitch}, f)
    is_calibrated = True
    log_and_print("Calibration complete and saved.")

def load_calibration():
    global initial_yaw, initial_pitch, is_calibrated
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                initial_yaw = data.get("yaw", 0.0)
                initial_pitch = data.get("pitch", 0.0)
                is_calibrated = True
                log_and_print("Calibration loaded from file.")
        except Exception as e:
            log_and_print(f"Failed to load calibration file: {e}", level="error")

# === Calibration logic ===
def check_calibration_gesture(hmd, controller1, controller2):
    try:
        hmd_pose = hmd.get_pose_quaternion()
        c1_pose = controller1.get_pose_quaternion() if controller1 else None
        c2_pose = controller2.get_pose_quaternion() if controller2 else None
        if not (hmd_pose and c1_pose and c2_pose):
            return False
        hmd_y = hmd_pose[1]
        c1_y = c1_pose[1]
        c2_y = c2_pose[1]
        return (c1_y > hmd_y + 0.15 and c2_y > hmd_y + 0.15)
    except Exception as e:
        log_and_print(f"Calibration gesture check failed: {e}", level="warning")
        return False

async def give_haptic_feedback(controller1, controller2, duration=0.5, strength=1.0):
    try:
        if controller1:
            controller1.trigger_haptic_pulse(int(strength * 3999))
        if controller2:
            controller2.trigger_haptic_pulse(int(strength * 3999))
        await asyncio.sleep(duration)
    except Exception as e:
        log_and_print(f"Haptic feedback failed: {e}", level="warning")

async def handle_calibration(controller1, controller2, hmd, left_grip):
    global last_calibration_time
    now = time.time()
    if left_grip and now - last_calibration_time >= 1.0:
        if check_calibration_gesture(hmd, controller1, controller2):
            pose = hmd.get_pose_euler()
            if pose:
                save_calibration(pose[4], pose[5])
                asyncio.create_task(give_haptic_feedback(controller1, controller2))
                last_calibration_time = now
                await asyncio.sleep(0.1)

# === VR Headtracking ===
def clamp_and_scale(value, range_degrees):
    max_range = range_degrees
    clamped = max(-max_range, min(max_range, value))
    return clamped / max_range

def apply_deadzone(value, deadzone):
    return 0.0 if abs(value) < deadzone else value

def apply_sensitivity(value, sensitivity):
    return value * sensitivity

def apply_headtracking_to_right_stick(hmd, gamepad, raw_r_x, raw_r_y, yaw_smoother, pitch_smoother):
    if HEADTRACKING_ENABLED:
        pose = hmd.get_pose_euler()
        hmd_x = hmd_y = 0.0

        if pose and is_calibrated:
            raw_yaw = pose[4] - initial_yaw
            raw_pitch = pose[5] - initial_pitch
            # Apply sensitivity first (before deadzone)
            yaw = apply_sensitivity(raw_yaw, HEADTRACKING_SENSITIVITY_YAW)
            pitch = apply_sensitivity(raw_pitch, HEADTRACKING_SENSITIVITY_PITCH)
            # Apply deadzone after sensitivity
            yaw = apply_deadzone(yaw, HEADTRACKING_DEADZONE_X)
            pitch = apply_deadzone(pitch, HEADTRACKING_DEADZONE_Y)
            # Apply smoothing
            hmd_x = clamp_and_scale(yaw_smoother.smooth(yaw), HEADTRACKING_RANGE_DEGREES)
            hmd_y = clamp_and_scale(pitch_smoother.smooth(pitch), HEADTRACKING_RANGE_DEGREES)

        # Blend head tracking with raw controller values
        right_x = max(min(JOYSTICK_BLEND_HMD * hmd_x + JOYSTICK_BLEND_CONTROLLER * raw_r_x, 1.0), -1.0)
        right_y = max(min(JOYSTICK_BLEND_HMD * hmd_y + JOYSTICK_BLEND_CONTROLLER * raw_r_y, 1.0), -1.0)
    else:
        right_x = raw_r_x
        right_y = raw_r_y

    gamepad.right_joystick_float(x_value_float=right_x, y_value_float=right_y)
