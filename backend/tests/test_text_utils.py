import pytest

from app.text_utils import truncate


def test_fits_unchanged():
    assert truncate("hello", 5) == "hello"
    assert truncate("", 3) == ""


def test_cut_adds_ellipsis_within_limit():
    out = truncate("abcdefghij", 5)
    assert out == "abcd…"
    assert len(out) == 5


def test_trailing_space_before_ellipsis_is_trimmed():
    assert truncate("hello world", 7) == "hello…"


@pytest.mark.parametrize("limit", [1, 2, 10, 79, 80, 200])
def test_never_exceeds_limit(limit):
    assert len(truncate("x" * 500, limit)) <= limit


def test_nonpositive_limit():
    assert truncate("abc", 0) == ""
    assert truncate("abc", -1) == ""
