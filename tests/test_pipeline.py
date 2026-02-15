"""Tests for the full pipeline."""

import json
import tempfile
from pathlib import Path

from code_extract.models import PipelineConfig
from code_extract.pipeline import run_pipeline, run_scan
from code_extract.extractor import extract_item
from code_extract.cleaner import clean_block
from code_extract.formatter import format_block

FIXTURES = Path(__file__).parent / "fixtures"


def test_scan():
    config = PipelineConfig(source_dir=FIXTURES)
    items = run_scan(config)
    assert len(items) > 0


def test_extract_python_function():
    config = PipelineConfig(source_dir=FIXTURES)
    items = run_scan(config)

    func = next(i for i in items if i.name == "helper_function")
    block = extract_item(func)
    assert "def helper_function" in block.source_code
    assert len(block.imports) > 0


def test_extract_clean_format_python():
    config = PipelineConfig(source_dir=FIXTURES)
    items = run_scan(config)

    from code_extract.models import Language
    cls = next(i for i in items if i.name == "UserService" and i.language == Language.PYTHON)
    extracted = extract_item(cls)
    cleaned = clean_block(extracted)
    formatted = format_block(cleaned)

    assert "class UserService" in formatted.source_code
    assert formatted.is_valid


def test_full_pipeline_single_target():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = PipelineConfig(
            source_dir=FIXTURES,
            output_dir=Path(tmpdir) / "out",
            target="UserService",
        )
        result = run_pipeline(config)

        assert result.output_dir.exists()
        assert result.readme_path and result.readme_path.exists()
        assert result.manifest_path and result.manifest_path.exists()

        # Check manifest
        manifest = json.loads(result.manifest_path.read_text())
        assert manifest["total_items"] >= 1
        assert any(i["name"] == "UserService" for i in manifest["items"])


def test_full_pipeline_extract_all():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = PipelineConfig(
            source_dir=FIXTURES,
            output_dir=Path(tmpdir) / "out",
            extract_all=True,
        )
        result = run_pipeline(config)

        assert result.output_dir.exists()
        assert len(result.files_created) > 5  # multiple files + README + manifest

        # Should have subdirectories — at least Python is always there
        assert (result.output_dir / "python").exists()
        # With tree-sitter: JS/Dart use their language subdir names
        # Without tree-sitter: regex scanners produce javascript/dart
        # Either way, there should be more than one language subdirectory
        subdirs = [d for d in result.output_dir.iterdir() if d.is_dir()]
        assert len(subdirs) >= 2


def test_full_pipeline_with_pattern():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = PipelineConfig(
            source_dir=FIXTURES,
            output_dir=Path(tmpdir) / "out",
            pattern="*Widget*",
        )
        result = run_pipeline(config)

        manifest = json.loads(result.manifest_path.read_text())
        for item in manifest["items"]:
            assert "Widget" in item["name"] or "widget" in item["name"].lower()
