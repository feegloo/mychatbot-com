import pytest
from shared.extractors import clean_file_name


class TestCleanFileName:
    def test_strips_uuid_prefix(self):
        assert clean_file_name("550e8400-e29b-41d4-a716-446655440000_report.pdf") == "report.pdf"

    def test_strips_short_id_suffix_with_extension(self):
        assert clean_file_name("report_Abc123XYZdef4567.pdf") == "report.pdf"

    def test_strips_short_id_suffix_without_extension(self):
        assert clean_file_name("Wallhaven-289e1g_B2p2jEVxhjrYZkvh") == "Wallhaven-289e1g"

    def test_returns_unchanged_if_no_id(self):
        assert clean_file_name("report.pdf") == "report.pdf"

    def test_handles_empty_string(self):
        assert clean_file_name("") == ""

    def test_only_strips_first_uuid_prefix(self):
        result = clean_file_name("550e8400-e29b-41d4-a716-446655440000_550e8400-e29b-41d4-a716-446655440001_file.txt")
        assert result == "550e8400-e29b-41d4-a716-446655440001_file.txt"

    def test_strips_both_uuid_prefix_and_short_id_suffix(self):
        result = clean_file_name("550e8400-e29b-41d4-a716-446655440000_photo_Abc123XYZdef4567.jpg")
        assert result == "photo.jpg"

    def test_preserves_underscores_in_name(self):
        assert clean_file_name("my_cool_file.pdf") == "my_cool_file.pdf"

    def test_short_suffix_not_stripped_if_too_short(self):
        assert clean_file_name("report_abc.pdf") == "report_abc.pdf"

    def test_short_suffix_not_stripped_if_too_long(self):
        assert clean_file_name("report_Abc123XYZdef45678.pdf") == "report_Abc123XYZdef45678.pdf"

    def test_image_filename_with_suffix(self):
        assert clean_file_name("wallhaven-289e1g_B2p2jEVxhjrYZkvh.jpg") == "wallhaven-289e1g.jpg"

    def test_long_filename_with_hash_suffix(self):
        """Filenames like '2732x4096_50df03347243cf3f645f088f03bc546c.jpg' should keep the hash (32 chars, not 16)."""
        assert clean_file_name("2732x4096_50df03347243cf3f645f088f03bc546c.jpg") == "2732x4096_50df03347243cf3f645f088f03bc546c.jpg"
