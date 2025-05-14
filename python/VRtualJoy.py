# === VRtualJoy.py ===

import json
import os
import sys
import subprocess
import argparse

# === CLI Argument Parser ===
parser = argparse.ArgumentParser(description="Launch VRtualJoy with DS4 or XInput backend.")
parser.add_argument('--controller', choices=['ds4', 'xinput'], help='Override controller type (ds4 or xinput)')
args = parser.parse_args()

# === Resolve Paths ===
base_dir = os.path.dirname(os.path.abspath(__file__))
vrtualjoy_dir = os.path.join(base_dir, 'vrtualjoy')
config_path = os.path.join(vrtualjoy_dir, '..', '..', 'main_config.json')

# === Load Config File ===
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except Exception as e:
    print(f"[ERROR] Failed to load config: {e}")
    sys.exit(1)

# === Determine Controller Type ===
controller_type = args.controller.upper() if args.controller else config.get("CONTROLLER_TYPE", "").upper()
script_map = {
    "DS4": "DS4_main.py",
    "XINPUT": "Xinput_main.py"
}
target_script = script_map.get(controller_type)

if not target_script:
    print(f"[ERROR] Unsupported or missing CONTROLLER_TYPE: {controller_type}")
    sys.exit(1)

# === Resolve and Launch Script ===
script_path = os.path.join(vrtualjoy_dir, target_script)
if not os.path.exists(script_path):
    print(f"[ERROR] Script not found: {script_path}")
    sys.exit(1)

print(f"[INFO] Launching {target_script} using controller type: {controller_type}")
subprocess.run([sys.executable, script_path])
