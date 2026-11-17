import os
import math
from PIL import Image, ImageDraw, ImageFilter

def create_nexus_icon(output_dir="build"):
    os.makedirs(output_dir, exist_ok=True)
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background Rounded Rectangle
    padding = 24
    rect = [padding, padding, size - padding, size - padding]
    corner_radius = 96

    # Gradient base
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base_draw = ImageDraw.Draw(base)

    for y in range(padding, size - padding):
        ratio = (y - padding) / (size - padding * 2)
        r = int(18 + ratio * 35)   # 18 -> 53
        g = int(12 + ratio * 15)   # 12 -> 27
        b = int(36 + ratio * 65)   # 36 -> 101
        base_draw.line([(padding, y), (size - padding, y)], fill=(r, g, b, 255))

    # Mask with rounded rectangle
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(rect, radius=corner_radius, fill=255)
    
    # Composite background
    img.paste(base, (0, 0), mask)

    # Border Glow
    border_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(border_img)
    b_draw.rounded_rectangle(rect, radius=corner_radius, outline=(168, 85, 247, 220), width=8)
    img = Image.alpha_composite(img, border_img)

    # Center Coordinates
    cx, cy = size // 2, size // 2

    # Outer Orbital Ring
    ring_radius = 160
    ring_box = [cx - ring_radius, cy - ring_radius, cx + ring_radius, cy + ring_radius]
    ring_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r_draw = ImageDraw.Draw(ring_img)
    r_draw.ellipse(ring_box, outline=(147, 51, 234, 180), width=6)
    img = Image.alpha_composite(img, ring_img)

    # Orbiting decorative nodes
    for angle_deg in [30, 150, 210, 330]:
        rad = math.radians(angle_deg)
        nx = cx + ring_radius * math.cos(rad)
        ny = cy + ring_radius * math.sin(rad)
        r_draw.ellipse([nx - 10, ny - 10, nx + 10, ny + 10], fill=(56, 189, 248, 255))
    img = Image.alpha_composite(img, ring_img)

    # Central 4-Point NEXUS Star Emblem
    star_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(star_img)

    # Star polygon
    outer_r = 140
    inner_r = 32
    points = []
    for i in range(8):
        angle = i * math.pi / 4 - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Outer star glow
    s_draw.polygon(points, fill=(192, 132, 252, 255))

    # Inner Core Diamond
    core_points = []
    core_outer_r = 70
    core_inner_r = 18
    for i in range(8):
        angle = i * math.pi / 4 - math.pi / 2
        r = core_outer_r if i % 2 == 0 else core_inner_r
        core_points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    s_draw.polygon(core_points, fill=(245, 243, 255, 255))

    # Center Cyan Node
    center_node_r = 14
    s_draw.ellipse([cx - center_node_r, cy - center_node_r, cx + center_node_r, cy + center_node_r], fill=(56, 189, 248, 255))

    img = Image.alpha_composite(img, star_img)

    # Save high-res PNG
    png_path = os.path.join(output_dir, "icon.png")
    img.save(png_path, "PNG")
    print(f"Saved {png_path} ({size}x{size})")

    # Also save as favicon.ico in root for browser / Flask
    root_favicon = os.path.join(".", "favicon.ico")
    
    # Save multi-size ICO
    ico_path = os.path.join(output_dir, "icon.ico")
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    img.save(root_favicon, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"Saved {ico_path} with sizes {icon_sizes}")

if __name__ == "__main__":
    create_nexus_icon()
