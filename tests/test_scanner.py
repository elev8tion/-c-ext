"""Tests for the scanner layer."""

from pathlib import Path

from code_extract.models import CodeBlockType, Language
from code_extract.scanner import scan_directory
from code_extract.scanner.python_scanner import PythonScanner
from code_extract.scanner.js_scanner import JsScanner
from code_extract.scanner.dart_scanner import DartScanner

FIXTURES = Path(__file__).parent / "fixtures"


def test_python_scanner():
    scanner = PythonScanner()
    items = scanner.scan_file(FIXTURES / "sample.py")
    names = [i.name for i in items]

    assert "helper_function" in names
    assert "UserService" in names
    assert "fetch_data" in names
    assert "get_user" in names
    assert "create_user" in names

    # Check types
    by_name = {i.name: i for i in items}
    assert by_name["helper_function"].block_type == CodeBlockType.FUNCTION
    assert by_name["UserService"].block_type == CodeBlockType.CLASS
    assert by_name["get_user"].block_type == CodeBlockType.METHOD
    assert by_name["get_user"].parent == "UserService"


def test_js_scanner():
    scanner = JsScanner()
    items = scanner.scan_file(FIXTURES / "sample.js")
    names = [i.name for i in items]

    assert "fetchUsers" in names
    assert "ApiClient" in names
    assert "UserCard" in names

    by_name = {i.name: i for i in items}
    assert by_name["fetchUsers"].block_type == CodeBlockType.FUNCTION
    assert by_name["ApiClient"].block_type == CodeBlockType.CLASS
    assert by_name["UserCard"].block_type == CodeBlockType.COMPONENT


def test_dart_scanner():
    scanner = DartScanner()
    items = scanner.scan_file(FIXTURES / "sample.dart")
    names = [i.name for i in items]

    assert "UserModel" in names
    assert "ProfileWidget" in names
    assert "ValidationMixin" in names

    by_name = {i.name: i for i in items}
    assert by_name["UserModel"].block_type == CodeBlockType.CLASS
    assert by_name["ProfileWidget"].block_type == CodeBlockType.WIDGET
    assert by_name["ValidationMixin"].block_type == CodeBlockType.MIXIN


def test_scan_directory():
    items = scan_directory(FIXTURES)
    assert len(items) > 0

    languages = {i.language for i in items}
    assert Language.PYTHON in languages
    # JS and Dart should be found by either tree-sitter or regex scanner
    assert Language.JAVASCRIPT in languages or Language.TYPESCRIPT in languages
    assert Language.DART in languages
