import pytest

from natural_tts.segments import Kind, Segment


class TestSegment:
    def test_defaults_are_plain_prose(self):
        segment = Segment("Hello.")
        assert segment.kind is Kind.PROSE
        assert segment.pause_before == 0.0
        assert segment.rate == 1.0
        assert segment.voice is None

    def test_is_immutable(self):
        with pytest.raises(AttributeError):
            Segment("x").text = "y"  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"text": ""}, "text must not be blank"),
            ({"text": "  "}, "text must not be blank"),
            ({"text": "x", "pause_before": -0.1}, "pause_before must be >= 0"),
            ({"text": "x", "rate": 0}, "rate must be > 0"),
        ],
    )
    def test_rejects_invalid_values(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            Segment(**kwargs)

    def test_every_reader_kind_exists(self):
        assert {k.name for k in Kind} == {
            "PROSE",
            "HEADING",
            "LIST_ITEM",
            "QUOTE",
            "CODE",
            "MATH",
            "TABLE",
        }
