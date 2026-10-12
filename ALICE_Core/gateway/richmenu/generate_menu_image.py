import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
OUTPUT_PATH = BASE_DIR / "UserMenu.png"
FONT_BOLD_PATH = BASE_DIR / "NotoSansJP-Bold.ttf"
FONT_REG_PATH = BASE_DIR / "NotoSansJP-Regular.ttf"

# 2500 x 1686 canvas
WIDTH = 2500
HEIGHT = 1686

img = Image.new("RGBA", (WIDTH, HEIGHT), (250, 250, 250, 255))
draw = ImageDraw.Draw(img)

# Fonts (~1.5x larger as requested)
font_title = ImageFont.truetype(str(FONT_BOLD_PATH), 102)
font_sub = ImageFont.truetype(str(FONT_REG_PATH), 45)
font_footer = ImageFont.truetype(str(FONT_REG_PATH), 34)
font_icon_symbol = ImageFont.truetype(str(FONT_BOLD_PATH), 170)

# Tile Layout: 3 columns x 2 rows
# Col width: 833, 834, 833 -> Total 2500
# Row height: 843, 843 -> Total 1686
COLS = [
    (0, 833),
    (833, 834),
    (1667, 833),
]
ROWS = [
    (0, 843),
    (843, 843),
]

TILES = [
    # Row 0
    {
        "col": 0, "row": 0,
        "title": "文字起こし",
        "sub": "音声をテキストに変換します",
        "bg_color": (255, 253, 246, 255),
        "icon_type": "mic",
        "icon_color": (40, 40, 40, 255),
        "badge_color": (252, 238, 212, 255),
    },
    {
        "col": 1, "row": 0,
        "title": "要約",
        "sub": "会議内容を要点だけまとめます",
        "bg_color": (244, 251, 247, 255),
        "icon_type": "doc",
        "icon_color": (30, 30, 30, 255),
        "badge_color": (215, 246, 226, 255),
    },
    {
        "col": 2, "row": 0,
        "title": "議事録",
        "sub": "整理された議事録を作成します",
        "bg_color": (255, 253, 245, 255),
        "icon_type": "clipboard",
        "icon_color": (40, 40, 40, 255),
        "badge_color": (252, 241, 212, 255),
    },
    # Row 1
    {
        "col": 0, "row": 1,
        "title": "Queue",
        "sub": "処理待ち・待機状況を確認します",
        "bg_color": (244, 247, 255, 255),
        "icon_type": "queue",
        "icon_color": (35, 50, 100, 255),
        "badge_color": (220, 232, 255, 255),
    },
    {
        "col": 1, "row": 1,
        "title": "ヘルプ",
        "sub": "使い方や対応ファイルを確認します",
        "bg_color": (242, 248, 252, 255),
        "icon_type": "help",
        "icon_color": (30, 30, 30, 255),
        "badge_color": (220, 238, 252, 255),
    },
    {
        "col": 2, "row": 1,
        "title": "送信方法",
        "sub": "ファイルの送信手順を確認します",
        "bg_color": (243, 249, 244, 255),
        "icon_type": "clip",
        "icon_color": (35, 115, 60, 255),
        "badge_color": (218, 245, 226, 255),
    },
]


