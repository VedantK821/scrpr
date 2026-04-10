import pytest
from app.services.contact_parser import parse_contact_value, extract_name


class TestParseContactValue:
    def test_full_contact_with_em_dash(self):
        result = parse_contact_value("Rajesh Kumar — VP HR — linkedin.com/in/rajesh")
        assert result["name"] == "Rajesh Kumar"
        assert result["title"] == "VP HR"
        assert result["linkedin_url"] == "linkedin.com/in/rajesh"

    def test_name_and_title_with_hyphen(self):
        result = parse_contact_value("Alice Smith - CTO")
        assert result["name"] == "Alice Smith"
        assert result["title"] == "CTO"
        assert "linkedin_url" not in result

    def test_name_only(self):
        result = parse_contact_value("Bob Jones")
        assert result["name"] == "Bob Jones"
        assert "title" not in result

    def test_with_pipe_delimiter(self):
        result = parse_contact_value("Alice Smith | CTO | linkedin.com/in/alice")
        assert result["name"] == "Alice Smith"
        assert result["title"] == "CTO"
        assert result["linkedin_url"] == "linkedin.com/in/alice"

    def test_empty_string(self):
        assert parse_contact_value("") == {}

    def test_none_returns_empty(self):
        assert parse_contact_value(None) == {}

    def test_linkedin_url_detection(self):
        result = parse_contact_value("Name — Title — https://linkedin.com/in/person")
        assert result["linkedin_url"] == "https://linkedin.com/in/person"

    def test_url_without_linkedin_not_tagged(self):
        result = parse_contact_value("Name — Title — example.com")
        assert "linkedin_url" not in result


class TestExtractName:
    def test_extracts_name_from_structured_value(self):
        assert extract_name("Rajesh Kumar — VP HR — linkedin.com/in/rajesh") == "Rajesh Kumar"

    def test_returns_plain_name_unchanged(self):
        assert extract_name("Alice Smith") == "Alice Smith"

    def test_extracts_from_hyphen_format(self):
        assert extract_name("Bob Jones - Manager") == "Bob Jones"

    def test_empty_returns_empty(self):
        assert extract_name("") == ""

    def test_none_returns_empty(self):
        assert extract_name(None) == ""
