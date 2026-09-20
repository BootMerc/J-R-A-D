"""Phase 9 tests for app/integrations/tiktok/visual_generator.py.

Unlike Phase 7/8's OS-level and network integrations, this module has no
side effect worth mocking — no browser, no clipboard, no network call, just
local Pillow calls. So these tests generate real images and assert on the
real files, rather than mocking anything. Service/API-level Phase 9 tests
(PostService.generate_tiktok_visual and POST
/posts/{id}/generate-tiktok-visual) live in test_posts.py instead.
"""

from pathlib import Path

from PIL import Image

from app.integrations.tiktok.visual_generator import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    _has_arabic,
    _reshape,
    _to_display,
    generate_recruitment_visual,
)


def test_has_arabic_detects_arabic_script():
    assert _has_arabic("نبحث عن سائق") is True
    assert _has_arabic("Warehouse Associate") is False
    assert _has_arabic("Customer Service - خدمة عملاء") is True
    assert _has_arabic("") is False


def test_has_arabic_detects_reshaped_presentation_forms():
    """Reshaping moves characters into the Arabic Presentation Forms
    block — _has_arabic must still recognize them there, since
    _to_display() relies on checking already-reshaped lines."""
    reshaped = _reshape("سائق")
    assert _has_arabic(reshaped) is True


def test_reshape_changes_arabic_text():
    original = "نبحث عن سائق توصيل"
    reshaped = _reshape(original)
    assert reshaped != original  # contextual joining actually did something


def test_reshape_leaves_latin_text_unchanged():
    text = "Warehouse Associate"
    assert _reshape(text) == text


def test_to_display_reorders_reshaped_arabic():
    original = "نبحث عن سائق"
    reshaped = _reshape(original)
    displayed = _to_display(reshaped)
    # bidi reordering changes character order for RTL display — the
    # reshaped-but-not-yet-reordered string and the final display string
    # must differ for genuinely multi-word Arabic text.
    assert displayed != reshaped


def test_to_display_leaves_latin_text_unchanged():
    reshaped = _reshape("Warehouse Associate")
    assert _to_display(reshaped) == "Warehouse Associate"


def test_generate_recruitment_visual_creates_valid_png(tmp_path):
    output_path = tmp_path / "test.png"
    result = generate_recruitment_visual(
        job_title="Warehouse Associate",
        company="Acme Logistics",
        location="Cairo, Egypt",
        salary_text="8,000 - 10,000 EGP",
        output_path=str(output_path),
    )

    assert result == str(output_path)
    assert output_path.exists()
    with Image.open(output_path) as img:
        assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
        assert img.format == "PNG"


def test_generate_recruitment_visual_handles_arabic_content(tmp_path):
    output_path = tmp_path / "arabic.png"
    generate_recruitment_visual(
        job_title="نبحث عن سائق توصيل بدوام كامل",
        company="شركة النقل السريع",
        location="القاهرة",
        salary_text="6000 جنيه",
        output_path=str(output_path),
    )

    assert output_path.exists()
    with Image.open(output_path) as img:
        assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)


def test_generate_recruitment_visual_handles_missing_optional_fields(tmp_path):
    """company/location/salary_text are all Optional on the Job model —
    must not crash when they're None."""
    output_path = tmp_path / "minimal.png"
    generate_recruitment_visual(
        job_title="Cashier",
        company=None,
        location=None,
        salary_text=None,
        output_path=str(output_path),
    )
    assert output_path.exists()


def test_generate_recruitment_visual_creates_parent_directories(tmp_path):
    nested_path = tmp_path / "nested" / "dirs" / "post_1.png"
    generate_recruitment_visual(
        job_title="Cashier", company=None, location=None, salary_text=None, output_path=str(nested_path)
    )
    assert nested_path.exists()


def test_generate_recruitment_visual_wraps_long_titles(tmp_path):
    """A long title must still fit on the canvas (word-wrapped/shrunk),
    not overflow or raise."""
    output_path = tmp_path / "long_title.png"
    generate_recruitment_visual(
        job_title="Senior Regional Warehouse and Logistics Operations Associate Manager",
        company="Acme Logistics International Holdings",
        location="Cairo, Egypt",
        salary_text="15,000 - 20,000 EGP per month",
        output_path=str(output_path),
    )
    assert output_path.exists()
    with Image.open(output_path) as img:
        assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
