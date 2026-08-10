"""Content hash / change detection tests."""

from knowledge.change_detection import extract_fingerprint, compare_fingerprints


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


def test_extract_fingerprint():
    fp = extract_fingerprint(HTML_A)
    assert fp.hashes.content_hash
    assert fp.hashes.text_hash
    assert fp.hashes.download_hash
    assert fp.hashes.image_hash
    print("extract ok")


def test_format_change_not_meaningful():
    a = extract_fingerprint(HTML_A)
    b = extract_fingerprint(HTML_B_FORMAT_ONLY)
    result = compare_fingerprints(a, b)
    assert "TEXT_CHANGED" not in result.classifications
    assert result.meaningful is False
    print("format-only not meaningful ok")


def test_download_change_is_meaningful():
    a = extract_fingerprint(HTML_A)
    c = extract_fingerprint(HTML_C_NEW_DOWNLOAD)
    result = compare_fingerprints(a, c)
    assert "DOWNLOAD_ADDED" in result.classifications
    assert result.meaningful is True
    print("download change meaningful ok")


if __name__ == "__main__":
    test_extract_fingerprint()
    test_format_change_not_meaningful()
    test_download_change_is_meaningful()
    print("all change detection tests passed")
