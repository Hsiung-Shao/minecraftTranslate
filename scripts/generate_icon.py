"""Generate assets/icon.ico programmatically.

設計: 翡翠綠圓角方塊背景 + 白色文字「文」
多尺寸: 16, 32, 48, 64, 128, 256 (Windows 標準)
執行一次即可，產物 commit 進 repo。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ASSETS_DIR = Path(__file__).parent.parent / "assets"
OUTPUT = ASSETS_DIR / "icon.ico"

BG_START = (46, 160, 67)    # #2ea043 (emerald)
BG_END = (63, 185, 80)      # #3fb950 (light emerald)
FG = (255, 255, 255)
TEXT = "文"


def _gradient(size: int) -> Image.Image:
    """Solid emerald tile with subtle vertical gradient."""
    img = Image.new("RGBA", (size, size), BG_START + (255,))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        ratio = y / max(1, size - 1)
        r = int(BG_START[0] + (BG_END[0] - BG_START[0]) * ratio)
        g = int(BG_START[1] + (BG_END[1] - BG_START[1]) * ratio)
        b = int(BG_START[2] + (BG_END[2] - BG_START[2]) * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))
    return img


def _rounded_mask(size: int, radius_ratio: float = 0.2) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    r = int(size * radius_ratio)
    draw.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=r, fill=255)
    return mask


def _try_load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try Chinese-capable fonts on Windows first, fall back to default."""
    candidates = [
        "C:/Windows/Fonts/msjh.ttc",      # 微軟正黑體
        "C:/Windows/Fonts/msyh.ttc",      # Microsoft YaHei
        "C:/Windows/Fonts/simhei.ttf",    # SimHei
        "C:/Windows/Fonts/simsun.ttc",    # SimSun
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, int(size * 0.62))
        except OSError:
            continue
    return ImageFont.load_default()


def _corner_block_accent(img: Image.Image, size: int) -> None:
    """Add a small MC-style block accent in the top-right corner."""
    draw = ImageDraw.Draw(img)
    block_size = int(size * 0.18)
    x0 = size - int(size * 0.12) - block_size
    y0 = int(size * 0.12)
    # Slightly lighter fill for accent
    accent_color = (255, 255, 255, 80)
    draw.rectangle(
        [(x0, y0), (x0 + block_size, y0 + block_size)],
        fill=accent_color,
        outline=(255, 255, 255, 140),
        width=max(1, size // 80),
    )


def render(size: int) -> Image.Image:
    base = _gradient(size)
    mask = _rounded_mask(size)
    base.putalpha(mask)

    _corner_block_accent(base, size)

    # Text
    draw = ImageDraw.Draw(base)
    font = _try_load_font(size)
    try:
        bbox = draw.textbbox((0, 0), TEXT, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) / 2 - bbox[0]
        ty = (size - th) / 2 - bbox[1]
    except Exception:
        tw, th = size // 2, size // 2
        tx, ty = (size - tw) / 2, (size - th) / 2

    # Soft shadow
    shadow_offset = max(1, size // 80)
    draw.text((tx + shadow_offset, ty + shadow_offset), TEXT,
              font=font, fill=(0, 0, 0, 100))
    # Foreground
    draw.text((tx, ty), TEXT, font=font, fill=FG + (255,))
    return base


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 48, 64, 128, 256]
    images = [render(s) for s in sizes]

    # Save as multi-resolution .ico
    images[-1].save(
        OUTPUT,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    # Also save a PNG for README / preview
    images[-1].save(ASSETS_DIR / "icon.png", format="PNG")
    print(f"Wrote: {OUTPUT}")
    print(f"Wrote: {ASSETS_DIR / 'icon.png'}")


if __name__ == "__main__":
    main()
