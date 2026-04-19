import json

from shared.extractors import (
    _reflow_pdf_text,
    _sanitize_text,
    extract_csv,
    extract_json,
    extract_plain_text,
    extract_text,
)


class TestSanitizeText:
    def test_removes_null_bytes(self):
        assert _sanitize_text("hello\x00world") == "helloworld"

    def test_preserves_newlines_and_tabs(self):
        assert _sanitize_text("line1\nline2\ttab") == "line1\nline2\ttab"

    def test_removes_control_characters(self):
        assert _sanitize_text("hello\x01\x02\x03world") == "helloworld"

    def test_preserves_normal_text(self):
        text = "Normal text with Unicode: zażółć gęślą jaźń"
        assert _sanitize_text(text) == text


class TestReflowPdfText:
    def test_joins_single_line_breaks(self):
        result = _reflow_pdf_text("hello\nworld")
        assert result == "hello world"

    def test_preserves_paragraph_breaks(self):
        result = _reflow_pdf_text("paragraph 1\n\nparagraph 2")
        assert result == "paragraph 1\n\nparagraph 2"

    def test_handles_empty_string(self):
        assert _reflow_pdf_text("") == ""

    def test_strips_whitespace(self):
        result = _reflow_pdf_text("  hello  \n  world  ")
        assert result == "hello world"


class TestExtractPlainText:
    def test_reads_text_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello, World!", encoding="utf-8")
        assert extract_plain_text(f) == "Hello, World!"


class TestExtractJson:
    def test_formats_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key":"value"}', encoding="utf-8")
        result = extract_json(f)
        parsed = json.loads(result)
        assert parsed == {"key": "value"}


class TestExtractCsv:
    def test_reads_csv(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")
        result = extract_csv(f)
        assert "Alice" in result
        assert "Bob" in result


class TestExtractText:
    def test_dispatch_txt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("plain text content", encoding="utf-8")
        result = extract_text(str(f))
        assert result == "plain text content"

    def test_dispatch_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        result = extract_text(str(f))
        assert '"a": 1' in result

    def test_dispatch_md(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\nContent", encoding="utf-8")
        result = extract_text(str(f))
        assert "Title" in result
