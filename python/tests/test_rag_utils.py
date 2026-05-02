"""Tests for rag.py utility functions — no LLM, no DB.

Covers: build_context, _strip_orphan_source_tags, _is_quiz_request,
_extract_quiz_question_count, _is_exif_request, _is_recognize_request,
_handle_exif, _build_citations, _limit_image_rows, _format_welcome_messages.
"""

from __future__ import annotations

from shared.rag import (
    _build_citations,
    _extract_quiz_question_count,
    _handle_exif,
    _is_exif_request,
    _is_quiz_request,
    _is_recognize_request,
    _limit_image_rows,
    _normalize_source_tags,
    _strip_orphan_source_tags,
    build_context,
)

# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


class TestBuildContext:
    def _row(self, **overrides) -> dict:
        base = {
            "file_name": "doc.pdf",
            "text": "Some relevant text.",
            "distance": 0.4,
            "page": None,
            "section": None,
            "chapter_number": None,
            "chapter_name": None,
            "chunk_id": "c1",
        }
        base.update(overrides)
        return base

    def test_empty_rows_returns_placeholder(self):
        assert build_context([]) == "(no matching sources found)"

    def test_single_source_label(self):
        rows = [self._row(file_name="intro.pdf", text="First chunk")]
        result = build_context(rows)
        assert "[Source 1]" in result
        assert "intro.pdf" in result
        assert "First chunk" in result

    def test_multiple_sources_numbered(self):
        rows = [
            self._row(text="chunk 1"),
            self._row(file_name="other.pdf", text="chunk 2"),
        ]
        result = build_context(rows)
        assert "[Source 1]" in result
        assert "[Source 2]" in result
        assert "chunk 1" in result
        assert "chunk 2" in result

    def test_separator_between_sources(self):
        rows = [self._row(text="a"), self._row(text="b")]
        result = build_context(rows)
        assert "--" in result

    def test_page_number_shown(self):
        rows = [self._row(page=5)]
        result = build_context(rows)
        assert "Page 5" in result

    def test_no_page_number_omitted(self):
        rows = [self._row(page=None)]
        result = build_context(rows)
        assert "Page" not in result

    def test_section_shown(self):
        rows = [self._row(section="Introduction")]
        result = build_context(rows)
        assert "Section: Introduction" in result

    def test_chapter_number_shown(self):
        rows = [self._row(chapter_number=3)]
        result = build_context(rows)
        assert "Chapter 3" in result

    def test_chapter_name_shown_when_present(self):
        rows = [self._row(chapter_number=2, chapter_name="Origins of Rome")]
        result = build_context(rows)
        assert "Chapter 2: Origins of Rome" in result

    def test_chapter_name_omitted_when_empty(self):
        rows = [self._row(chapter_number=1, chapter_name=None)]
        result = build_context(rows)
        assert "Chapter 1)" in result
        assert "None" not in result

    def test_similarity_score_computed_from_distance(self):
        # distance=0.0 → similarity=1.0
        rows = [self._row(distance=0.0)]
        result = build_context(rows)
        assert "Similarity: 1.00" in result

    def test_similarity_clamps_at_zero(self):
        # distance=2.5 → 1 - 2.5/2 = -0.25, clamped to 0.0
        rows = [self._row(distance=2.5)]
        result = build_context(rows)
        assert "Similarity: 0.00" in result

    def test_similarity_typical_value(self):
        rows = [self._row(distance=0.4)]
        result = build_context(rows)
        assert "Similarity: 0.80" in result


# ---------------------------------------------------------------------------
# _normalize_source_tags
# ---------------------------------------------------------------------------


class TestNormalizeSourceTags:
    def test_strips_trailing_letter(self):
        assert _normalize_source_tags("[source:3a]") == "[source:3]"

    def test_strips_lowercase_and_uppercase_suffix(self):
        assert _normalize_source_tags("[source:2B]") == "[source:2]"

    def test_no_suffix_unchanged(self):
        assert _normalize_source_tags("[source:5]") == "[source:5]"

    def test_multiple_tags_mixed(self):
        result = _normalize_source_tags("See [source:1a] and [source:2] here [source:3b].")
        assert "[source:1]" in result
        assert "[source:2]" in result
        assert "[source:3]" in result
        assert "a" not in result.split("[source:1]")[1].split("[")[0]

    def test_comma_separated_not_affected(self):
        # Comma-separated tags have no letter suffix; should pass through unchanged
        assert _normalize_source_tags("[source:1,2]") == "[source:1,2]"

    def test_no_source_tags_unchanged(self):
        text = "No citations here."
        assert _normalize_source_tags(text) == text


