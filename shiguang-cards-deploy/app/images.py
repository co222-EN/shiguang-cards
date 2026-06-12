from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_image(content_type: str, data: bytes, max_mb: int) -> None:
    if content_type not in ALLOWED_TYPES:
        raise ValueError("只支持 JPG、PNG 或 WebP 图片")
    if len(data) > max_mb * 1024 * 1024:
        raise ValueError(f"图片不能超过 {max_mb}MB")


def normalize_image(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, "#ffffff")
        background.paste(image, mask=image.split()[-1])
        image = background
    return image


def crop_to_ratio(image: Image.Image, ratio: float = 4 / 5) -> Image.Image:
    width, height = image.size
    current_ratio = width / height
    if current_ratio > ratio:
        new_width = int(height * ratio)
        left = max((width - new_width) // 2, 0)
        box = (left, 0, left + new_width, height)
    else:
        new_height = int(width / ratio)
        top = max((height - new_height) // 2, 0)
        box = (0, top, width, top + new_height)
    return image.crop(box)


def fit_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_ratio = size[0] / size[1]
    cropped = crop_to_ratio(image, target_ratio)
    return cropped.resize(size, Image.Resampling.LANCZOS)


def fit_inside(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    copy = image.copy()
    copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    return copy


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def make_ins_card(image: Image.Image, mood_color: str = "#f3a6a6") -> Image.Image:
    canvas_size = (1200, 1500)
    canvas = Image.new("RGB", canvas_size, mood_color)
    wash = Image.new("RGB", canvas_size, "#fffaf7")
    canvas = Image.blend(canvas, wash, 0.58)

    grain = Image.effect_noise(canvas_size, 7).convert("L")
    canvas = Image.composite(ImageEnhance.Brightness(canvas).enhance(0.98), canvas, grain.point(lambda x: 24 if x > 130 else 0))

    photo = fit_cover(image, (960, 1200))
    photo = ImageEnhance.Color(photo).enhance(1.08)
    photo = ImageEnhance.Contrast(photo).enhance(1.04)

    mat = Image.new("RGB", (1030, 1290), "#fffdf9")
    mat_mask = rounded_mask(mat.size, 34)
    shadow = Image.new("RGBA", mat.size, (0, 0, 0, 86))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.alpha_composite(shadow, (91, 116))
    canvas_rgba.paste(mat.convert("RGBA"), (85, 94), mat_mask)

    photo_mask = rounded_mask(photo.size, 22)
    canvas_rgba.paste(photo.convert("RGBA"), (120, 130), photo_mask)

    draw = ImageDraw.Draw(canvas_rgba)
    draw.rounded_rectangle((120, 1360, 1080, 1418), radius=29, fill=(255, 255, 255, 172))
    draw.ellipse((142, 1378, 168, 1404), fill=(239, 111, 97, 230))
    draw.ellipse((184, 1378, 210, 1404), fill=(255, 211, 110, 230))
    draw.ellipse((226, 1378, 252, 1404), fill=(167, 216, 201, 230))

    return canvas_rgba.convert("RGB")


def make_images(data: bytes, output_dir: Path, record_id: str | None = None) -> dict[str, Path]:
    record_id = record_id or uuid4().hex
    original_dir = output_dir / "photos" / "original"
    cropped_dir = output_dir / "photos" / "cropped"
    thumbs_dir = output_dir / "photos" / "thumbs"
    original_dir.mkdir(parents=True, exist_ok=True)
    cropped_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    image = normalize_image(data)
    original = original_dir / f"{record_id}.jpg"
    cropped = cropped_dir / f"{record_id}.jpg"
    thumb = thumbs_dir / f"{record_id}.jpg"

    image.save(original, "JPEG", quality=92, optimize=True)

    card = crop_to_ratio(image)
    card.thumbnail((1400, 1750), Image.Resampling.LANCZOS)
    styled = make_ins_card(card)
    styled.save(cropped, "JPEG", quality=91, optimize=True)

    preview = crop_to_ratio(image, ratio=1)
    preview.thumbnail((640, 640), Image.Resampling.LANCZOS)
    preview.save(thumb, "JPEG", quality=86, optimize=True)

    return {"original": original, "cropped": cropped, "thumb": thumb}


def restyle_card_for_analysis(original_path: Path, cropped_path: Path, *, is_food: bool, mood_color: str) -> None:
    image = Image.open(original_path)
    image = ImageOps.exif_transpose(image).convert("RGB")
    styled = make_ins_card(image, mood_color)
    styled.save(cropped_path, "JPEG", quality=91, optimize=True)


def image_to_data_url(path: Path) -> str:
    import base64

    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"
