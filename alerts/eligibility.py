"""
Eligibility rules for the Discord test transport.

Pure functions, no I/O. A `reason` is a short tag describing *why* a caller
wants to send an alert. Unknown reasons are ineligible (fail closed) so a
typo never accidentally starts flooding a channel.
"""

from __future__ import annotations

NEWSROOM_ELIGIBLE_REASONS = {
    "new_sitemap_url",
    "new_model",
    "marketing_name_revealed",
    "manual_added",
    "firmware_added",
    "support_page_change",
    "new_regional_variant",
    "official_status_change",
}

NEWSROOM_SUPPRESSED_REASONS = {
    "baseline_import",
    "initial_backfill",
    "unchanged_resighting",
    "health_check",
    "cleanup",
    "quarantine",
    "fixture",
    "demo",
}

MAINTENANCE_ELIGIBLE_REASONS = {
    "out_of_scope_collector",
    "config_drift",
    "parser_collapse",
    "parser_empty_streak",
    "collector_failure_streak",
    "scheduler_stall",
    "db_integrity_failure",
    "migration_failure",
    "webhook_delivery_failure",
    "invalid_soak_state",
    "health_score_critical",
}


def newsroom_eligible(reason: str, *, backfill: bool = False, test_mode: bool = False) -> bool:
    """Should a newsroom alert fire for this reason?

    `backfill` marks a run that's populating history (baseline catalog
    import, initial backfill) rather than discovering something new.
    `test_mode` marks a synthetic diagnostic send — those go through
    WebhookTransport directly and never call this function with real intent,
    so if test_mode is set here it's being asked about non-test content and
    must be suppressed.
    """
    if backfill or test_mode:
        return False
    if reason in NEWSROOM_SUPPRESSED_REASONS:
        return False
    return reason in NEWSROOM_ELIGIBLE_REASONS


def maintenance_eligible(reason: str) -> bool:
    """Should a maintenance alert fire for this reason?"""
    return reason in MAINTENANCE_ELIGIBLE_REASONS
