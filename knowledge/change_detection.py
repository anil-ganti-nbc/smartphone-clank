"""
Multi-hash content change detection + deterministic classifier.

Support pages produce fingerprints; the classifier explains what changed
and whether it is meaningful for device intelligence.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from selectolax.parser import HTMLParser

logger = logging.getLogger("clank.change_detection")


# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------

@dataclass
class ContentHashes:
    content_hash: str                          # raw HTML (after optional normalize)
    text_hash: Optional[str] = None
    dom_hash: Optional[str] = None
    download_hash: Optional[str] = None
    image_hash: Optional[str] = None
    title_hash: Optional[str] = None


@dataclass
class AssetRef:
    """Downloadable asset or image reference extracted from a page."""
    kind: str                                  # download | image
    url: str
    normalized_url: str
    title: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
    alt: Optional[str] = None
    category: Optional[str] = None             # user_manual | firmware | regulatory | product_render | logo | icon | decorative | generic
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageFingerprint:
    hashes: ContentHashes
    title: Optional[str] = None
    downloads: list[AssetRef] = field(default_factory=list)
    images: list[AssetRef] = field(default_factory=list)
    model_references: list[str] = field(default_factory=list)
    visible_text: Optional[str] = None
    content_length: int = 0


@dataclass
class ChangeResult:
    classifications: list[str]
    meaningful: bool
    details: dict[str, Any]
    hashes: ContentHashes
    fingerprint: Optional[PageFingerprint] = None


def _sha(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Normalization (collector-supplied rules, not manufacturer hardcodes in engine)
# ---------------------------------------------------------------------------

DEFAULT_STRIP_QUERY = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "_ga", "sessionid",
    "sid", "token", "csrf", "csrf_token",
}

DEFAULT_IGNORE_SELECTORS = [
    ".cookie-banner", ".cookie-notice", "#cookie-consent",
    ".recommended-products", ".recommendations",
    ".chat-widget", ".support-chat", ".live-chat",
    ".analytics", "script", "style", "noscript",
]


def normalize_url(url: str, strip_params: set[str] | None = None) -> str:
    strip = strip_params or DEFAULT_STRIP_QUERY
    try:
        parsed = urlparse(url)
        q = parse_qs(parsed.query, keep_blank_values=False)
        cleaned = {k: v for k, v in q.items() if k.lower() not in strip}
        new_query = urlencode(cleaned, doseq=True)
        # drop fragment
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
    except Exception:
        return url


def normalize_html(
    html: str,
    ignore_selectors: list[str] | None = None,
    strip_query_params: set[str] | None = None,
) -> str:
    """
    Strip noisy dynamic content before hashing.
    Collectors may pass manufacturer-specific selectors via config.
    """
    selectors = ignore_selectors or DEFAULT_IGNORE_SELECTORS
    try:
        tree = HTMLParser(html)
        for sel in selectors:
            for node in tree.css(sel):
                node.decompose()
        # strip common tracking attributes
        for node in tree.css("[id], [class]"):
            # do not remove nodes; only clean highly volatile id patterns later if needed
            pass
        body = tree.body.html if tree.body else tree.html
        text = body or html
        # collapse whitespace for stability
        text = re.sub(r"\s+", " ", text)
        return text
    except Exception:
        return re.sub(r"\s+", " ", html)


# ---------------------------------------------------------------------------
# Asset classification heuristics (deterministic, no CV)
# ---------------------------------------------------------------------------

MANUAL_HINTS = ("manual", "user guide", "userguide", "user_manual", "handbook", "quick start")
FIRMWARE_HINTS = ("firmware", "ota", "rom", "software update", "sw update", ".zip", ".tar")
REGULATORY_HINTS = ("regulatory", "compliance", "sar", "fcc", "declaration", "safety")
PRODUCT_RENDER_HINTS = ("product", "device", "phone", "render", "hero", "gallery", "official")
LOGO_HINTS = ("logo", "brand", "wordmark")
ICON_HINTS = ("icon", "sprite", "favicon", "arrow", "chevron", "social")


def classify_download(title: str, url: str, filename: str | None = None) -> str:
    blob = f"{title or ''} {url or ''} {filename or ''}".lower()
    if any(h in blob for h in FIRMWARE_HINTS):
        return "firmware"
    if any(h in blob for h in MANUAL_HINTS):
        return "user_manual"
    if any(h in blob for h in REGULATORY_HINTS):
        return "regulatory_document"
    if filename and filename.lower().endswith((".pdf", ".doc", ".docx")):
        return "generic_document"
    return "generic_document"


def classify_image(alt: str | None, url: str, filename: str | None = None) -> str:
    blob = f"{alt or ''} {url or ''} {filename or ''}".lower()
    if any(h in blob for h in LOGO_HINTS):
        return "logo"
    if any(h in blob for h in ICON_HINTS):
        return "icon"
    if any(h in blob for h in PRODUCT_RENDER_HINTS):
        return "product_render"
    # size hints in filename
    if filename and any(x in filename.lower() for x in ("thumb", "icon", "sprite", "1x1", "pixel")):
        return "decorative"
    if filename and any(x in filename.lower() for x in ("hero", "product", "device", "phone", "gallery")):
        return "product_render"
    return "decorative"


def _filename_from_url(url: str) -> Optional[str]:
    try:
        path = urlparse(url).path
        name = path.rstrip("/").split("/")[-1]
        return name or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fingerprint extraction
# ---------------------------------------------------------------------------

MODEL_PATTERNS = [
    re.compile(r"\b(SM-[A-Z0-9]{4,10})\b", re.I),
    re.compile(r"\b(CPH\d{4})\b", re.I),
    re.compile(r"\b(G[A-Z0-9]{6,12})\b", re.I),
    re.compile(r"\b(A0\d{2}|A1\d{2})\b", re.I),
    re.compile(r"\b(Pixel\s?(?:[0-9]+|a|Pro|Fold)[a-zA-Z0-9\s]*)\b", re.I),
]


def extract_fingerprint(
    html: str,
    *,
    normalize: bool = True,
    ignore_selectors: list[str] | None = None,
    strip_query_params: set[str] | None = None,
    model_patterns: list[re.Pattern] | None = None,
) -> PageFingerprint:
    strip = strip_query_params or DEFAULT_STRIP_QUERY
    work_html = normalize_html(html, ignore_selectors, strip) if normalize else html
    content_hash = _sha(work_html)
    content_length = len(html)

    title = None
    text_hash = None
    dom_hash = None
    download_hash = None
    image_hash = None
    title_hash = None
    visible_text = None
    downloads: list[AssetRef] = []
    images: list[AssetRef] = []
    models: list[str] = []

    try:
        # Prefer normalized HTML for text/DOM so ignored selectors (scripts, cookies)
        # do not create false TEXT_CHANGED / DOM_CHANGED signals.
        tree = HTMLParser(work_html if normalize else html)
        # title still from original when possible
        orig_tree = HTMLParser(html)
        tnode = orig_tree.css_first("title")
        if tnode:
            title = (tnode.text() or "").strip()
            title_hash = _sha(title) if title else None

        # visible text
        if tree.body:
            visible_text = tree.body.text(separator="\n", strip=True)
            visible_text = re.sub(r"[ \t]+", " ", visible_text)
            visible_text = re.sub(r"\n{3,}", "\n\n", visible_text).strip()
            text_hash = _sha(re.sub(r"\s+", " ", visible_text))

        # DOM structure
        tags = [n.tag for n in tree.css("h1, h2, h3, a, img, table, ul, ol, section, article")]
        dom_hash = _sha("|".join(tags[:500])) if tags else None

        # downloads
        seen_dl = set()
        for a in tree.css("a"):
            href = a.attributes.get("href") or ""
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            text = (a.text() or "").strip()
            href_l = href.lower()
            text_l = text.lower()
            if any(k in href_l or k in text_l for k in (
                "download", "firmware", "ota", ".zip", ".pdf", ".doc", "manual", "rom", "guide"
            )):
                nurl = normalize_url(href, strip)
                if nurl in seen_dl:
                    continue
                seen_dl.add(nurl)
                fname = _filename_from_url(href)
                cat = classify_download(text, href, fname)
                downloads.append(AssetRef(
                    kind="download",
                    url=href,
                    normalized_url=nurl,
                    title=text or fname,
                    filename=fname,
                    file_type=(fname.rsplit(".", 1)[-1].lower() if fname and "." in fname else None),
                    category=cat,
                ))
        if downloads:
            download_hash = _sha("\n".join(sorted(d.normalized_url for d in downloads)))

        # images
        seen_img = set()
        for img in tree.css("img"):
            src = img.attributes.get("src") or img.attributes.get("data-src") or ""
            if not src or src.startswith("data:"):
                continue
            nurl = normalize_url(src.split("?")[0], strip)
            if nurl in seen_img:
                continue
            seen_img.add(nurl)
            alt = img.attributes.get("alt")
            fname = _filename_from_url(src)
            cat = classify_image(alt, src, fname)
            images.append(AssetRef(
                kind="image",
                url=src,
                normalized_url=nurl,
                title=alt,
                filename=fname,
                alt=alt,
                category=cat,
            ))
        if images:
            image_hash = _sha("\n".join(sorted(i.normalized_url for i in images)))

        # model references
        blob = (title or "") + "\n" + (visible_text or "")
        patterns = model_patterns or MODEL_PATTERNS
        found = set()
        for pat in patterns:
            for m in pat.findall(blob):
                found.add(m.strip())
        models = sorted(found)

    except Exception as e:
        logger.debug(f"fingerprint extraction partial failure: {e}")

    return PageFingerprint(
        hashes=ContentHashes(
            content_hash=content_hash,
            text_hash=text_hash,
            dom_hash=dom_hash,
            download_hash=download_hash,
            image_hash=image_hash,
            title_hash=title_hash,
        ),
        title=title,
        downloads=downloads,
        images=images,
        model_references=models,
        visible_text=visible_text,
        content_length=content_length,
    )


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def compare_fingerprints(
    old: Optional[PageFingerprint],
    new: PageFingerprint,
    *,
    status_code: Optional[int] = None,
    previous_status: Optional[int] = None,
) -> ChangeResult:
    """
    Deterministic classification of what changed between two fingerprints.
    """
    classifications: list[str] = []
    details: dict[str, Any] = {
        "new_downloads": [],
        "removed_downloads": [],
        "new_images": [],
        "removed_images": [],
        "text_summary": {},
        "title": {},
        "models": {},
    }

    # HTTP-level
    if status_code and status_code >= 500:
        return ChangeResult(
            classifications=["FETCH_ERROR"],
            meaningful=False,
            details={"status_code": status_code},
            hashes=new.hashes,
            fingerprint=new,
        )

    if status_code in (404, 410):
        # caller decides PAGE_REMOVED after threshold; here we only signal
        return ChangeResult(
            classifications=["FETCH_ERROR"],  # may be upgraded by monitor
            meaningful=False,
            details={"status_code": status_code, "hint": "not_found"},
            hashes=new.hashes,
            fingerprint=new,
        )

    if old is None:
        classifications.append("NEW_PAGE")
        details["new_downloads"] = [
            {"title": d.title, "url": d.url, "category": d.category} for d in new.downloads
        ]
        details["new_images"] = [
            {"alt": i.alt, "url": i.url, "category": i.category} for i in new.images
            if i.category == "product_render"
        ]
        details["models"] = {"added": new.model_references}
        if new.title:
            details["title"] = {"new": new.title}
        return ChangeResult(
            classifications=classifications,
            meaningful=True,
            details=details,
            hashes=new.hashes,
            fingerprint=new,
        )

    # Title
    if (old.title or "") != (new.title or ""):
        classifications.append("TITLE_CHANGED")
        details["title"] = {"old": old.title, "new": new.title}

    # Models
    old_models = set(old.model_references)
    new_models = set(new.model_references)
    added_models = sorted(new_models - old_models)
    removed_models = sorted(old_models - new_models)
    if added_models:
        classifications.append("MODEL_REFERENCE_ADDED")
        details["models"]["added"] = added_models
    if removed_models:
        classifications.append("MODEL_REFERENCE_REMOVED")
        details["models"]["removed"] = removed_models

    # Downloads
    old_dl = {d.normalized_url: d for d in old.downloads}
    new_dl = {d.normalized_url: d for d in new.downloads}
    for url, d in new_dl.items():
        if url not in old_dl:
            classifications.append("DOWNLOAD_ADDED")
            details["new_downloads"].append(
                {"title": d.title, "url": d.url, "category": d.category, "filename": d.filename}
            )
    for url, d in old_dl.items():
        if url not in new_dl:
            classifications.append("DOWNLOAD_REMOVED")
            details["removed_downloads"].append(
                {"title": d.title, "url": d.url, "category": d.category}
            )
    # changed = same url different title? treat as DOWNLOAD_CHANGED
    for url in set(old_dl) & set(new_dl):
        if (old_dl[url].title or "") != (new_dl[url].title or ""):
            if "DOWNLOAD_CHANGED" not in classifications:
                classifications.append("DOWNLOAD_CHANGED")

    # Images (product renders matter most)
    old_img = {i.normalized_url: i for i in old.images}
    new_img = {i.normalized_url: i for i in new.images}
    for url, i in new_img.items():
        if url not in old_img:
            classifications.append("IMAGE_ADDED")
            details["new_images"].append(
                {"alt": i.alt, "url": i.url, "category": i.category}
            )
    for url, i in old_img.items():
        if url not in new_img:
            classifications.append("IMAGE_REMOVED")
            details["removed_images"].append(
                {"alt": i.alt, "url": i.url, "category": i.category}
            )

    # Text / DOM
    text_changed = bool(old.hashes.text_hash and new.hashes.text_hash and old.hashes.text_hash != new.hashes.text_hash)
    dom_changed = bool(old.hashes.dom_hash and new.hashes.dom_hash and old.hashes.dom_hash != new.hashes.dom_hash)
    content_changed = old.hashes.content_hash != new.hashes.content_hash

    if text_changed:
        classifications.append("TEXT_CHANGED")
        # rough line diff counts
        old_lines = set((old.visible_text or "").splitlines())
        new_lines = set((new.visible_text or "").splitlines())
        details["text_summary"] = {
            "added_lines": len(new_lines - old_lines),
            "removed_lines": len(old_lines - new_lines),
        }
    if dom_changed and not text_changed:
        classifications.append("DOM_CHANGED")

    # Deduplicate classification list while preserving order
    seen = set()
    uniq = []
    for c in classifications:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    classifications = uniq

    if not classifications:
        if content_changed:
            classifications = ["FORMAT_ONLY"]
        else:
            classifications = ["NO_CHANGE"]

    meaningful = _is_meaningful(classifications, details)
    return ChangeResult(
        classifications=classifications,
        meaningful=meaningful,
        details=details,
        hashes=new.hashes,
        fingerprint=new,
    )


def _is_meaningful(classifications: list[str], details: dict) -> bool:
    # Strong signals always meaningful
    strong = {
        "NEW_PAGE",
        "DOWNLOAD_ADDED",
        "DOWNLOAD_REMOVED",
        "DOWNLOAD_CHANGED",
        "MODEL_REFERENCE_ADDED",
        "TITLE_CHANGED",
        "PAGE_RESTORED",
    }
    if any(c in strong for c in classifications):
        return True
    # TEXT_CHANGED only if substantial line delta (filters analytics noise)
    if "TEXT_CHANGED" in classifications:
        summary = details.get("text_summary") or {}
        added = int(summary.get("added_lines") or 0)
        removed = int(summary.get("removed_lines") or 0)
        if added + removed >= 3:
            return True
    # product renders only
    if "IMAGE_ADDED" in classifications:
        for img in details.get("new_images", []):
            if img.get("category") == "product_render":
                return True
    return False


# Weights for evidence integration
DEFAULT_SUPPORT_CHANGE_WEIGHTS = {
    "new_page": 10,
    "model_reference_added": 8,
    "download_added": {
        "user_manual": 18,
        "firmware": 20,
        "regulatory_document": 15,
        "generic_document": 3,
    },
    "product_image_added": 10,
    "title_changed": 3,
    "page_restored": 2,
}


def score_change(result: ChangeResult, weights: dict | None = None) -> int:
    """Compute confidence contribution from a classified change."""
    w = weights or DEFAULT_SUPPORT_CHANGE_WEIGHTS
    total = 0
    cls = set(result.classifications)
    if "NEW_PAGE" in cls:
        total += int(w.get("new_page", 10))
    if "MODEL_REFERENCE_ADDED" in cls:
        total += int(w.get("model_reference_added", 8))
    if "TITLE_CHANGED" in cls:
        total += int(w.get("title_changed", 3))
    if "PAGE_RESTORED" in cls:
        total += int(w.get("page_restored", 2))
    dl_weights = w.get("download_added", {})
    if isinstance(dl_weights, dict):
        for d in result.details.get("new_downloads", []):
            cat = d.get("category") or "generic_document"
            total += int(dl_weights.get(cat, 3))
    for img in result.details.get("new_images", []):
        if img.get("category") == "product_render":
            total += int(w.get("product_image_added", 10))
    return total
