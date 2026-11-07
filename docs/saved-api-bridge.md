# Saved API history bridge repair — November 2, 2026

One unfinished native request could previously stop both saved-response cursors
at its preceding ID. Later completed replies then remained outside the indexed
sales-intelligence metadata, even though they were already saved locally.

`sync_raw_catalog` now records unfinished IDs in separate durable control queues
for `raw_cursor` and `raw_history_cursor`. Each normal pass advances through up
to 100 new request rows and retries up to 25 queued IDs through primary-key reads.
Unfinished retries rotate to the queue's end, allowing later completions and new
rows to progress. The default forward limit remains 25; collection schedules,
API calls, source scopes and provider quotas do not change.

The pending queue has a 1,000-ID bound. If it is full, the forward cursor stops
before an additional unfinished ID rather than losing its retry identity. The
result reports `pending_capacity`. At the current journal maximum, unresolved
IDs instead report `waiting_on_saved_responses`; they are not called complete
or assigned a product value. Missing source rows remain pending and explicit
failed requests contribute no product observation.

Metadata, cursor advancement and the pending queue commit in the same archive
transaction. A failed archive write rolls all three back. The native journal is
opened read-only; this bridge never changes an unfinished native request's
status or deletes its evidence. Duplicate successful replies remain idempotent.
No database schema migration or cursor reset is required.

Late completions use the saved `quota_json.captured_at` response timestamp for
both capture and availability. A queued response without that timestamp remains
unknown and pending, rather than being backdated to its original attempt. For
already completed, unqueued historical replies, the existing attempted-time
fallback remains compatible; it does not establish an otherwise unknown sales
period. Review or image responses still cannot become partial product records.

Isolated tests cover the obstructing request followed by a completed listing,
late completion after reopening connections, independent forward/history lanes,
bounded fair retries, queue capacity, missing and failed records, unknown capture
time, atomic rollback, idempotence and an unchanged native database. These are
source tests, not evidence of an installed repair or improved sales accuracy.
The desktop `docs/CURRENT_STATE.md` records exact installation and live proof.