# ---------------------------------------------------------------------------
# _strip_orphan_source_tags
# ---------------------------------------------------------------------------


class TestStripOrphanSourceTags:
    def test_no_tags_unchanged(self):
        text = "No source tags here."
        assert _strip_orphan_source_tags(text, 5) == text

    def test_valid_tag_kept(self):
        result = _strip_orphan_source_tags("See [source:1] for details.", 3)
        assert "[source:1]" in result

    def test_orphan_tag_removed(self):
        result = _strip_orphan_source_tags("See [source:5] for details.", 3)
        assert "[source:5]" not in result

    def test_boundary_source_kept(self):
        result = _strip_orphan_source_tags("See [source:3] here.", 3)
        assert "[source:3]" in result

    def test_mixed_valid_and_orphan(self):
        result = _strip_orphan_source_tags("A [source:1] and [source:5]", 3)
        assert "[source:1]" in result
        assert "[source:5]" not in result

    def test_comma_separated_all_valid(self):
        result = _strip_orphan_source_tags("[source:1,2,3]", 4)
        assert "[source:1,2,3]" in result

    def test_comma_separated_partial_orphan_filtered(self):
        result = _strip_orphan_source_tags("[source:1,2,5]", 3)
        assert "5" not in result
        assert "1" in result
        assert "2" in result

    def test_comma_separated_all_orphan_tag_removed(self):
        result = _strip_orphan_source_tags("text [source:8,9] here", 3)
        assert "[source:" not in result
        assert "text" in result
        assert "here" in result

    def test_multiple_tags_mixed(self):
        result = _strip_orphan_source_tags("[source:1] [source:2,5] [source:4]", 3)
        assert "[source:1]" in result
        assert "5" not in result
        assert "[source:4]" not in result

    def test_whitespace_in_tag_handled(self):
        result = _strip_orphan_source_tags("[source: 2 ]", 3)
        assert "[source:" in result

    def test_citation_count_zero_removes_all(self):
        result = _strip_orphan_source_tags("[source:1] text [source:2]", 0)
        assert "[source:" not in result


# ---------------------------------------------------------------------------
# _is_quiz_request
# ---------------------------------------------------------------------------


class TestIsQuizRequest:
    def test_english_quiz(self):
        assert _is_quiz_request("make a quiz about history")

    def test_quiz_me(self):
        assert _is_quiz_request("quiz me on this topic")

    def test_kwiz_variant(self):
        assert _is_quiz_request("give me a kwiz")

    def test_test_keyword(self):
        assert _is_quiz_request("I want a test on chapter 3")

    def test_egzamin_polish(self):
        assert _is_quiz_request("zrób egzamin z historii")

    def test_quiz_case_insensitive(self):
        assert _is_quiz_request("QUIZ ME")
        assert _is_quiz_request("Quiz time!")

    def test_unrelated_question_false(self):
        assert not _is_quiz_request("what is the capital of France?")

    def test_contains_quiz_as_substring_boundary(self):
        # "quiz" inside another word should not match due to \b
        assert not _is_quiz_request("mosquito bites")

    def test_empty_string_false(self):
        assert not _is_quiz_request("")

    def test_summarize_false(self):
        assert not _is_quiz_request("please summarize the chapter")


# ---------------------------------------------------------------------------
# _extract_quiz_question_count
# ---------------------------------------------------------------------------


class TestExtractQuizQuestionCount:
    def test_polish_n_pytan(self):
        assert _extract_quiz_question_count("Zrób quiz z 10 pytań o Stirnerze 🧠") == 10

    def test_english_n_questions(self):
        assert _extract_quiz_question_count("create a quiz with 15 questions") == 15

    def test_english_singular_question(self):
        assert _extract_quiz_question_count("give me a quiz with 1 question") == 1

    def test_no_number_returns_default(self):
        assert _extract_quiz_question_count("quiz me on this topic") == 5

    def test_empty_string_returns_default(self):
        assert _extract_quiz_question_count("") == 5

    def test_number_too_large_capped(self):
        assert _extract_quiz_question_count("make a quiz with 100 questions") == 20

    def test_zero_clamped_to_one(self):
        assert _extract_quiz_question_count("0 questions quiz") == 1

    def test_polish_pytania_form(self):
        assert _extract_quiz_question_count("zrób quiz z 3 pytania") == 3

    def test_number_after_keyword(self):
        assert _extract_quiz_question_count("questions: 7 about the book") == 7


