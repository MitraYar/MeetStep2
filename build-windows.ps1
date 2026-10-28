$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Run-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Exe (exit $LASTEXITCODE)" }
}
Run-Checked 'py' @('-3.12', '-m', 'venv', '.venv')
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Run-Checked $Python @('-c', 'import struct; assert struct.calcsize("P") == 8, "Use Python x64"')
Run-Checked $Python @('-m', 'pip', 'install', '-r', 'requirements.txt', 'pyinstaller==6.11.1')
Run-Checked $Python @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
Run-Checked $Python @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'MeetStep', '--add-data', 'led_packets.json;.', '--hidden-import', 'mido.backends.rtmidi', 'app.py')
Get-Item 'dist\MeetStep.exe'
Get-FileHash 'dist\MeetStep.exe' -Algorithm SHA256