def draw_icon(draw: ImageDraw.ImageDraw, tile_type: str, cx: int, cy: int, color: tuple, badge_color: tuple):
    # Circle background badge (~2x larger: radius 175 px)
    r = 175
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=badge_color)

    if tile_type == "mic":
        # Mic body & stand (~2x size)
        draw.rounded_rectangle([cx - 38, cy - 80, cx + 38, cy + 24], radius=38, fill=color)
        draw.arc([cx - 66, cy - 40, cx + 66, cy + 44], start=0, end=180, fill=color, width=16)
        draw.line([cx, cy + 44, cx, cy + 88], fill=color, width=16)
        draw.line([cx - 48, cy + 88, cx + 48, cy + 88], fill=color, width=16)
        # Sound waves
        draw.line([cx - 105, cy - 16, cx - 105, cy + 16], fill=(180, 180, 180, 255), width=10)
        draw.line([cx - 128, cy - 40, cx - 128, cy + 40], fill=(180, 180, 180, 255), width=10)
        draw.line([cx + 105, cy - 16, cx + 105, cy + 16], fill=(180, 180, 180, 255), width=10)
        draw.line([cx + 128, cy - 40, cx + 128, cy + 40], fill=(180, 180, 180, 255), width=10)

    elif tile_type == "doc":
        # Document icon (~2x size)
        w, h = 125, 158
        x0, y0 = cx - w // 2, cy - h // 2
        draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=16, outline=color, width=13)
        draw.line([x0 + 28, y0 + 42, x0 + w - 28, y0 + 42], fill=(50, 160, 120, 255), width=12)
        draw.line([x0 + 28, y0 + 78, x0 + w - 28, y0 + 78], fill=color, width=10)
        draw.line([x0 + 28, y0 + 112, x0 + w - 44, y0 + 112], fill=color, width=10)
        # Sparkle
        draw.polygon([(cx + 90, cy - 55), (cx + 98, cy - 40), (cx + 115, cy - 32), (cx + 98, cy - 24), (cx + 90, cy - 9), (cx + 82, cy - 24), (cx + 65, cy - 32), (cx + 82, cy - 40)], fill=(50, 180, 140, 255))

    elif tile_type == "clipboard":
        # Clipboard icon (~2x size)
        w, h = 130, 158
        x0, y0 = cx - w // 2, cy - h // 2 + 8
        draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=16, outline=color, width=13)
        # Clip top
        draw.rounded_rectangle([cx - 38, y0 - 20, cx + 38, y0 + 20], radius=10, outline=color, width=11)
        # Checklines
        for y_off in [52, 88, 120]:
            draw.line([x0 + 28, y0 + y_off, x0 + 48, y0 + y_off], fill=color, width=10)
            draw.line([x0 + 60, y0 + y_off, x0 + w - 28, y0 + y_off], fill=color, width=10)

    elif tile_type == "queue":
        # Queue / Stack list icon (~2x size)
        w, h = 136, 136
        x0, y0 = cx - w // 2, cy - h // 2 - 5
        # 3 Stacked horizontal cards
        draw.rounded_rectangle([x0, y0, x0 + w, y0 + 34], radius=10, fill=color)
        draw.rounded_rectangle([x0, y0 + 48, x0 + w, y0 + 82], radius=10, fill=(70, 100, 180, 255))
        draw.rounded_rectangle([x0, y0 + 96, x0 + w, y0 + 130], radius=10, fill=(120, 150, 220, 255))
        # Clock / Timer badge on bottom right
        draw.ellipse([cx + 30, cy + 15, cx + 95, cy + 80], fill=(255, 255, 255, 255), outline=color, width=8)
        draw.line([cx + 62, cy + 47, cx + 62, cy + 32], fill=color, width=8)
        draw.line([cx + 62, cy + 47, cx + 75, cy + 47], fill=color, width=8)

    elif tile_type == "help":
        # Speech bubble with question mark (~2x size)
        r_b = 80
        draw.ellipse([cx - r_b, cy - r_b - 8, cx + r_b, cy + r_b - 8], outline=color, width=13)
        # Tail
        draw.polygon([(cx - 30, cy + 50), (cx - 55, cy + 85), (cx - 3, cy + 65)], fill=color)
        # Question mark
        bbox = font_icon_symbol.getbbox("?")
        w_q = bbox[2] - bbox[0]
        h_q = bbox[3] - bbox[1]
        draw.text((cx - w_q // 2 - bbox[0], cy - 40 - bbox[1]), "?", font=font_icon_symbol, fill=color)

    elif tile_type == "clip":
        # Paperclip icon (~2x size)
        draw.line([cx - 40, cy - 48, cx + 25, cy + 24], fill=color, width=20)
        draw.arc([cx + 0, cy + 0, cx + 72, cy + 72], start=300, end=120, fill=color, width=20)
        draw.arc([cx - 72, cy - 72, cx + 15, cy + 15], start=120, end=300, fill=color, width=20)


# Draw Tiles
for tile in TILES:
    c_idx = tile["col"]
    r_idx = tile["row"]
    x_start, width = COLS[c_idx]
    y_start, height = ROWS[r_idx]
    x_end = x_start + width
    y_end = y_start + height

    # Fill background
    draw.rectangle([x_start, y_start, x_end, y_end], fill=tile["bg_color"])

    # Draw separator grid lines
    draw.rectangle([x_start, y_start, x_end, y_end], outline=(220, 224, 230, 255), width=3)

    # Content positioning
    cx = x_start + width // 2
    cy_icon = y_start + 260

    # Icon
    draw_icon(draw, tile["icon_type"], cx, cy_icon, tile["icon_color"], tile["badge_color"])

    # Title text
    title_text = tile["title"]
    bbox_t = font_title.getbbox(title_text)
    tw = bbox_t[2] - bbox_t[0]
    draw.text((cx - tw // 2, y_start + 500), title_text, font=font_title, fill=(30, 30, 30, 255))

    # Subtext
    sub_text = tile["sub"]
    bbox_s = font_sub.getbbox(sub_text)
    sw = bbox_s[2] - bbox_s[0]
    draw.text((cx - sw // 2, y_start + 655), sub_text, font=font_sub, fill=(100, 105, 115, 255))

# Footer bar at bottom
draw.rectangle([0, HEIGHT - 70, WIDTH, HEIGHT], fill=(30, 30, 30, 255))
footer_text = "ALICE は、あなたの会議をもっとスマートに。"
bbox_f = font_footer.getbbox(footer_text)
fw = bbox_f[2] - bbox_f[0]
draw.text((WIDTH // 2 - fw // 2, HEIGHT - 55), footer_text, font=font_footer, fill=(240, 240, 240, 255))

# Save output
img.save(OUTPUT_PATH, "PNG")
print(f"Successfully generated enlarged {OUTPUT_PATH} (size: {img.size})")
