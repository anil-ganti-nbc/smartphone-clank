"""Source maturity registry — evidence-bearing notification authority.

Campaign rule: every NEW collector begins in soak maturity. During soak,
collection/persistence/diffing run normally but Discord newsroom
notification is SUPPRESSED BY POLICY — not merely by leaving webhook
credentials unset. Environment and source maturity are independent: a
soak source may run on production infrastructure against the production
database and still never reach a production channel.

Policy is fail-closed: a source id that is not explicitly listed here is
treated as soak. Promotion to `production` requires an explicit,
reviewed edit to this module (Fleet Law 8: promotion gates) — never a
config-only flip.

Every suppression decision flows through
`alerts/discord.DiscordAlerter._send`, which records a `WebhookDelivery`
row with ``suppressed=1`` so the evidence trail shows exactly why
nothing was sent.
"""

from __future__ import annotations

MATURITY_PRODUCTION = "production"
MATURITY_SOAK = "soak"

# Sources whose promotion record exists and which are currently enabled in
# production scheduling (systemd timers per deploy/systemd/ + Samsung cron).
# samsung_support / samsung_firmware / *_ota legacy collectors are disabled
# by config and therefore intentionally absent: if one is ever re-enabled it
# re-enters soak by default.
PRODUCTION_SOURCES = frozenset({
    # legacy registry
    "samsung_us_support_sitemap",
    # wave 1 adapters
    "google_store_category_phones",
    "nothing_products_sitemap",
    "oneplus_regional_sitemap",
    # wave 2 adapters
    "motorola_regional_sitemap",
    "honor_global_sitemap",
    "oppo_global_sitemap",
    "realme_regional_sitemap",
})


def source_maturity(source_id: str | None) -> str:
    """Fail-closed: unknown/absent source ids are soak by definition."""
    if source_id and source_id in PRODUCTION_SOURCES:
        return MATURITY_PRODUCTION
    return MATURITY_SOAK


def notifications_allowed(source_id: str | None) -> bool:
    """True only when the source holds production notification authority."""
    return source_maturity(source_id) == MATURITY_PRODUCTION
