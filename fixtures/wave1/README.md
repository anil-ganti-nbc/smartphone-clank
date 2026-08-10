# Wave 1 negative fixture corpus

These fixtures encode the August 2026 contamination incident (`docs/V038_PRODUCTION_REPORT_INVESTIGATION.md`)
as a permanent regression corpus, per the Wave 1 spec section 13/43.

`data/clank.db`'s `rejected_candidates` table is empty (the polluting collectors
predated that table, or the rows were deleted after the incident without being
preserved) — there is no raw historical DB dump of the 73 bad rows to replay.
Instead, this corpus was reconstructed two ways, both traceable:

1. **`*_invalid.json`** — representative bad strings in the same shape as the
   incident report's quoted example (`"PIXEL 11 SERIES AND RECEIVE AN EXCLUSIVE
   OFFER..."`) and the `ONEPLUSSHOP` example from
   `docs/V038_PRODUCTION_REPORT_INVESTIGATION.md`, each tagged with the
   rejection reason a strict validator must produce.
2. **`*_marketing_page.html`** — synthetic support/store pages built to match
   the real page shapes `collectors/generic_support.py::OEM_CONFIG[oem]["urls"]`
   targets, run through the *actual old regex patterns* in that file to confirm
   they really do extract garbage (see `tests/wave1/test_pollution_cannot_recur.py`
   which imports those patterns directly for the "what the old code did" half of
   the proof, then asserts the new validator rejects every one of the results).

Every string in `*_invalid.json` must classify as `INVALID` (or `AMBIGUOUS`,
never `VALID`) under the corresponding OEM's `collectors/wave1/<oem>/model_validator.py`.
