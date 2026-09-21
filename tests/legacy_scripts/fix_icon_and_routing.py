"""
Golden AI - Fix Icon and Routing
1. Regenerates the .ico with proper resolutions
2. Checks and fixes the .lnk shortcut
3. Refreshes Windows icon cache
4. Fixes routing: _is_project_tool_request should not match MT5 general inspection
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

ICON_PATH = r"C:\GoldenAI\assets\golden_ai.ico"
SHORTCUT_PATH = r"C:\Users\Anderson\Desktop\Golden AI.lnk"
VBS_LAUNCHER = r"C:\GoldenAI\ABRIR_GOLDEN_AI_STUDIO.vbs"
SCREENSHOT_PATH = r"C:\Users\Anderson\Pictures\Screenshots\Captura de tela 2026-08-14 135224.png"
STUDIO_PATH = r"C:\GoldenAI\studio\golden_ai_studio.py"
BACKUP_DIR = r"C:\GoldenAI\backups\routing_permissions_e2e_fix_v1"

def backup_files():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for f in [STUDIO_PATH, ICON_PATH, SHORTCUT_PATH]:
        if os.path.exists(f):
            dest = os.path.join(BACKUP_DIR, os.path.basename(f) + "_BEFORE_FIX")
            shutil.copy2(f, dest)
            print(f"  Backup: {dest}")
    print("  Backups created.")

def regenerate_ico():
    from PIL import Image
    if not os.path.exists(SCREENSHOT_PATH):
        print(f"  ERROR: Screenshot not found: {SCREENSHOT_PATH}")
        return False
    img = Image.open(SCREENSHOT_PATH).convert("RGBA")
    print(f"  Original screenshot: {img.size}")
    if img.width > 500:
        small = img.convert("RGB").resize((200, 200))
        pixels = small.load()
        w, h = small.size
        min_x, min_y = w, h
        max_x, max_y = 0, 0
        found = False
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]
                if r > 120 and g > 90 and b < 120 and r > b:
                    if x < min_x: min_x = x
                    if x > max_x: max_x = x
                    if y < min_y: min_y = y
                    if y > max_y: max_y = y
                    found = True
        if found:
            scale_x = img.width / w
            scale_y = img.height / h
            pad = 10
            x1 = max(0, int((min_x - pad) * scale_x))
            y1 = max(0, int((min_y - pad) * scale_y))
            x2 = min(img.width, int((max_x + pad) * scale_x))
            y2 = min(img.height, int((max_y + pad) * scale_y))
            if x2 - x1 > 20 and y2 - y1 > 20:
                img = img.crop((x1, y1, x2, y2))
                print(f"  Cropped to coin: {img.size}")
    size = min(img.width, img.height)
    if img.width != img.height:
        new_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        x = (size - img.width) // 2
        y = (size - img.height) // 2
        new_img.paste(img, (x, y))
        img = new_img
        print(f"  Made square: {img.size}")
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r < 50 and g < 50 and b < 50:
                pixels[x, y] = (0, 0, 0, 0)
            elif r < 80 and g < 80 and b < 80:
                pixels[x, y] = (r, g, b, 128)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        resized = img.resize((s, s), Image.LANCZOS)
        images.append(resized)
    images[0].save(ICON_PATH, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
    icon_size = os.path.getsize(ICON_PATH)
    print(f"  ICO generated: {ICON_PATH} ({icon_size} bytes)")
    verify = Image.open(ICON_PATH)
    print(f"  ICO verify: size={verify.size}, mode={verify.mode}")
    return True

def check_and_fix_shortcut():
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(SHORTCUT_PATH)
        print(f"  Current Target: {shortcut.TargetPath}")
        print(f"  Current IconLocation: {shortcut.IconLocation}")
        shortcut.TargetPath = VBS_LAUNCHER
        shortcut.WorkingDirectory = r"C:\GoldenAI"
        shortcut.IconLocation = f"{ICON_PATH}, 0"
        shortcut.Description = "Golden AI Studio"
        shortcut.Save()
        shortcut2 = shell.CreateShortCut(SHORTCUT_PATH)
        print(f"  New Target: {shortcut2.TargetPath}")
        print(f"  New IconLocation: {shortcut2.IconLocation}")
        return True
    except ImportError:
        print("  win32com not available, using PowerShell...")
        ps_script = '$ws = New-Object -ComObject WScript.Shell\n'
        ps_script += f'$sc = $ws.CreateShortcut("{SHORTCUT_PATH}")\n'
        ps_script += f'$sc.TargetPath = "{VBS_LAUNCHER}"\n'
        ps_script += '$sc.WorkingDirectory = "C:\\GoldenAI"\n'
        ps_script += f'$sc.IconLocation = "{ICON_PATH}, 0"\n'
        ps_script += '$sc.Description = "Golden AI Studio"\n'
        ps_script += '$sc.Save()\n'
        ps_script += 'Write-Host "IconLocation:" $sc.IconLocation\n'
        result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, timeout=15)
        print(f"  PowerShell: {result.stdout}")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def refresh_icon_cache():
    try:
        subprocess.run(["cmd", "/c", "ie4uinit.exe", "-show"], capture_output=True, timeout=10)
        print("  ie4uinit -show executed")
    except Exception:
        pass
    try:
        cache_path = os.path.expanduser(r"~\AppData\Local\IconCache.db")
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print(f"  Deleted: IconCache.db")
        explorer_cache = os.path.expanduser(r"~\AppData\Local\Microsoft\Windows\Explorer")
        if os.path.isdir(explorer_cache):
            for f in os.listdir(explorer_cache):
                if f.startswith("iconcache"):
                    try:
                        os.remove(os.path.join(explorer_cache, f))
                        print(f"  Deleted: {f}")
                    except Exception:
                        pass
    except Exception as e:
        print(f"  Cache cleanup: {e}")
    try:
        print("  Restarting Explorer...")
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True, timeout=10)
        import time
        time.sleep(2)
        subprocess.run(["start", "explorer.exe"], shell=True, timeout=10)
        print("  Explorer restarted")
    except Exception as e:
        print(f"  Explorer restart: {e}")

def fix_routing():
    with open(STUDIO_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    old_block = """        if self._is_project_tool_request(prompt):
            self._persist_current_conversation()
            if self._answer_project_tool_request(prompt):
                return"""

    new_block = """        if self._is_mt5_general_inspection(prompt):
            pass  # MT5 general inspection does not need project tools
        elif self._is_project_tool_request(prompt):
            self._persist_current_conversation()
            if self._answer_project_tool_request(prompt):
                return"""

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("  Fix 1: Added MT5 inspection check before project tool request")
    else:
        print("  Fix 1: Block not found")

    old_method = """    def _is_project_tool_request(self, prompt):
        text = self._normalized_prompt(prompt)
        if any(term in text for term in ("quanto e", "quanto \xc3\xa9", "o que e uma funcao", "o que \xc3\xa9 uma funcao", "vamos conversar")):
            return False"""

    new_method = """    def _is_project_tool_request(self, prompt):
        text = self._normalized_prompt(prompt)
        if self._is_mt5_general_inspection(prompt):
            return False
        if any(term in text for term in ("quanto e", "quanto \xc3\xa9", "o que e uma funcao", "o que \xc3\xa9 uma funcao", "vamos conversar")):
            return False"""

    if old_method in content:
        content = content.replace(old_method, new_method)
        print("  Fix 2: Added MT5 inspection check inside _is_project_tool_request")
    else:
        print("  Fix 2: Block not found")

    with open(STUDIO_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("  Studio file updated.")

def main():
    print("=" * 60)
    print("GOLDEN AI - Fix Icon and Routing")
    print("=" * 60)

    print("\n[0] Creating backups...")
    backup_files()

    print("\n[1] Regenerating .ICO file...")
    regenerate_ico()

    print("\n[2] Checking and fixing shortcut...")
    check_and_fix_shortcut()

    print("\n[3] Refreshing icon cache...")
    refresh_icon_cache()

    print("\n[4] Fixing routing in Studio...")
    fix_routing()

    print("\n[5] Verifying py_compile...")
    result = subprocess.run([sys.executable, "-m", "py_compile", STUDIO_PATH], capture_output=True, text=True)
    if result.returncode == 0:
        print("    OK: py_compile passed")
    else:
        print(f"    ERROR: py_compile failed: {result.stderr}")

    print("\n" + "=" * 60)
    print("DONE")
    print(f"  Icon: {ICON_PATH}")
    print(f"  Shortcut: {SHORTCUT_PATH}")
    print(f"  Studio: {STUDIO_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()