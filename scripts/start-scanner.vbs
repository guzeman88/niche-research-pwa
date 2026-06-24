' Silent launcher: no terminal window, runs the system tray app.
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "pythonw """ & ScriptDir & "\tray_app.py""", 0, False
