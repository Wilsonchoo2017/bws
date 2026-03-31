"""GWT tests for pure enrichment helper functions -- no mocks needed."""

from api.workers.enrichment import _parse_job_url, _error_result


class TestParseJobUrl:
    """Given enrichment job URLs, verify pure parsing logic."""

    def test_given_bare_set_number_when_parsed_then_source_is_none(self):
        """Given '75192', when parsed, then returns ('75192', None)."""
        assert _parse_job_url("75192") == ("75192", None)

    def test_given_set_with_source_when_parsed_then_both_returned(self):
        """Given '75192:bricklink', when parsed, then returns ('75192', 'bricklink')."""
        assert _parse_job_url("75192:bricklink") == ("75192", "bricklink")

    def test_given_set_with_unknown_source_when_parsed_then_string_preserved(self):
        """Given '75192:xyz', when parsed, then source string is 'xyz'."""
        assert _parse_job_url("75192:xyz") == ("75192", "xyz")


class TestErrorResult:
    """Given error conditions, verify pure error result builder."""

    def test_given_error_when_built_then_fields_are_zero(self):
        """Given an error message, when built, then fields_found and fields_total are 0."""
        result = _error_result("75192", "Item not found")

        assert result["set_number"] == "75192"
        assert result["fields_found"] == 0
        assert result["fields_total"] == 0
        assert result["error"] == "Item not found"
        assert result["field_details"] == []