# ---------------------------------------------------------------------------
# _is_exif_request
# ---------------------------------------------------------------------------


class TestIsExifRequest:
    def test_show_exif(self):
        assert _is_exif_request("show exif")

    def test_exif_metadata(self):
        assert _is_exif_request("exif metadata please")

    def test_polish_pokaz_exif(self):
        assert _is_exif_request("pokaż exif")

    def test_polish_metadane_exif(self):
        assert _is_exif_request("metadane exif")

    def test_case_insensitive(self):
        assert _is_exif_request("SHOW EXIF METADATA")

    def test_normal_question_false(self):
        assert not _is_exif_request("who is in this photo?")

    def test_empty_string_false(self):
        assert not _is_exif_request("")


# ---------------------------------------------------------------------------
# _is_recognize_request
# ---------------------------------------------------------------------------


class TestIsRecognizeRequest:
    def test_who_is_the_woman(self):
        assert _is_recognize_request("Who is the woman on the photo?")

    def test_who_is_the_man(self):
        assert _is_recognize_request("Who is the man in this picture?")

    def test_who_is_the_person(self):
        assert _is_recognize_request("Who is the person here?")

    def test_who_is_the_girl(self):
        assert _is_recognize_request("Who is the girl on the left?")

    def test_recognize_name_prompt(self):
        assert _is_recognize_request("recognize person name")

    def test_identify_person(self):
        assert _is_recognize_request("identify the person in this image")

    def test_polish_rozpoznaj(self):
        assert _is_recognize_request("rozpoznaj osobę na zdjęciu")

    def test_normal_description_false(self):
        assert not _is_recognize_request("describe the photo for me")

    def test_unrelated_false(self):
        assert not _is_recognize_request("what is the weather today?")

    def test_empty_false(self):
        assert not _is_recognize_request("")

    def test_case_insensitive(self):
        assert _is_recognize_request("WHO IS THE WOMAN in this photo?")


# ---------------------------------------------------------------------------
# _handle_exif
# ---------------------------------------------------------------------------


class TestHandleExif:
    def _image_meta(self, **overrides):
        base = {
            "file_type": "image",
            "camera_make": "Canon",
            "camera_model": "EOS R5",
            "date_taken": "2023-05-12",
            "image_width": 6720,
            "image_height": 4480,
            "file_size_bytes": 25 * 1024 * 1024,
            "image_format": "JPEG",
            "image_mode": "RGB",
            "iso": "800",
            "exposure_time": "1/500",
            "f_number": "f/2.8",
            "focal_length": "85mm",
            "lens_model": "RF 85mm f/1.2",
            "software": "Lightroom",
            "copyright": "© Photographer",
            "artist": "Jane Doe",
            "description": "Portrait shot",
            "gps_latitude": "52.2297",
            "gps_longitude": "21.0122",
        }
        base.update(overrides)
        return base

    def test_returns_none_for_empty_metadata(self):
        assert _handle_exif({}) is None

    def test_returns_none_for_none(self):
        assert _handle_exif(None) is None

    def test_returns_none_for_non_image_file(self):
        assert _handle_exif({"doc.pdf": {"file_type": "pdf", "camera_make": "x"}}) is None

    def test_returns_dict_with_answer_and_citations(self):
        meta = {"photo.jpg": self._image_meta()}
        result = _handle_exif(meta)
        assert isinstance(result, dict)
        assert "answer" in result
        assert "citations" in result
        assert result["citations"] == []

    def test_answer_contains_camera(self):
        meta = {"photo.jpg": self._image_meta()}
        result = _handle_exif(meta)
        assert "Canon" in result["answer"]
        assert "EOS R5" in result["answer"]

    def test_answer_contains_dimensions(self):
        meta = {"photo.jpg": self._image_meta()}
        result = _handle_exif(meta)
        assert "6720" in result["answer"]
        assert "4480" in result["answer"]

    def test_answer_contains_iso(self):
        meta = {"photo.jpg": self._image_meta()}
        result = _handle_exif(meta)
        assert "800" in result["answer"]

    def test_answer_contains_gps(self):
        meta = {"photo.jpg": self._image_meta()}
        result = _handle_exif(meta)
        assert "52.2297" in result["answer"]
        assert "21.0122" in result["answer"]

    def test_file_size_formatted_as_mb(self):
        meta = {"photo.jpg": self._image_meta(file_size_bytes=1024 * 1024)}
        result = _handle_exif(meta)
        assert "1.00 MB" in result["answer"]

    def test_no_exif_fallback_message(self):
        meta = {"photo.jpg": {"file_type": "image"}}
        result = _handle_exif(meta)
        assert result is not None
        assert "No EXIF metadata" in result["answer"]

    def test_filename_displayed_as_header(self):
        meta = {"myphoto.jpg": self._image_meta()}
        result = _handle_exif(meta)
        assert "myphoto.jpg" in result["answer"]

    def test_missing_camera_make_still_works(self):
        meta = {"photo.jpg": self._image_meta(camera_make="")}
        result = _handle_exif(meta)
        assert result is not None


