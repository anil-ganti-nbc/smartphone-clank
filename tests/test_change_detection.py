"""Content hash / change detection tests."""

from knowledge.change_detection import extract_hashes, compare_hashes, ContentHashes


HTML_A = """
<html><body>
<h1>Support</h1>
<p>Model SM-S957B</p>
<a href="/download/firmware.zip">Download firmware</a>
<img src="/img/phone.png">
</body></html>
"""

HTML_B_FORMAT_ONLY = """
<html><body>
<h1>Support</h1>
<p>Model SM-S957B</p>
<a href="/download/firmware.zip">Download firmware</a>
<img src="/img/phone.png">
<!-- comment added -->
</body></html>
"""

HTML_C_NEW_DOWNLOAD = """
<html><body>
<h1>Support</h1>
<p>Model SM-S957B</p>
<a href="/download/firmware.zip">Download firmware</a>
<a href="/download/new_ota.zip">New OTA</a>
<img src="/img/phone.png">
</body></html>
"""


def test_extract_hashes():
    h = extract_hashes(HTML_A)
    assert h.content_hash
    assert h.text_hash
    assert h.download_hash
    assert h.image_hash
    print("extract ok")


def test_format_change_not_meaningful():
    a = extract_hashes(HTML_A)
    b = extract_hashes(HTML_B_FORMAT_ONLY)
    result = compare_hashes(a, b)
    # content may change due to comment, but text/download/image should be stable
    assert result.summary["text_changed"] is False
    assert result.meaningful is False
    print("format-only not meaningful ok")


def test_download_change_is_meaningful():
    a = extract_hashes(HTML_A)
    c = extract_hashes(HTML_C_NEW_DOWNLOAD)
    result = compare_hashes(a, c)
    assert result.summary["download_changed"] is True
    assert result.meaningful is True
    print("download change meaningful ok")


if __name__ == "__main__":
    test_extract_hashes()
    test_format_change_not_meaningful()
    test_download_change_is_meaningful()
    print("all change detection tests passed")
