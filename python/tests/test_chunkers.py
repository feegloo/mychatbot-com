from shared.chunkers import Chunk, _has_markdown_headers, _split_paragraphs, split_into_chunks


class TestSplitParagraphs:
    def test_splits_on_double_newline(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _split_paragraphs(text)
        assert result == ["First paragraph.", "Second paragraph."]

    def test_splits_on_multiple_blank_lines(self):
        text = "First.\n\n\nSecond.\n\n\n\nThird."
        result = _split_paragraphs(text)
        assert result == ["First.", "Second.", "Third."]

    def test_strips_whitespace(self):
        text = "  First.  \n\n  Second.  "
        result = _split_paragraphs(text)
        assert result == ["First.", "Second."]

    def test_filters_empty_paragraphs(self):
        text = "\n\nFirst.\n\n\n\n\nSecond.\n\n"
        result = _split_paragraphs(text)
        assert result == ["First.", "Second."]

    def test_preserves_internal_single_newlines(self):
        text = "Line one\nLine two\n\nSecond paragraph"
        result = _split_paragraphs(text)
        assert result == ["Line one\nLine two", "Second paragraph"]

    def test_blank_lines_with_spaces(self):
        text = "First.\n   \nSecond."
        result = _split_paragraphs(text)
        assert result == ["First.", "Second."]


class TestHasMarkdownHeaders:
    def test_detects_h1(self):
        assert _has_markdown_headers("# Title\n\nContent")

    def test_detects_h2(self):
        assert _has_markdown_headers("Some text\n\n## Section\n\nContent")

    def test_no_headers_plain_text(self):
        assert not _has_markdown_headers("Just plain text\n\nAnother paragraph")

    def test_hash_in_middle_of_line_not_header(self):
        assert not _has_markdown_headers("This has a #hashtag in it")

    def test_numbered_list_not_header(self):
        assert not _has_markdown_headers("1. item\n* bullet")


class TestSplitIntoChunks:
    def test_basic_chunking(self):
        text = "First paragraph about apples.\n\nSecond paragraph about oranges."
        chunks = split_into_chunks("test.txt", text)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)
        # All original text should be present across chunks
        combined = "".join(c.text for c in chunks)
        assert "apples" in combined
        assert "oranges" in combined

    def test_markdown_splitting(self):
        text = "# Header 1\n\nSome content.\n\n## Header 2\n\nMore content."
        chunks = split_into_chunks("doc.md", text)
        assert len(chunks) >= 1
        combined = "".join(c.text for c in chunks)
        assert "Header 1" in combined
        assert "Header 2" in combined

    def test_chunk_ids_are_unique(self):
        text = "\n\n".join(f"Paragraph {i} with enough content." for i in range(10))
        chunks = split_into_chunks("file.txt", text)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_file_name_is_set(self):
        text = "Some content.\n\nMore content."
        chunks = split_into_chunks("report.pdf", text)
        for chunk in chunks:
            assert chunk.file_name == "report.pdf"

    def test_large_text_is_split(self):
        # Create text larger than chunk_size (1600 chars)
        text = "\n\n".join(f"Paragraph {i}. " + "A" * 200 for i in range(20))
        chunks = split_into_chunks("big.txt", text)
        assert len(chunks) >= 2

    def test_empty_text(self):
        chunks = split_into_chunks("empty.txt", "")
        assert chunks == []

    def test_section_label_from_first_line(self):
        text = "# My Section\n\nContent under my section."
        chunks = split_into_chunks("test.md", text)
        assert chunks[0].section is not None

    def test_plain_text_paragraphs(self):
        text = "Title Line\n\nFirst paragraph content here.\n\nSecond paragraph content here."
        chunks = split_into_chunks("plain.txt", text)
        assert len(chunks) >= 1
        combined = "".join(c.text for c in chunks)
        assert "First paragraph" in combined
        assert "Second paragraph" in combined

    def test_plain_text_splits_by_paragraph(self):
        """Each paragraph separated by blank lines becomes its own chunk."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = split_into_chunks("plain.txt", text)
        assert len(chunks) == 3
        assert chunks[0].text == "Paragraph one."
        assert chunks[1].text == "Paragraph two."
        assert chunks[2].text == "Paragraph three."

    def test_plain_text_preserves_bullet_lists_in_paragraph(self):
        """Bullet points directly under a line stay in the same chunk."""
        text = (
            "Karmienie\n\n"
            "1. saszetka mokrej\n"
            "* powinna zjeść całą lub 80%\n"
            "* jeśli nie chce jeść, dodać suchej karmy\n\n"
            "2. filet\n"
            "* raz na parę dni\n"
            "* jak zje, dołożyć połowę saszetki mokrej"
        )
        chunks = split_into_chunks("test.txt", text)
        assert len(chunks) == 3
        assert chunks[0].text == "Karmienie"
        assert "saszetka mokrej" in chunks[1].text
        assert "powinna zjeść" in chunks[1].text
        assert "filet" in chunks[2].text
        assert "raz na parę dni" in chunks[2].text

    def test_plain_text_removes_extra_blank_lines(self):
        """Multiple blank lines between paragraphs still produce clean chunks."""
        text = "First.\n\n\n\nSecond.\n\n\n\n\nThird."
        chunks = split_into_chunks("test.txt", text)
        assert len(chunks) == 3
        assert chunks[0].text == "First."
        assert chunks[1].text == "Second."
        assert chunks[2].text == "Third."

    def test_crlf_line_endings_normalized(self):
        """Windows-style line endings are normalized before splitting."""
        text = "First.\r\n\r\nSecond.\r\n\r\nThird."
        chunks = split_into_chunks("test.txt", text)
        assert len(chunks) == 3

    def test_aurora_instructions_file(self):
        """Real-world test: Aurora cat instructions should split into ~10 paragraphs."""
        text = (
            "Karmienie\n\n\n"
            "1. saszetka mokrej\n"
            "* powinna zjeść całą lub 80%\n"
            "* jeśli nie chce jeść, posypać pokruszone kostki lub dodać suchej karmy i wymieszać\n"
            "* sucha karma: w jednym posiłku może zjeść 1 warstwę miseczki\n"
            "   * nie zostawiaj proszę za dużo suchej\n\n\n"
            "2. filet\n"
            "* raz na parę dni\n"
            "* jak zje, dołożyć połowę saszetki mokrej (zamknij klipsem)\n"
            "* kolejny posiłek: drugi filet + druga połowa saszetki mokrej\n\n\n"
            "Jeśli zostanie mało mokrej i już nie chce jeść, wyrzuć mokrą.\n\n\n"
            "Kuweta\n"
            "* są dwie automatyczne kuwety\n"
            "* przez 5 dni nie trzeba będzie wyrzucać worków\n\n\n"
            "Fontanna\n"
            "* woda będzie uzupełniona, nie musisz nic robić\n\n\n"
            "Trawa\n"
            "* możesz raz podlać po 3 dniach\n\n\n"
            "SMSy / zdjęcia\n"
            "* po wizycie możesz napisać mi krótki tekst\n\n\n"
            "Najbardziej zależy mi tym, aby ładnie jadła.\n\n\n"
            "Na koniec wrzuć klucz do skrzynki pocztowej."
        )
        chunks = split_into_chunks("Aurora - instrukcja.txt", text)
        assert len(chunks) == 10
        assert chunks[0].text == "Karmienie"
        assert "saszetka mokrej" in chunks[1].text
        assert "filet" in chunks[2].text
        assert "Kuweta" in chunks[4].text
        assert "Fontanna" in chunks[5].text
        assert "Trawa" in chunks[6].text
        assert "SMSy" in chunks[7].text
        assert "klucz" in chunks[9].text

    def test_large_plain_paragraph_further_split(self):
        """A single paragraph exceeding chunk_size is further split."""
        large_para = "Word " * 400  # ~2000 chars
        text = f"Short paragraph.\n\n{large_para}\n\nAnother short one."
        chunks = split_into_chunks("test.txt", text)
        assert len(chunks) >= 3  # short + split(large) + short

    def test_markdown_uses_chonkie_chunker(self):
        """Markdown with headers should still use the recursive chunker."""
        text = "# Section A\n\n" + "Content A. " * 50 + "\n\n## Section B\n\n" + "Content B. " * 50
        chunks = split_into_chunks("doc.md", text)
        combined = " ".join(c.text for c in chunks)
        assert "Section A" in combined
        assert "Section B" in combined