# ---------------------------------------------------------------------------
# _build_citations
# ---------------------------------------------------------------------------


class TestBuildCitations:
    def _row(self, **overrides) -> dict:
        base = {
            "file_name": "doc.pdf",
            "chunk_id": "abc",
            "text": "Chunk text.",
            "section": None,
            "page": 1,
        }
        base.update(overrides)
        return base

    def test_empty_rows_returns_empty_list(self):
        assert _build_citations([]) == []

    def test_single_row_citation_structure(self):
        rows = [self._row()]
        result = _build_citations(rows)
        assert len(result) == 1
        c = result[0]
        assert c["fileName"] == "doc.pdf"
        assert c["chunkId"] == "abc"
        assert c["text"] == "Chunk text."
        assert c["page"] == 1
        assert c["section"] is None

    def test_image_name_included_when_present(self):
        rows = [self._row(image_name="page_3.png")]
        result = _build_citations(rows)
        assert result[0]["imageName"] == "page_3.png"

    def test_image_name_omitted_when_absent(self):
        rows = [self._row()]
        result = _build_citations(rows)
        assert "imageName" not in result[0]

    def test_multiple_rows_all_converted(self):
        rows = [self._row(chunk_id=f"c{i}") for i in range(5)]
        result = _build_citations(rows)
        assert len(result) == 5
        assert [c["chunkId"] for c in result] == ["c0", "c1", "c2", "c3", "c4"]


# ---------------------------------------------------------------------------
# _limit_image_rows
# ---------------------------------------------------------------------------


class TestLimitImageRows:
    def _text_row(self, chunk_id: str = "t1") -> dict:
        return {"chunk_id": chunk_id, "file_name": "doc.pdf", "text": "text", "image_name": None}

    def _image_row(self, chunk_id: str = "i1") -> dict:
        return {"chunk_id": chunk_id, "file_name": "doc.pdf", "text": "img", "image_name": f"{chunk_id}.png"}

    def test_no_images_unchanged(self):
        rows = [self._text_row("t1"), self._text_row("t2")]
        assert _limit_image_rows(rows) == rows

    def test_exactly_three_images_all_kept(self):
        rows = [self._image_row(f"i{i}") for i in range(3)]
        result = _limit_image_rows(rows)
        assert len(result) == 3

    def test_excess_images_truncated_to_three(self):
        rows = [self._image_row(f"i{i}") for i in range(6)]
        result = _limit_image_rows(rows)
        assert len(result) == 3
        assert [r["chunk_id"] for r in result] == ["i0", "i1", "i2"]

    def test_text_rows_always_kept(self):
        rows = [
            self._image_row("i1"),
            self._text_row("t1"),
            self._image_row("i2"),
            self._text_row("t2"),
            self._image_row("i3"),
            self._image_row("i4"),  # this 4th image should be dropped
            self._text_row("t3"),
        ]
        result = _limit_image_rows(rows)
        chunk_ids = [r["chunk_id"] for r in result]
        assert "i4" not in chunk_ids
        assert "t1" in chunk_ids
        assert "t2" in chunk_ids
        assert "t3" in chunk_ids

    def test_empty_rows_returns_empty(self):
        assert _limit_image_rows([]) == []

    def test_preserves_order_of_kept_rows(self):
        rows = [
            self._text_row("t1"),
            self._image_row("i1"),
            self._image_row("i2"),
            self._image_row("i3"),
            self._image_row("i4"),
            self._text_row("t2"),
        ]
        result = _limit_image_rows(rows)
        chunk_ids = [r["chunk_id"] for r in result]
        assert chunk_ids == ["t1", "i1", "i2", "i3", "t2"]

