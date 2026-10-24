Option Explicit
Dim shell, fso, folder, python, entry
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
python = fso.BuildPath(folder, ".venv\Scripts\pythonw.exe")
entry = fso.BuildPath(folder, "launch.pyw")
If Not fso.FileExists(python) Then
    MsgBox "Run Install.bat once, then open Start.vbs again.", vbInformation, "Handy Tools App"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & entry & Chr(34), 0, False
