import pytest
from shared.chunkers import split_into_chunks, split_structured_text, Chunk


class TestSplitStructuredText:
    def test_splits_by_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        docs = split_structured_text(text)
        assert len(docs) == 3

    def test_detects_markdown_headers(self):
        text = "# Header 1\n\nSome content.\n\n## Header 2\n\nMore content."
        docs = split_structured_text(text)
        # With markdown headers, should use MarkdownHeaderTextSplitter
        assert len(docs) >= 2

    def test_single_paragraph(self):
        text = "Just one paragraph of text."
        docs = split_structured_text(text)
        assert len(docs) == 1
        assert docs[0].page_content == "Just one paragraph of text."


class TestSplitIntoChunks:
    def test_basic_chunking(self):
        text = "First paragraph about apples.\n\nSecond paragraph about oranges."
        chunks = split_into_chunks("test.txt", text)
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)

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
        text = "A" * 3000
        chunks = split_into_chunks("big.txt", text)
        assert len(chunks) >= 2

    def test_empty_text(self):
        chunks = split_into_chunks("empty.txt", "")
        assert chunks == []
