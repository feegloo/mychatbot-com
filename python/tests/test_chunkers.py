import pytest
from shared.chunkers import split_into_chunks, Chunk


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
