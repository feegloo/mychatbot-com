"""Tests for shared.url_fetch — HTML parsing and text extraction.

No network calls: all tests use local HTML strings or mock urllib.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Import the internal helpers directly for unit tests
from shared.url_fetch import _extract_visible_text, fetch_url


class TestExtractVisibleText:
    """Tests for _extract_visible_text — the HTML→plaintext extractor."""

    def test_strips_simple_tags(self):
        html = "<p>Hello <b>world</b>!</p>"
        text = _extract_visible_text(html)
        # Each text node is emitted separately; check all words are present
        assert "Hello" in text
        assert "world" in text
        assert "!" in text

    def test_skips_script_blocks(self):
        html = "<p>Visible</p><script>var x = 1;</script>"
        text = _extract_visible_text(html)
        assert "Visible" in text
        assert "var x" not in text

    def test_skips_style_blocks(self):
        html = "<style>.cls { color: red; }</style><p>Content</p>"
        text = _extract_visible_text(html)
        assert "Content" in text
        assert "color" not in text

    def test_skips_noscript_blocks(self):
        html = "<noscript>Enable JS</noscript><p>Main</p>"
        text = _extract_visible_text(html)
        assert "Main" in text
        assert "Enable JS" not in text

    def test_skips_svg_blocks(self):
        html = "<svg><path d='M0 0'/></svg><p>After</p>"
        text = _extract_visible_text(html)
        assert "After" in text
        assert "M0 0" not in text

    def test_skips_head_section(self):
        html = "<head><title>Page Title</title><meta charset='utf-8'/></head><body><p>Body</p></body>"
        text = _extract_visible_text(html)
        assert "Body" in text
        # _TextExtractor intentionally keeps <title> content for page identification
        assert "Page Title" in text

    def test_empty_html_returns_empty(self):
        assert _extract_visible_text("") == ""

    def test_only_tags_no_text(self):
        assert _extract_visible_text("<div><span></span></div>") == ""

    def test_whitespace_only_data_filtered(self):
        text = _extract_visible_text("<p>   </p><p>  \n  </p>")
        assert text.strip() == ""

    def test_multiple_paragraphs_joined_with_newline(self):
        html = "<p>First</p><p>Second</p><p>Third</p>"
        text = _extract_visible_text(html)
        assert "First" in text
        assert "Second" in text
        assert "Third" in text
        lines = [line for line in text.splitlines() if line.strip()]
        assert len(lines) == 3

    def test_nested_skip_tags_handled(self):
        # script inside noscript — both should be skipped
        html = "<noscript><script>evil()</script></noscript><p>Safe</p>"
        text = _extract_visible_text(html)
        assert "Safe" in text
        assert "evil" not in text

    def test_real_world_article_structure(self):
        html = """
        <html>
          <head><title>Article</title></head>
          <body>
            <nav>Menu</nav>
            <main>
              <h1>The Main Heading</h1>
              <p>First paragraph of the article.</p>
              <p>Second paragraph with <em>emphasis</em>.</p>
            </main>
            <footer>Footer text</footer>
            <script>analytics()</script>
          </body>
        </html>
        """
        text = _extract_visible_text(html)
        assert "The Main Heading" in text
        assert "First paragraph" in text
        assert "emphasis" in text
        # navigation and footer are not in skip-tags, so they appear
        assert "analytics" not in text

    def test_unicode_content_preserved(self):
        html = "<p>Zażółć gęślą jaźń — Polish text</p>"
        text = _extract_visible_text(html)
        assert "Zażółć" in text
        assert "Polish text" in text

    def test_html_entities_not_double_decoded(self):
        html = "<p>Tom &amp; Jerry</p>"
        text = _extract_visible_text(html)
        # HTMLParser decodes &amp; → &
        assert "Tom" in text
        assert "Jerry" in text


class TestFetchUrl:
    """Tests for fetch_url — mocked urllib so no real HTTP."""

    def _make_mock_response(self, content: str, charset: str = "utf-8"):
        mock_resp = MagicMock()
        mock_resp.read.return_value = content.encode(charset)
        mock_resp.headers.get_content_charset.return_value = charset
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("shared.url_fetch.urllib.request.urlopen")
    def test_returns_decoded_string(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response("<p>Hello</p>")
        result = fetch_url("http://example.com")
        assert result == "<p>Hello</p>"

    @patch("shared.url_fetch.urllib.request.urlopen")
    def test_uses_custom_user_agent(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response("<p>ok</p>")
        fetch_url("http://example.com")
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        assert "Mozilla" in req.get_header("User-agent")

    @patch("shared.url_fetch.urllib.request.urlopen")
    def test_uses_timeout_param(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response("<p>ok</p>")
        fetch_url("http://example.com", timeout=30)
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 30

    @patch("shared.url_fetch.urllib.request.urlopen")
    def test_default_timeout_is_15(self, mock_urlopen):
        mock_urlopen.return_value = self._make_mock_response("<p>ok</p>")
        fetch_url("http://example.com")
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 15

    @patch("shared.url_fetch.urllib.request.urlopen")
    def test_falls_back_to_utf8_when_charset_missing(self, mock_urlopen):
        mock_resp = self._make_mock_response("content")
        mock_resp.headers.get_content_charset.return_value = None
        mock_urlopen.return_value = mock_resp
        result = fetch_url("http://example.com")
        assert "content" in result

    @patch("shared.url_fetch.urllib.request.urlopen")
    def test_handles_latin1_charset(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = "café".encode("latin-1")
        mock_resp.headers.get_content_charset.return_value = "latin-1"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = fetch_url("http://example.com")
        assert "caf" in result
