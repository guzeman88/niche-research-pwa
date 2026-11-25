# Native public publication and service health

Public packages read the existing local Supabase research projection, separately
from the larger canonical native SQLite library. They contain public keyword
research only. Account tables, buyer information, artwork and private financial
records are excluded. Missing demand, sales and profit remain unknown.

The backend owns the six-hour export cadence (`APP_PUBLIC_EXPORT_ENABLED=1`).
It requires the pinned runtime commit, local Supabase URL/service credential,
Node and the existing Python environment. A source watermark change during the
export aborts that candidate. Generation is outside request handlers and uses a
single-process lease, bounded staging, atomic identity pointer and a verified
current/previous cache. Unexpected operator files are preserved during retention.

The authenticated `/api/export/public-snapshot` manifest lists all eight
resources. Keywords are partitioned into at most 5,000 rows or 4 MiB per file.
Every file has a byte count and SHA-256 hash; the complete resource map has a
content identity. Partial exports never become current. No generation runs on GET.

GitHub's existing publishing workflow reads the service-only connection registry
using its dedicated account credentials, decrypts the existing private connector
credential in memory, and downloads files with method/path-bound 30-second read
tickets. Secrets exist only in the required build step. These public files are
published under `/data/current/<identity>/`; the eight original compatibility
files keep their original observation date and exact bytes. The compatibility
archive is not described as current collection. Browser reads validate sizes,
hashes, identity and keyword counts, and restart once after a deployment race.
New-package corruption cannot silently mix in old-package data.

The separate public collection report reads a bounded aggregate published from
the canonical native library. It measures rows stored in the last 24 hours;
it does not infer provider utilization, sales or a numeric collection ceiling.
Aggregates refresh hourly and expire after 75 minutes without fresh evidence.

Apply the root repository's account-service health migration before deploying
the health function. The existing five-minute dashboard job records only three
bounded service-only status rows: hosted account storage, private heartbeat and
published research freshness. Storage warns at 350 MB; heartbeat uses 150 seconds;
public publication uses 13 hours and underlying observations 48 hours. The
authenticated administrator health view marks checks older than 11 minutes
unavailable. It sends no external messages and introduces no separate scheduler.

`GET /api/production/etsy/validation` compares frozen estimates with complete
own-shop receipt windows only when listing ownership, time window, units, target
definition and recording time agree. A first recording timestamp is preserved;
old predictions are never retroactively certified. Gross paid units/purchases
by receipt creation are separate from net sales. Target-unknown models remain
ineligible. Metrics describe matched own-shop cases, never general competitor
accuracy. Existing manual outcome import remains available, including an optional
explicit target definition. No automatic model activation or training is added.

Source support is not installation or deployment proof. Record actual commits,
backup receipts, live manifest checks and remaining consent/approval requirements
in the root CURRENT_STATE handoff after rollout.
