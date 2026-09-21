import os
import sys

# Try to use win32com if available, otherwise use a simple approach
try:
    import win32com.client
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

def create_shortcut_with_win32():
    """Create shortcut using win32com.client"""
    shell = win32com.client.Dispatch("WScript.Shell")
    
    # Desktop path
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    shortcut_path = os.path.join(desktop, "Golden AI.lnk")
    
    # Target
    target = r"C:\GoldenAI\ABRIR_GOLDEN_AI_STUDIO.bat"
    
    # Create shortcut
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = r"C:\GoldenAI"
    shortcut.WindowStyle = 1  # Normal window
    shortcut.Description = "Golden AI Studio V2.1.0"
    
    # Try to set icon (use Python icon if available)
    python_exe = r"C:\GoldenAI\.venv\Scripts\python.exe"
    if os.path.exists(python_exe):
        shortcut.IconLocation = f"{python_exe},0"
    
    shortcut.Save()
    return shortcut_path

def create_shortcut_with_powershell():
    """Create shortcut using PowerShell"""
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    shortcut_path = os.path.join(desktop, "Golden AI.lnk")
    
    # PowerShell script to create shortcut
    ps_script = f'''
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Golden AI.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "C:\\GoldenAI\\ABRIR_GOLDEN_AI_STUDIO.bat"
$Shortcut.WorkingDirectory = "C:\\GoldenAI"
$Shortcut.WindowStyle = 1
$Shortcut.Description = "Golden AI Studio V2.1.0"
$Shortcut.Save()
Write-Host "Shortcut created at: $ShortcutPath"
'''
    
    import subprocess
    result = subprocess.run(
        ["powershell", "-Command", ps_script],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        return shortcut_path
    else:
        raise Exception(f"PowerShell failed: {result.stderr}")

def main():
    print("Creating Golden AI desktop shortcut...")
    
    # Check if shortcut already exists
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    shortcut_path = os.path.join(desktop, "Golden AI.lnk")
    
    if os.path.exists(shortcut_path):
        print(f"Shortcut already exists: {shortcut_path}")
        return shortcut_path
    
    try:
        if HAS_WIN32:
            path = create_shortcut_with_win32()
            print(f"Shortcut created using win32com: {path}")
            return path
        else:
            path = create_shortcut_with_powershell()
            print(f"Shortcut created using PowerShell: {path}")
            return path
    except Exception as e:
        print(f"Error creating shortcut: {e}")
        return None

if __name__ == "__main__":
    result = main()
    if result:
        print("SUCCESS: Desktop shortcut created!")
    else:
        print("FAILED: Could not create desktop shortcut.")