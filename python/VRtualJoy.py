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
config = {}
if os.path.exists(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"[WARNING] Failed to load config file: {e}. Falling back to DS4.")

# === Determine Controller Type ===
requested_type = args.controller.upper() if args.controller else config.get("CONTROLLER_TYPE", "DS4").upper()
controller_type = requested_type if requested_type in {"DS4", "XINPUT"} else "DS4"

if requested_type not in {"DS4", "XINPUT"}:
    print(f"[WARNING] Unsupported CONTROLLER_TYPE '{requested_type}'. Falling back to 'DS4'.")

# === Launch Script ===
script_map = {
    "DS4": "DS4_main.py",
    "XINPUT": "Xinput_main.py"
}
target_script = script_map[controller_type]
script_path = os.path.join(vrtualjoy_dir, target_script)

if not os.path.exists(script_path):
    print(f"[ERROR] Script not found: {script_path}")
    sys.exit(1)

print(f"[INFO] Launching {target_script} using controller type: {controller_type}")
subprocess.run([sys.executable, script_path])
