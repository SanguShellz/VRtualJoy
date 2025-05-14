Dim objShell
Set objShell = WScript.CreateObject("WScript.Shell")

pythonPath = "Bin\Python\python.exe"
scriptPath = "Bin\Python\VRtualJoy.py"

command = pythonPath & " " & scriptPath

objShell.Run command

Set objShell = Nothing
