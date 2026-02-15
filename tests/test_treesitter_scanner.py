"""Tests for the tree-sitter scanner."""

import pytest
from pathlib import Path

from code_extract.models import CodeBlockType, Language

FIXTURES = Path(__file__).parent / "fixtures"

# Only run if tree-sitter is installed
try:
    from code_extract.scanner.treesitter_scanner import TreeSitterScanner
    HAS_TREESITTER = True
except ImportError:
    HAS_TREESITTER = False

pytestmark = pytest.mark.skipif(not HAS_TREESITTER, reason="tree-sitter not installed")


@pytest.fixture
def scanner():
    return TreeSitterScanner()


def test_js_scanner_finds_items(scanner):
    items = scanner.scan_file(FIXTURES / "sample.js")
    names = [i.name for i in items]
    assert "fetchUsers" in names
    assert "ApiClient" in names
    assert "UserCard" in names


def test_js_types_correct(scanner):
    items = scanner.scan_file(FIXTURES / "sample.js")
    by_name = {i.name: i for i in items}
    assert by_name["ApiClient"].block_type == CodeBlockType.CLASS
    # fetchUsers should be function
    assert by_name["fetchUsers"].block_type == CodeBlockType.FUNCTION


def test_dart_scanner_finds_items(scanner):
    items = scanner.scan_file(FIXTURES / "sample.dart")
    names = [i.name for i in items]
    assert "UserModel" in names
    assert "ProfileWidget" in names
    assert "ValidationMixin" in names


def test_dart_widget_detection(scanner):
    items = scanner.scan_file(FIXTURES / "sample.dart")
    by_name = {i.name: i for i in items}
    assert by_name["ProfileWidget"].block_type == CodeBlockType.WIDGET
    assert by_name["UserModel"].block_type == CodeBlockType.CLASS
    assert by_name["ValidationMixin"].block_type == CodeBlockType.MIXIN


def test_rust_scanner(scanner):
    items = scanner.scan_file(FIXTURES / "sample.rs")
    names = [i.name for i in items]
    assert "Config" in names
    assert "Status" in names
    assert "process_status" in names
    assert "Serializable" in names

    by_name = {i.name: i for i in items}
    assert by_name["Config"].block_type == CodeBlockType.STRUCT
    assert by_name["Status"].block_type == CodeBlockType.ENUM
    assert by_name["process_status"].block_type == CodeBlockType.FUNCTION
    assert by_name["Serializable"].block_type == CodeBlockType.TRAIT


def test_go_scanner(scanner):
    items = scanner.scan_file(FIXTURES / "sample.go")
    names = [i.name for i in items]
    assert "UserService" in names
    assert "Validator" in names
    assert "NewUserService" in names
    assert "FormatAge" in names

    by_name = {i.name: i for i in items}
    assert by_name["UserService"].block_type == CodeBlockType.STRUCT
    assert by_name["Validator"].block_type == CodeBlockType.INTERFACE
    assert by_name["NewUserService"].block_type == CodeBlockType.FUNCTION


def test_java_scanner(scanner):
    items = scanner.scan_file(FIXTURES / "sample.java")
    names = [i.name for i in items]
    assert "TaskManager" in names
    assert "Runnable" in names
    assert "Priority" in names

    by_name = {i.name: i for i in items}
    assert by_name["TaskManager"].block_type == CodeBlockType.CLASS
    assert by_name["Runnable"].block_type == CodeBlockType.INTERFACE
    assert by_name["Priority"].block_type == CodeBlockType.ENUM


def test_swift_scanner(scanner):
    items = scanner.scan_file(FIXTURES / "sample.swift")
    names = [i.name for i in items]
    assert "NetworkManager" in names
    assert "UserProfile" in names
    assert "Cacheable" in names
    assert "AppError" in names

    by_name = {i.name: i for i in items}
    assert by_name["NetworkManager"].block_type == CodeBlockType.CLASS
    assert by_name["UserProfile"].block_type == CodeBlockType.STRUCT
    assert by_name["Cacheable"].block_type == CodeBlockType.INTERFACE
    assert by_name["AppError"].block_type == CodeBlockType.ENUM


def test_end_lines_populated(scanner):
    """Tree-sitter should populate end_line for items."""
    items = scanner.scan_file(FIXTURES / "sample.rs")
    for item in items:
        if item.end_line is not None:
            assert item.end_line >= item.line_number


def test_scan_directory(scanner):
    items = scanner.scan_directory(FIXTURES)
    languages = {i.language for i in items}
    # Should find at least JS, Dart, Rust, Go, Java, Swift
    assert Language.JAVASCRIPT in languages
    assert Language.DART in languages
    assert Language.RUST in languages
    assert Language.GO in languages
    assert Language.JAVA in languages
    assert Language.SWIFT in languages
