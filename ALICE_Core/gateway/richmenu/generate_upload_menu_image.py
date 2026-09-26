import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
OUTPUT_PATH = BASE_DIR / "UploadMenu.png"
FONT_BOLD_PATH = BASE_DIR / "NotoSansJP-Bold.ttf"
FONT_REG_PATH = BASE_DIR / "NotoSansJP-Regular.ttf"

# 2500 x 843 canvas (Compact LINE Rich Menu exact size)
WIDTH = 2500
HEIGHT = 843

img = Image.new("RGBA", (WIDTH, HEIGHT), (250, 250, 250, 255))
draw = ImageDraw.Draw(img)

# Fonts matching UserMenu.png style
font_title = ImageFont.truetype(str(FONT_BOLD_PATH), 102)
font_sub = ImageFont.truetype(str(FONT_REG_PATH), 45)

# Layout: 2 equal tiles (Left: x=0..1250, Right: x=1250..2500)
TILES = [
    {
        "x_start": 0, "width": 1250,
        "title": "送信方法",
        "sub": "ファイル送信手順を確認します",
        "bg_color": (243, 249, 244, 255),
        "badge_color": (218, 245, 226, 255),
        "icon_color": (35, 115, 60, 255),
        "type": "clip",
    },
    {
        "x_start": 1250, "width": 1250,
        "title": "キャンセル",
        "sub": "受付操作をキャンセルします",
        "bg_color": (255, 245, 245, 255),
        "badge_color": (255, 225, 225, 255),
        "icon_color": (210, 55, 55, 255),
        "type": "cancel",
    },
]

def draw_upload_icon(draw: ImageDraw.ImageDraw, tile_type: str, cx: int, cy: int, color: tuple, badge_color: tuple):
    # Badge circle
    r = 160
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=badge_color)

    if tile_type == "clip":
        # Paperclip icon
        draw.line([cx - 40, cy - 48, cx + 25, cy + 24], fill=color, width=20)
        draw.arc([cx + 0, cy + 0, cx + 72, cy + 72], start=300, end=120, fill=color, width=20)
        draw.arc([cx - 72, cy - 72, cx + 15, cy + 15], start=120, end=300, fill=color, width=20)

    elif tile_type == "cancel":
        # Thick Cross / X icon
        s = 55
        w = 22
        draw.line([cx - s, cy - s, cx + s, cy + s], fill=color, width=w)
        draw.line([cx + s, cy - s, cx - s, cy + s], fill=color, width=w)

# Draw Tiles
for tile in TILES:
    x_start = tile["x_start"]
    width = tile["width"]
    x_end = x_start + width

    # Background
    draw.rectangle([x_start, 0, x_end, HEIGHT], fill=tile["bg_color"])

    # Separator outline
    draw.rectangle([x_start, 0, x_end, HEIGHT], outline=(220, 224, 230, 255), width=3)

    cx = x_start + width // 2
    cy_icon = 260

    # Draw icon
    draw_upload_icon(draw, tile["type"], cx, cy_icon, tile["icon_color"], tile["badge_color"])

    # Title text
    title_text = tile["title"]
    bbox_t = font_title.getbbox(title_text)
    tw = bbox_t[2] - bbox_t[0]
    draw.text((cx - tw // 2, 500), title_text, font=font_title, fill=(30, 30, 30, 255))

    # Subtext
    sub_text = tile["sub"]
    bbox_s = font_sub.getbbox(sub_text)
    sw = bbox_s[2] - bbox_s[0]
    draw.text((cx - sw // 2, 655), sub_text, font=font_sub, fill=(100, 105, 115, 255))

# Save output
img.save(OUTPUT_PATH, "PNG")
print(f"Successfully generated redesign {OUTPUT_PATH} (size: {img.size})")
