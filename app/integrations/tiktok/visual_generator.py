# TikTok's Content Posting API requires an app audit that most users won't
# have access to, so the default workflow is manual. This module generates
# the visual, then the recruiter downloads it and posts it from their phone.
#
# Arabic text handling:
# Pillow's raqm engine normally handles Arabic shaping and RTL text
# automatically, but it isn't reliably available on Windows because the
# required FriBiDi library isn't included with Pillow's official Windows
# wheels.
#
# Since Windows is the project's deployment target, we don't rely on raqm.
# Fonts are loaded with Pillow's BASIC layout engine, while Arabic text is
# manually reshaped with arabic_reshaper and reordered with python-bidi
# before drawing. This keeps the output consistent across platforms.

import re
from pathlib import Path
from typing import Optional

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).parent / "assets"
LATIN_FONT_PATH = ASSETS_DIR / "NotoSans.ttf"
ARABIC_FONT_PATH = ASSETS_DIR / "NotoSansArabic.ttf"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920  # TikTok's standard vertical (9:16) format
MARGIN = 90

# Arabic block + supplement + extended-A (raw text) and presentation
# forms A/B (text after arabic_reshaper has already run) — checking both
# ranges means this same test works before AND after reshaping, which
# matters because reshaping moves characters into the presentation-forms
# range.
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def _has_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


def _reshape(text: str) -> str:
    """Contextual letter joining for Arabic. Word order and whitespace
    are unaffected, so this is safe to run BEFORE word-wrapping — wrap on
    the reshaped text, then bidi-reorder each resulting line separately
    (see _to_display). Running bidi on a whole wrapped multi-line block
    instead of per line would reorder across line breaks incorrectly."""
    return arabic_reshaper.reshape(text) if _has_arabic(text) else text


def _to_display(line: str) -> str:
    """Bidi-reorders one already-reshaped line into correct left-to-right
    drawing order. Call this once per line, after wrapping, right before
    drawing it — never on unreshaped text or on multiple lines at once."""
    return get_display(line) if _has_arabic(line) else line


def _load_font(sample_text: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Picks the Arabic or Latin font family based on sample_text's
    script. Always BASIC layout — see module docstring."""
    path = ARABIC_FONT_PATH if _has_arabic(sample_text) else LATIN_FONT_PATH
    font = ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)
    font.set_variation_by_axes([700 if bold else 400, 100])  # [wght, wdth]
    return font


def _wrap_reshaped_text(draw: ImageDraw.ImageDraw, reshaped_text: str, font, max_width: int) -> list[str]:
    """Greedy word-wrap by measured width. Takes already-reshaped (not
    yet bidi-reordered) text — see _reshape's docstring for why."""
    words = reshaped_text.split()
    if not words:
        return [reshaped_text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_title_font(draw: ImageDraw.ImageDraw, reshaped_title: str, max_width: int) -> ImageFont.FreeTypeFont:
    """Shrinks from a large starting size until the title's single-line
    width fits, down to a readable floor — keeps a short title big and a
    long one from overflowing the canvas."""
    size, floor = 92, 52
    while size > floor:
        font = _load_font(reshaped_title, size, bold=True)
        if draw.textlength(reshaped_title, font=font) <= max_width:
            return font
        size -= 4
    return _load_font(reshaped_title, floor, bold=True)


def _draw_centered_line(draw: ImageDraw.ImageDraw, y: int, reshaped_line: str, font, fill: str) -> None:
    draw.text((CANVAS_WIDTH / 2, y), _to_display(reshaped_line), font=font, fill=fill, anchor="mm")


def generate_recruitment_visual(
    job_title: str,
    company: Optional[str],
    location: Optional[str],
    salary_text: Optional[str],
    output_path: str,
) -> str:
    """Renders a 1080x1920 recruitment graphic and saves it as a PNG at
    output_path (parent directories created if needed). Returns
    output_path unchanged, for convenient chaining into Post.media_path.

    No external image asset — the background is a procedural gradient,
    so there's nothing to source or license beyond the two bundled fonts
    (see assets/OFL.txt).
    """
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), "#0f1f3d")
    draw = ImageDraw.Draw(img)

    top, bottom = (26, 58, 92), (10, 14, 28)
    for y_px in range(CANVAS_HEIGHT):
        t = y_px / CANVAS_HEIGHT
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y_px), (CANVAS_WIDTH, y_px)], fill=color)

    max_text_width = CANVAS_WIDTH - 2 * MARGIN
    y = 260

    tag_source = "وظيفة شاغرة" if _has_arabic(job_title) else "We're hiring"
    tag_reshaped = _reshape(tag_source)
    tag_font = _load_font(tag_reshaped, 54, bold=True)
    _draw_centered_line(draw, y, tag_reshaped, tag_font, "#7fd1ff")
    y += 140

    title_reshaped = _reshape(job_title)
    title_font = _fit_title_font(draw, title_reshaped, max_text_width)
    for line in _wrap_reshaped_text(draw, title_reshaped, title_font, max_text_width):
        _draw_centered_line(draw, y, line, title_font, "white")
        y += 110

    y += 40
    if company:
        company_reshaped = _reshape(company)
        company_font = _load_font(company_reshaped, 56, bold=False)
        _draw_centered_line(draw, y, company_reshaped, company_font, "#cfd8e3")
        y += 90

    subtitle_bits = [b for b in (location, salary_text) if b]
    if subtitle_bits:
        subtitle_reshaped = _reshape("   •   ".join(subtitle_bits))
        subtitle_font = _load_font(subtitle_reshaped, 46, bold=False)
        _draw_centered_line(draw, y, subtitle_reshaped, subtitle_font, "#9aa7b8")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return str(output_path)
