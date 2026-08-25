"""Samsung US Owners product-page collector — SOAK / EXPERIMENTAL.

source_id ``samsung_us_owners_product``. Declared LIVE_VALIDATED in
config/samsung_sources.yaml (seed paths validated live 2026-08-02) but it
has no production promotion record, so it is deliberately absent from
``RUNNABLE_SAMSUNG_SOURCE_IDS``: production scheduling can never execute
it. It runs only where soak execution is explicitly enabled
(``build_collectors(..., include_soak=True)``, wired for staging
environments in runtime/run_once.py).

Signal rationale (Class A OEM surface): owner/product support pages are
published per-model and frequently appear BEFORE marketing/catalogue
surfaces for unannounced models, with static HTML containing SM- model
codes — genuinely distinct pre-announcement signal from the support
sitemap collector.

Notification authority: ``alerts/source_maturity.py`` classifies this
source as soak (fail-closed default), so even if its discoveries were
processed against a production database with a configured webhook, the
newsroom gate suppresses every send and records the suppressed delivery
row as evidence.
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
