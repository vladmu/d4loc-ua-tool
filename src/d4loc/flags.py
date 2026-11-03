"""Flags for the language switcher, drawn in code (no image files): Great Britain (EN) and Ukraine (UA)."""

BLUE_UK, RED_UK = (1, 33, 105), (200, 16, 46)
BLUE_UA, YELLOW_UA = (0, 87, 183), (255, 215, 0)


def _uk(draw, w, h):
    draw.rectangle([0, 0, w, h], fill=BLUE_UK)
    for width, color in ((h // 5, (255, 255, 255)), (h // 11, RED_UK)):   # diagonals: wide white, narrower red
        draw.line([0, 0, w, h], fill=color, width=width)
        draw.line([0, h, w, 0], fill=color, width=width)
    draw.rectangle([0, h * 2 // 5, w, h * 3 // 5], fill=(255, 255, 255))   # cross: white and red
    draw.rectangle([w * 2 // 5, 0, w * 3 // 5, h], fill=(255, 255, 255))
    draw.rectangle([0, h * 9 // 20, w, h * 11 // 20], fill=RED_UK)
    draw.rectangle([w * 9 // 20, 0, w * 11 // 20, h], fill=RED_UK)


def _ua(draw, w, h):
    draw.rectangle([0, 0, w, h // 2], fill=BLUE_UA)
    draw.rectangle([0, h // 2, w, h], fill=YELLOW_UA)


def flag_image(code, width=44, height=30):
    """A PIL.Image flag for a language code: 'en' is British, 'uk' is Ukrainian."""
    from PIL import Image, ImageDraw
    k = 6   # drawn enlarged and downscaled: smooth diagonals
    img = Image.new("RGB", (width * k, height * k))
    d = ImageDraw.Draw(img)
    (_uk if code == "en" else _ua)(d, width * k, height * k)
    return img.resize((width, height), Image.LANCZOS)
