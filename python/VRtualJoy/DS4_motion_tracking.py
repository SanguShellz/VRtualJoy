# DS4_motion_tracking.py

# === Standard library imports ===
import asyncio
import argparse
import logging
import os
import sys
import time
import json
import math

# === Third-party imports ===
import openvr
import triad_openvr

# === Logger setup ===
logger = logging.getLogger("DS4")

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
HEADTRACKING_DEADZONE_X = 0.1
HEADTRACKING_DEADZONE_Y = 0.1
initial_yaw = 0.0
initial_pitch = 0.0
is_calibrated = False
last_calibration_time = 0

dname = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.realpath(__file__))
CALIBRATION_FILE = os.path.join(dname, "DS4_calibration.json")

# === Smoother class ===
class Smoother:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.last = 0.0

    def smooth(self, value):
        self.last = (self.alpha * value) + ((1 - self.alpha) * self.last)
        return self.last

# === Calibration I/O ===
def clamp_and_scale(value, range_degrees):
    if range_degrees == 0:
        return 0.0
    clamped = max(-range_degrees, min(range_degrees, value))
    return clamped / range_degrees

def apply_deadzone(value, deadzone):
    if value is None:
        return 0.0
    return 0.0 if abs(value) < deadzone else value

def apply_sensitivity(value, sensitivity):
    return value * sensitivity

def remap_float_axis(val):
    return max(min(val, 1.0), -1.0)

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

def save_calibration(yaw, pitch):
    global initial_yaw, initial_pitch, is_calibrated
    initial_yaw = yaw
    initial_pitch = pitch
    with open(CALIBRATION_FILE, 'w') as f:
        json.dump({"yaw": yaw, "pitch": pitch}, f)
    is_calibrated = True
    log_and_print("Calibration complete and saved.")

# === Gesture-based calibration ===
def check_calibration_gesture(hmd, left_controller, right_controller):
    try:
        hmd_pose = hmd.get_pose_quaternion()
        c1_pose = left_controller.get_pose_quaternion() if left_controller else None
        c2_pose = right_controller.get_pose_quaternion() if right_controller else None
        if not (hmd_pose and c1_pose and c2_pose):
            return False
        hmd_y = hmd_pose[1]
        c1_y = c1_pose[1]
        c2_y = c2_pose[1]
        return (c1_y > hmd_y + 0.15 and c2_y > hmd_y + 0.15)
    except:
        return False

async def give_haptic_feedback(left_controller, right_controller, duration=0.5, strength=1.0):
    try:
        if left_controller is not None:
            left_controller.trigger_haptic_pulse(int(strength * 3999))
        if right_controller is not None:
            right_controller.trigger_haptic_pulse(int(strength * 3999))
        await asyncio.sleep(duration)
    except Exception as e:
        log_and_print(f"Haptic feedback failed: {e}", level="warning")

async def handle_calibration(left_controller, right_controller, hmd, left_grip):
    global last_calibration_time
    now = time.time()
    cooldown_seconds = 1.0
    if left_grip and now - last_calibration_time >= cooldown_seconds:
        if check_calibration_gesture(hmd, left_controller, right_controller):
            pose = hmd.get_pose_euler()
            if pose:
                save_calibration(pose[4], pose[5])
                asyncio.create_task(give_haptic_feedback(left_controller, right_controller))
                last_calibration_time = now
                await asyncio.sleep(0.1)

# === VR device detection ===
def get_controller_role_index(device_index):
    role = openvr.VRSystem().getControllerRoleForTrackedDeviceIndex(device_index)
    if role == openvr.TrackedControllerRole_LeftHand:
        return "left"
    elif role == openvr.TrackedControllerRole_RightHand:
        return "right"
    return "unknown"

def initialize_vr_devices():
    try:
        openvr.init(openvr.VRApplication_Other)
    except Exception as e:
        log_and_print(f"OpenVR initialization failed: {e}", level="error")
        sys.exit(1)

    v = triad_openvr.triad_openvr()
    left_controller, right_controller, hmd = None, None, None

    for dev in v.devices.values():
        if dev.device_class.lower() == "controller":
            role = get_controller_role_index(dev.index)
            log_and_print(f"Controller at index {dev.index} has role: {role}", level="debug")
            if role == "left" and left_controller is None:
                left_controller = dev
            elif role == "right" and right_controller is None:
                right_controller = dev
        elif dev.device_class.lower() == "hmd":
            hmd = dev

    return v, left_controller, right_controller, hmd

# === Main headtracking application ===
async def apply_headtracking_to_right_stick(hmd, left_controller_state, right_controller_state, gamepad, yaw_smoother, pitch_smoother, config):
    raw_r_x = remap_float_axis(right_controller_state.get("trackpad_x", 0.0) if right_controller_state else 0.0)
    raw_r_y = remap_float_axis(right_controller_state.get("trackpad_y", 0.0) if right_controller_state else 0.0)

    processed_r_x = apply_sensitivity(
        apply_deadzone(raw_r_x, config.get("RIGHT_X_DEADZONE", 0.1)),
        config.get("HEADTRACKING_SENSITIVITY_YAW", 1.5)
    )
    processed_r_y = apply_sensitivity(
        apply_deadzone(raw_r_y, config.get("RIGHT_Y_DEADZONE", 0.1)),
        config.get("HEADTRACKING_SENSITIVITY_PITCH", 1.5)
    )

    if config.get("HEADTRACKING_ENABLED", True) and hmd:
        pose = hmd.get_pose_euler()
        hmd_x, hmd_y = 0.0, 0.0
        if pose:
            raw_yaw = pose[4] - initial_yaw
            raw_pitch = pose[5] - initial_pitch
            if config.get("HEADTRACKING_YAW_ENABLED", True):
                yaw = apply_sensitivity(
                    apply_deadzone(raw_yaw, config.get("HEADTRACKING_DEADZONE_X", 0.1)),
                    config.get("HEADTRACKING_SENSITIVITY_YAW", 1.5)
                )
                hmd_x = clamp_and_scale(yaw_smoother.smooth(yaw), config.get("HEADTRACKING_RANGE_DEGREES", 45.0))
            if config.get("HEADTRACKING_PITCH_ENABLED", True):
                pitch = apply_sensitivity(
                    apply_deadzone(raw_pitch, config.get("HEADTRACKING_DEADZONE_Y", 0.1)),
                    config.get("HEADTRACKING_SENSITIVITY_PITCH", 1.5)
                )
                hmd_y = clamp_and_scale(pitch_smoother.smooth(pitch), config.get("HEADTRACKING_RANGE_DEGREES", 45.0))
        right_x = max(min(config.get("JOYSTICK_BLEND_HMD", 0.7) * hmd_x + config.get("JOYSTICK_BLEND_CONTROLLER", 0.3) * processed_r_x, 1.0), -1.0)
        right_y = max(min(config.get("JOYSTICK_BLEND_HMD", 0.7) * hmd_y + config.get("JOYSTICK_BLEND_CONTROLLER", 0.3) * processed_r_y, 1.0), -1.0)
    else:
        right_x = raw_r_x
        right_y = raw_r_y

    gamepad.right_joystick_float(x_value_float=right_x, y_value_float=-right_y)
