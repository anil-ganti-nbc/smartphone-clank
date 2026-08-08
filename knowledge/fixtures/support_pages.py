"""
Synthetic support-page HTML fixtures for offline testing and demo.
These describe fictional future devices — not production truth.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Event 1 — brand new Samsung support page for SM-S957B
# ---------------------------------------------------------------------------
SAMSUNG_NEW_PAGE = """<!DOCTYPE html>
<html><head><title>Samsung Support - SM-S957B</title></head>
<body>
<div class="cookie-banner">Accept cookies</div>
<h1>Mobile Support</h1>
<p>Model number: SM-S957B</p>
<p>Find manuals and software for your device.</p>
<a href="/support/download/guide.pdf">Quick Start Guide</a>
<img src="/images/icon-download.png" alt="download icon">
<script>var analyticsId='xyz123';</script>
</body></html>
"""

# ---------------------------------------------------------------------------
# Event 2 — same page, analytics + whitespace only (FORMAT_ONLY)
# ---------------------------------------------------------------------------
SAMSUNG_FORMAT_ONLY = """<!DOCTYPE html>
<html><head><title>Samsung Support - SM-S957B</title></head>
<body>
<div class="cookie-banner">Accept cookies</div>
<h1>Mobile Support</h1>
<p>Model number: SM-S957B</p>
<p>Find manuals and software for your device.</p>
<a href="/support/download/guide.pdf">Quick Start Guide</a>
<img src="/images/icon-download.png" alt="download icon">
<script>var analyticsId='abc999CHANGED';</script>
</body></html>
"""

# ---------------------------------------------------------------------------
# Event 3 — English user manual added
# ---------------------------------------------------------------------------
SAMSUNG_MANUAL_ADDED = """<!DOCTYPE html>
<html><head><title>Samsung Support - SM-S957B</title></head>
<body>
<div class="cookie-banner">Accept cookies</div>
<h1>Mobile Support</h1>
<p>Model number: SM-S957B</p>
<p>Find manuals and software for your device.</p>
<a href="/support/download/guide.pdf">Quick Start Guide</a>
<a href="/support/download/SM-S957B_User_Manual_EN.pdf">User Manual EN v1.0</a>
<img src="/images/icon-download.png" alt="download icon">
<script>var analyticsId='abc999';</script>
</body></html>
"""

# ---------------------------------------------------------------------------
# Event 4 — regional variant mention + product images
# ---------------------------------------------------------------------------
SAMSUNG_VARIANT_AND_IMAGES = """<!DOCTYPE html>
<html><head><title>Samsung Support - SM-S957B</title></head>
<body>
<div class="cookie-banner">Accept cookies</div>
<h1>Mobile Support</h1>
<p>Model number: SM-S957B</p>
<p>Also available as SM-S957U (USA) and SM-S957N (Korea).</p>
<p>Find manuals and software for your device.</p>
<a href="/support/download/guide.pdf">Quick Start Guide</a>
<a href="/support/download/SM-S957B_User_Manual_EN.pdf">User Manual EN v1.0</a>
<img src="/images/icon-download.png" alt="download icon">
<img src="/images/product/sm-s957b-hero-front.png" alt="Galaxy device front product render">
<img src="/images/product/sm-s957b-hero-back.png" alt="Galaxy device back product render">
<img src="/images/product/sm-s957b-gallery-1.png" alt="official product gallery">
<script>var analyticsId='abc999';</script>
</body></html>
"""

# ---------------------------------------------------------------------------
# Event 5 — marketing name appears in title
# ---------------------------------------------------------------------------
SAMSUNG_MARKETING_NAME = """<!DOCTYPE html>
<html><head><title>Samsung Galaxy S27 Ultra Support - SM-S957B</title></head>
<body>
<div class="cookie-banner">Accept cookies</div>
<h1>Galaxy S27 Ultra Support</h1>
<p>Model number: SM-S957B</p>
<p>Also available as SM-S957U (USA) and SM-S957N (Korea).</p>
<p>Find manuals and software for your device.</p>
<a href="/support/download/guide.pdf">Quick Start Guide</a>
<a href="/support/download/SM-S957B_User_Manual_EN.pdf">User Manual EN v1.0</a>
<img src="/images/icon-download.png" alt="download icon">
<img src="/images/product/sm-s957b-hero-front.png" alt="Galaxy device front product render">
<img src="/images/product/sm-s957b-hero-back.png" alt="Galaxy device back product render">
<img src="/images/product/sm-s957b-gallery-1.png" alt="official product gallery">
<script>var analyticsId='abc999';</script>
</body></html>
"""

# ---------------------------------------------------------------------------
# Regional variant page (SM-S957U) — separate URL
# ---------------------------------------------------------------------------
SAMSUNG_US_VARIANT = """<!DOCTYPE html>
<html><head><title>Samsung Support - SM-S957U</title></head>
<body>
<h1>Mobile Support</h1>
<p>Model number: SM-S957U</p>
<p>US variant of Galaxy S series device.</p>
<a href="/support/download/SM-S957U_User_Manual_EN.pdf">User Manual EN</a>
</body></html>
"""

URL_MAIN = "https://www.samsung.com/support/model/SM-S957B/"
URL_US = "https://www.samsung.com/us/support/model/SM-S957U/"
