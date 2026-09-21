"""
Golden AI - Process Coin Icon
Finds the golden coin screenshot, processes it, and generates .ICO
"""
import os
import sys
from PIL import Image, ImageDraw
import subprocess

SCREENSHOT_DIR = r"C:\Users\Anderson\Pictures\Screenshots"
ICON_PATH = r"C:\GoldenAI\assets\golden_ai.ico"
SHORTCUT_PATH = r"C:\Users\Anderson\Desktop\Golden AI.lnk"
VBS_LAUNCHER = r"C:\GoldenAI\ABRIR_GOLDEN_AI_STUDIO.vbs"

def find_golden_coin_screenshot():
    """Find the screenshot that contains a golden coin."""
    if not os.path.isdir(SCREENSHOT_DIR):
        return None

    files = []
    for f in os.listdir(SCREENSHOT_DIR):
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            fpath = os.path.join(SCREENSHOT_DIR, f)
            ftime = os.path.getmtime(fpath)
            files.append((ftime, fpath))

    files.sort(reverse=True)

    for _, fpath in files[:10]:
        try:
            img = Image.open(fpath).convert("RGB")
            small = img.resize((100, 100))
            colors = small.getcolors(10000)
            if not colors:
                continue

            colors.sort(reverse=True)
            golden_count = 0
            total = 0
            for count, (r, g, b) in colors:
                total += count
                if r > 150 and g > 120 and b < 100:
                    golden_count += count

            golden_pct = (golden_count / total * 100) if total > 0 else 0
            print(f"  {os.path.basename(fpath)}: {img.size} golden={golden_pct:.1f}%")

            if golden_pct > 5:
                return fpath
        except Exception as e:
            print(f"  Error reading {fpath}: {e}")
            continue

    return files[0][1] if files else None


def process_coin_image(image_path):
    """Process the coin image: crop to coin, make background transparent."""
    img = Image.open(image_path).convert("RGBA")
    print(f"  Original size: {img.size}")

    if img.width > 500 or img.height > 500:
        bbox = find_coin_bbox(img)
        if bbox:
            print(f"  Coin bbox: {bbox}")
            img = img.crop(bbox)
            print(f"  Cropped size: {img.size}")

    size = min(img.width, img.height)
    if img.width != img.height:
        new_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        x = (size - img.width) // 2
        y = (size - img.height) // 2
        new_img.paste(img, (x, y))
        img = new_img

    max_size = 512
    if size > max_size:
        img = img.resize((max_size, max_size), Image.LANCZOS)

    return img


def find_coin_bbox(img):
    """Find the bounding box of the golden coin in the image."""
    if img.width < 100:
        return None

    small = img.convert("RGB").resize((200, 200))
    pixels = small.load()
    width, height = small.size

    min_x, min_y = width, height
    max_x, max_y = 0, 0
    found = False

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if r > 120 and g > 90 and b < 120 and r > b:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
                found = True

    if not found:
        return None

    scale_x = img.width / width
    scale_y = img.height / height

    padding = 10
    x1 = max(0, int((min_x - padding) * scale_x))
    y1 = max(0, int((min_y - padding) * scale_y))
    x2 = min(img.width, int((max_x + padding) * scale_x))
    y2 = min(img.height, int((max_y + padding) * scale_y))

    if x2 - x1 < 20 or y2 - y1 < 20:
        return None

    return (x1, y1, x2, y2)


def make_background_transparent(img):
    """Make non-coin pixels transparent."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    pixels = img.load()
    width, height = img.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if r < 50 and g < 50 and b < 50:
                pixels[x, y] = (0, 0, 0, 0)
            elif r < 80 and g < 80 and b < 80:
                pixels[x, y] = (r, g, b, 128)

    return img


def generate_ico(img):
    """Generate .ICO file with multiple resolutions."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        resized = img.resize((size, size), Image.LANCZOS)
        images.append(resized)

    images[0].save(
        ICON_PATH,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    return True


def update_shortcut():
    """Update the desktop shortcut with the new icon."""
    try:
        ps_script = f'''
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{SHORTCUT_PATH}")
$sc.TargetPath = "{VBS_LAUNCHER}"
$sc.WorkingDirectory = "C:\\GoldenAI"
$sc.IconLocation = "{ICON_PATH}, 0"
$sc.Description = "Golden AI Studio"
$sc.Save()
'''
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, timeout=10)
        return True
    except Exception as e:
        print(f"Error updating shortcut: {e}")
        return False


def refresh_icon_cache():
    """Refresh Windows icon cache."""
    try:
        subprocess.run(
            ["cmd", "/c", "ie4uinit.exe", "-show"],
            capture_output=True, timeout=10
        )
        print("  Icon cache refreshed")
    except Exception:
        pass


def main():
    print("=" * 60)
    print("GOLDEN AI - Coin Icon Processor")
    print("=" * 60)

    print("\n[1] Finding golden coin screenshot...")
    coin_image = find_golden_coin_screenshot()
    if not coin_image:
        print("    ERROR: No suitable image found")
        return False

    print(f"    Found: {coin_image}")

    print("\n[2] Processing coin image...")
    img = process_coin_image(coin_image)
    print(f"    Processed size: {img.size}")

    print("\n[3] Making background transparent...")
    img = make_background_transparent(img)

    print("\n[4] Generating .ICO file...")
    if generate_ico(img):
        icon_size = os.path.getsize(ICON_PATH)
        print(f"    OK: Icon created at {ICON_PATH} ({icon_size} bytes)")
    else:
        print("    ERROR: Could not create icon")
        return False

    print("\n[5] Updating desktop shortcut...")
    if update_shortcut():
        print(f"    OK: Shortcut updated")
    else:
        print("    WARNING: Could not update shortcut")

    print("\n[6] Refreshing icon cache...")
    refresh_icon_cache()

    print("\n" + "=" * 60)
    print("DONE")
    print(f"  Icon: {ICON_PATH}")
    print(f"  Shortcut: {SHORTCUT_PATH}")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)