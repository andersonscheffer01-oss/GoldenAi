"""
Golden AI - Icon Generator
Creates a golden robot icon (.ico) for the Golden AI Studio.
Also updates the desktop shortcut to use the VBS launcher and the new icon.
"""
import os
import struct
import sys

ICON_PATH = r"C:\GoldenAI\assets\golden_ai.ico"
SHORTCUT_PATH = r"C:\Users\Anderson\Desktop\Golden AI.lnk"
VBS_LAUNCHER = r"C:\GoldenAI\ABRIR_GOLDEN_AI_STUDIO.vbs"

def create_icon_with_pil():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        gold = (212, 175, 55, 255)
        gold_dark = (185, 144, 47, 255)
        gold_light = (242, 201, 76, 255)
        dark_bg = (7, 9, 12, 255)
        eye_color = (7, 9, 12, 255)

        margin = max(1, size // 16)
        draw.ellipse([margin, margin, size - margin - 1, size - margin - 1], fill=dark_bg)

        head_margin_x = max(2, size // 6)
        head_margin_y = max(2, size // 5)
        head_top = head_margin_y
        head_bottom = size - head_margin_y
        head_left = head_margin_x
        head_right = size - head_margin_x

        radius = max(2, size // 10)
        draw.rounded_rectangle([head_left, head_top, head_right, head_bottom], radius=radius, fill=gold)

        highlight_h = max(2, (head_bottom - head_top) // 3)
        draw.rounded_rectangle([head_left, head_top, head_right, head_top + highlight_h], radius=radius, fill=gold_light)

        eye_w = max(1, size // 10)
        eye_h = max(2, size // 8)
        eye_y = head_top + (head_bottom - head_top) // 3
        eye_spacing = max(2, size // 6)

        cx = size // 2
        left_eye_x = cx - eye_spacing // 2 - eye_w
        draw.rounded_rectangle([left_eye_x, eye_y, left_eye_x + eye_w, eye_y + eye_h], radius=max(1, eye_w // 3), fill=eye_color)
        right_eye_x = cx + eye_spacing // 2
        draw.rounded_rectangle([right_eye_x, eye_y, right_eye_x + eye_w, eye_y + eye_h], radius=max(1, eye_w // 3), fill=eye_color)

        mouth_y = head_bottom - max(2, size // 6)
        mouth_w = max(3, size // 4)
        mouth_h = max(1, size // 16)
        mouth_x = cx - mouth_w // 2
        draw.rounded_rectangle([mouth_x, mouth_y, mouth_x + mouth_w, mouth_y + mouth_h], radius=max(1, mouth_h), fill=eye_color)

        ant_x = cx
        ant_top = max(0, head_top - size // 6)
        ant_w = max(1, size // 20)
        draw.rectangle([ant_x - ant_w // 2, ant_top, ant_x + ant_w // 2, head_top], fill=gold_dark)
        ball_r = max(1, size // 14)
        draw.ellipse([ant_x - ball_r, ant_top - ball_r, ant_x + ball_r, ant_top + ball_r], fill=gold_light)

        images.append(img)

    images[0].save(ICON_PATH, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
    return True


def create_icon_minimal():
    size = 32
    width = size
    height = size
    gold_r, gold_g, gold_b = 212, 175, 55
    dark_r, dark_g, dark_b = 7, 9, 12

    xor_data = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            cx, cy = width // 2, height // 2
            dx, dy = x - cx, y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > 14:
                xor_data.extend([0, 0, 0, 0])
            elif 10 <= abs(dx) and 6 <= y - cy <= 12:
                xor_data.extend([dark_b, dark_g, dark_r, 255])
            elif abs(dx) <= 5 and y == cy + 6:
                xor_data.extend([dark_b, dark_g, dark_r, 255])
            else:
                xor_data.extend([gold_b, gold_g, gold_r, 255])

    and_mask = bytearray()
    for y in range(height):
        byte_val = 0
        for x in range(width):
            idx = (y * width + x) * 4 + 3
            if xor_data[idx] == 0:
                byte_val |= (1 << (7 - (x % 8)))
            if x % 8 == 7:
                and_mask.append(byte_val)
                byte_val = 0
        while len(and_mask) % 4 != 0:
            and_mask.append(0)

    bmp_header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0, len(xor_data) + len(and_mask), 0, 0, 0, 0)
    ico_header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, 40 + len(xor_data) + len(and_mask), 22)

    with open(ICON_PATH, "wb") as f:
        f.write(ico_header)
        f.write(entry)
        f.write(bmp_header)
        f.write(bytes(xor_data))
        f.write(bytes(and_mask))
    return True


def update_shortcut():
    try:
        import subprocess
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


def main():
    print("=" * 60)
    print("GOLDEN AI - Icon Generator")
    print("=" * 60)

    print("\n[1] Creating golden robot icon...")
    if create_icon_with_pil():
        print(f"    OK: Icon created with PIL at {ICON_PATH}")
    else:
        print("    PIL not available, using minimal icon generator...")
        if create_icon_minimal():
            print(f"    OK: Minimal icon created at {ICON_PATH}")
        else:
            print("    ERROR: Could not create icon")
            return False

    if not os.path.exists(ICON_PATH):
        print(f"    ERROR: Icon file not found at {ICON_PATH}")
        return False

    icon_size = os.path.getsize(ICON_PATH)
    print(f"    Icon size: {icon_size} bytes")

    print("\n[2] Updating desktop shortcut...")
    if update_shortcut():
        print(f"    OK: Shortcut updated at {SHORTCUT_PATH}")
        print(f"    Target: {VBS_LAUNCHER}")
        print(f"    Icon: {ICON_PATH}")
    else:
        print("    WARNING: Could not update shortcut automatically")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)