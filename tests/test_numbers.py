import pytest

from autodialer.numbers import InvalidNumber, normalise_display, numbers_match, to_dial_sequence


@pytest.mark.parametrize("raw,seq", [
    ("+91 98765-43210", "+919876543210"),
    ("(555) 123.4567", "5551234567"),
    ("*123#", "*123#"),
])
def test_to_dial_sequence(raw, seq):
    assert to_dial_sequence(raw) == seq


@pytest.mark.parametrize("raw", ["", "  ", "12a45", "12+34", "+", "1" * 21, None])
def test_invalid(raw):
    with pytest.raises(InvalidNumber):
        to_dial_sequence(raw)


def test_display_normalisation():
    assert normalise_display("‪+91 98765 43210‬") == "+919876543210"
    assert numbers_match("5551234567", "(555) 123-4567")
    assert not numbers_match("5551234567", "(555) 123-456")
    assert not numbers_match("5551234567", None)
