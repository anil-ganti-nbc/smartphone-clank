"""Samsung US Owners product-page collector — CANARY (promoted from SOAK 2026-08-30).

source_id ``samsung_us_owners_product``. Declared LIVE_VALIDATED in
config/samsung_sources.yaml (seed paths validated live 2026-08-02). SOAK
history: implemented 2026-08-25, staging baseline 2026-08-26 03:48Z, then 32
clean repeat cycles (zero new devices, zero failures) — promoted to CANARY
per docs/infra/SAMSUNG_US_OWNERS_PRODUCT_CANARY_REPORT.md.

CANARY semantics (docs/ENGINEERING_PRINCIPLES.md Rule 7 lifecycle: STAGING →
BASELINE → REPEATABILITY → CANARY → PRODUCTION): the collector now runs in
real production execution — registered via
``collectors.CANARY_SAMSUNG_SOURCE_IDS`` (a reviewed code gate, Fleet Law 8),
``RUNNABLE_SAMSUNG_SOURCE_IDS``, and the production per-source timer
``smartphone-clank-source@samsung_us_owners_product.timer`` — against the
production config/DB. It does NOT hold production notification authority:
``alerts/source_maturity.py`` still classifies it soak (fail-closed; only an
explicit, reviewed edit there grants authority), so every newsroom decision
is suppressed with a persisted ``WebhookDelivery`` evidence row. Canary is
not production.

Signal rationale (Class A OEM surface): owner/product support pages are
published per-model and frequently appear BEFORE marketing/catalogue
surfaces for unannounced models, with static HTML containing SM- model
codes — genuinely distinct pre-announcement signal from the support
sitemap collector.
"""

from __future__ import annotations

import logging

from collectors.base import BaseCollector
from collectors.samsung import SamsungModelValidator
from models.schemas import Discovery, Manufacturer, SourceType

logger = logging.getLogger("clank.collectors.samsung_owners")

# Model matching is delegated to the canonical Samsung identifier parser
# (collectors/samsung/model_validator.py). That module's ``find_re`` accepts
# ``SM-[A-Z0-9]{3,16}`` (case-insensitive) and is the shared rule already used
# by Samsung support/sitemap discovery, so the owners collector must not
# maintain a competing regex (a previous ``{4,10}`` cap silently dropped
# current 11-character suffixes such as ``SM-S928ULBEXAA``).
# Owner-page slugs look like "galaxy-s24-ultra"; anything without a model
# hint is still fetched (Samsung may publish an owners page pre-announcement)
# but the slug is kept in raw evidence for provenance.


class SamsungOwnersCollector(BaseCollector):
    name = "samsung_us_owners_product"
    source_type = SourceType.SUPPORT_PAGE
    maturity = "soak"

    BASE_URL = "https://www.samsung.com/us/support/owners/product/"
    # Seed slugs validated live 2026-08-02 (config/samsung_sources.yaml).
    SEED_PATHS = (
        "galaxy-s24-ultra",
        "galaxy-s24",
        "galaxy-s24-plus",
        "galaxy-z-fold6",
        "galaxy-z-flip6",
        "galaxy-a55-5g",
        "galaxy-a35-5g",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validator = SamsungModelValidator()

    def collect(self) -> list[Discovery]:
        discoveries: list[Discovery] = []
        seen_models: set[str] = set()
        failures = 0

        for slug in self.SEED_PATHS:
            url = f"{self.BASE_URL}{slug}"
            try:
                resp = self.fetch(url)
                hash_ = self.content_hash(resp.text)
            except Exception as exc:  # noqa: BLE001 — one page failing must not kill the crawl
                failures += 1
                logger.warning("[%s] fetch failed for %s: %s", self.name, url, exc)
                continue

            text = resp.text
            # Canonical shared matcher: upper-cases and de-duplicates within a
            # page. Cross-page de-duplication is handled by ``seen_models``.
            matches = self._validator.find_candidates(text)
            page_models = []
            for model in matches:
                if model in seen_models:
                    continue
                seen_models.add(model)
                page_models.append(model)
                discoveries.append(
                    Discovery(
                        manufacturer=Manufacturer.SAMSUNG,
                        model_number=model,
                        source=self.name,
                        source_type=self.source_type,
                        url=url,
                        content_hash=hash_,
                        raw={"page": url, "slug": slug, "matched": model},
                    )
                )
            if not page_models:
                logger.info("[%s] %s -> 0 new SM- codes", self.name, url)

        if failures == len(self.SEED_PATHS):
            # Every page failed: this is a source failure, not a quiet zero.
            raise RuntimeError(
                f"all {len(self.SEED_PATHS)} owners pages failed to fetch "
                "(transport-level source failure)"
            )
        return discoveries
