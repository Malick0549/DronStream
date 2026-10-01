"""Draw a simple text watermark on a PNG/JPEG screenshot."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def apply_screenshot_watermark(
    file_path: str | Path,
    label: str | None = None,
) -> bool:
    """
    Overlay text on an image file in place.
    Returns True if watermark was applied, False if skipped (no Pillow / error).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("DroneStream: Pillow not installed — skip watermark")
        return False

    path = Path(file_path)
    if not path.is_file():
        return False

    try:
        img = Image.open(path).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        text = label or (
            "DroneStream · "
            + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        )

        # Prefer a small default font; fall back if truetype missing
        try:
            font = ImageFont.truetype("arial.ttf", max(14, img.width // 60))
        except Exception:
            font = ImageFont.load_default()

        # Bottom-right with padding
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = max(8, img.width - tw - 16)
        y = max(8, img.height - th - 16)

        # Semi-transparent bar behind text
        pad = 6
        draw.rectangle(
            (x - pad, y - pad, x + tw + pad, y + th + pad),
            fill=(0, 0, 0, 140),
        )
        draw.text((x, y), text, fill=(255, 255, 255, 230), font=font)

        out = Image.alpha_composite(img, overlay).convert("RGB")
        # Keep original format when possible
        suffix = path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            out.save(path, quality=92)
        else:
            out.save(path)

        return True
    except Exception as err:
        print("DroneStream: watermark error:", repr(err))
        return False