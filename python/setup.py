from cx_Freeze import setup, Executable

setup(
    name="TactServer",
    version="1.0",
    description="Server for bHaptics Tact Patterns",
    executables=[Executable("TactServer.py")],
    options={
        'build_exe': {
            'packages': [],  # List of packages to include
            'include_files': [],  # List of additional files to include
        }
    },
    executables=[Executable("TactServer.py")],
)