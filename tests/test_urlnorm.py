import pytest

from reelvault.urlnorm import extract_url, instagram_shortcode, is_safe_url, normalize_url


@pytest.mark.parametrize("raw, expected", [
    ("https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=abc123", "https://instagram.com/reel/C1a2B3c4D5e"),
    ("https://instagram.com/reels/C1a2B3c4D5e", "https://instagram.com/reel/C1a2B3c4D5e"),
    ("http://www.instagram.com/reel/C1a2B3c4D5e/?utm_source=ig_web_copy_link", "https://instagram.com/reel/C1a2B3c4D5e"),
    ("https://www.instagram.com/p/C1a2B3c4D5e/", "https://instagram.com/p/C1a2B3c4D5e"),
    ("https://www.instagram.com/someuser/reel/C1a2B3c4D5e/", "https://instagram.com/reel/C1a2B3c4D5e"),
    ("https://youtu.be/dQw4w9WgXcQ?si=xyz", "https://youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/abcDEF123", "https://youtube.com/shorts/abcDEF123"),
    ("https://Example.com/path/?b=2&a=1&utm_medium=x", "https://example.com/path?a=1&b=2"),
])
def test_normalize(raw, expected):
    assert normalize_url(raw) == expected


def test_extract_url_from_share_text():
    text = "Check out this reel by @someone https://www.instagram.com/reel/XyZ/?igsh=1 on Instagram."
    assert extract_url(text) == "https://www.instagram.com/reel/XyZ/?igsh=1"
    assert extract_url("no link here") is None
    assert extract_url(None) is None


def test_safe_url():
    assert is_safe_url("https://instagram.com/reel/abc")
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("https://" + "a" * 3000)


def test_shortcode():
    assert instagram_shortcode("https://www.instagram.com/reel/ABC_-1/") == "ABC_-1"
    assert instagram_shortcode("https://youtube.com/watch?v=1") is None
