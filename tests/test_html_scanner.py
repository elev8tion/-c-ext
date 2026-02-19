"""Tests for HTML scanner and extractor."""

from pathlib import Path

from code_extract.models import CodeBlockType, Language
from code_extract.scanner.html_scanner import HtmlScanner
from code_extract.extractor.html_extractor import HtmlExtractor
from code_extract.extractor import extract_item
from code_extract.cleaner import clean_block
from code_extract.formatter import format_block

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "sample.html"


def test_html_scanner_finds_script_blocks():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    script_blocks = [i for i in items if i.block_type == CodeBlockType.SCRIPT_BLOCK]
    # Should find the inline <script> and the JSON <script>, but not the empty one
    # and not <script src="external.js">
    assert len(script_blocks) == 2  # inline JS + JSON


def test_html_scanner_finds_style_blocks():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    style_blocks = [i for i in items if i.block_type == CodeBlockType.STYLE_BLOCK]
    assert len(style_blocks) == 1


def test_html_scanner_finds_inner_js_constructs():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    names = [i.name for i in items]

    assert "AppRouter" in names
    assert "initApp" in names
    assert "UserList" in names

    by_name = {i.name: i for i in items}
    assert by_name["AppRouter"].block_type == CodeBlockType.CLASS
    assert by_name["initApp"].block_type == CodeBlockType.FUNCTION
    assert by_name["UserList"].block_type == CodeBlockType.COMPONENT  # uppercase arrow const


def test_html_scanner_skips_external_scripts():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    # No items should reference "external.js" — the <script src=...> is skipped
    for item in items:
        assert "external" not in item.name


def test_html_scanner_handles_empty_script():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    # The empty <script></script> should produce no items
    names = [i.name for i in items]
    # There should be no block for an empty script
    for item in items:
        if item.block_type == CodeBlockType.SCRIPT_BLOCK:
            assert item.name != "script_block_22"  # empty script on line 22


def test_html_scanner_skips_json_script_type():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    # The JSON script block should exist but not produce inner JS items
    json_block = None
    for item in items:
        if item.block_type == CodeBlockType.SCRIPT_BLOCK and "config" not in item.name:
            continue
        if item.block_type == CodeBlockType.SCRIPT_BLOCK:
            # Check if any inner items have this as parent
            pass

    # No inner JS items should have the JSON script block as parent
    json_script_blocks = [
        i for i in items
        if i.block_type == CodeBlockType.SCRIPT_BLOCK
        and i.line_number > 19  # after the main script
    ]
    if json_script_blocks:
        json_parent = json_script_blocks[0].name
        inner_items = [i for i in items if i.parent == json_parent]
        assert len(inner_items) == 0


def test_html_scanner_correct_line_numbers():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    by_name = {i.name: i for i in items}

    # AppRouter class is inside the second <script> block, around line 9
    assert by_name["AppRouter"].line_number >= 9
    assert by_name["AppRouter"].line_number <= 10

    # initApp function is around line 13-14
    assert by_name["initApp"].line_number >= 13
    assert by_name["initApp"].line_number <= 14

    # All items should use Language.HTML
    for item in items:
        assert item.language == Language.HTML


def test_html_scanner_all_items_use_html_language():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    for item in items:
        assert item.language == Language.HTML


def test_html_scanner_inner_items_have_parent():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)

    for item in items:
        if item.block_type in (CodeBlockType.CLASS, CodeBlockType.FUNCTION, CodeBlockType.COMPONENT):
            assert item.parent is not None
            assert item.parent.startswith("script_block_")


def test_html_extractor_script_block():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    script_blocks = [i for i in items if i.block_type == CodeBlockType.SCRIPT_BLOCK]
    # First script block should have JS content
    main_block = script_blocks[0]

    extractor = HtmlExtractor()
    result = extractor.extract(main_block)
    assert "AppRouter" in result.source_code
    assert "initApp" in result.source_code


def test_html_extractor_inner_function():
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    by_name = {i.name: i for i in items}

    extractor = HtmlExtractor()
    result = extractor.extract(by_name["initApp"])
    assert "function initApp" in result.source_code
    assert "new AppRouter" in result.source_code


def test_html_full_pipeline():
    """HTML files survive scan → extract → clean → format."""
    scanner = HtmlScanner()
    items = scanner.scan_file(SAMPLE_HTML)
    assert len(items) > 0

    # Pick the first script block and run it through the full pipeline
    script_blocks = [i for i in items if i.block_type == CodeBlockType.SCRIPT_BLOCK]
    assert len(script_blocks) > 0

    item = script_blocks[0]
    extracted = extract_item(item)
    assert extracted.source_code

    cleaned = clean_block(extracted)
    assert cleaned.source_code

    formatted = format_block(cleaned)
    assert formatted.source_code
    assert formatted.is_valid
