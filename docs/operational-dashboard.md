# Active dashboard and private backend connection

The hosted administrator dashboard reads `app_dashboard_state`, a bounded report
published by the installed backend every60 seconds. Native keyword collection,
the validation ledger, sales intelligence and production retain their original
writers. Reports contain aggregates, versioned research leads and timestamps;
customer inputs, raw provider packets, account workspaces and credentials are excluded.

All chart sections and headline counts use this same report. Unknown rankings
and unavailable breakout detection stay unknown. User-mode imported scans retain
their separate account scope. Static files are an explicitly historical fallback;
their source observation watermark is distinct from their build date.

The owner explicitly approved the free authenticated Cloudflare connection on
November11,2026. The backend owns the connector process; no Windows collection
timer or Codex automation is added. It verifies the HTTPS route before announcing
it. Restarting the app can change the temporary address. The publisher updates
the protected connection row; browsers do not store or configure that address.

`app_backend_connections` is service-only with RLS. It contains an AES-GCM
encrypted access credential bound to `private-backend`, plus the heartbeat and
current endpoint. The account function validates session, active administrator,
MFA and revocation, then issues a30-second HS256 permission for an exact method
and decoded API path. The browser uses that permission directly, including for
large uploads/downloads. Long-lived access credentials and database service-role
keys never enter browser storage or responses. Connector mode protects every
`/api/` route; invalid credentials never fall back to loopback authorization.

Protected configuration, outside Git:

- `APP_DASHBOARD_REPORTING_ENABLED=1`
- `REPORTING_SUPABASE_URL`, `REPORTING_SUPABASE_SERVICE_ROLE_KEY`
- `APP_DASHBOARD_TUNNEL_ENABLED=1`, `CLOUDFLARED_PATH`
- `PIPELINE_API_TOKEN` (random strong local server credential)
- `DASHBOARD_BRIDGE_SECRET` (random32-byte base64 encryption key, also configured
  in the hosted account function environment without a VITE prefix)

Apply the root repository's November11 dashboard migrations first. They add
isolated reporting tables, a narrow observation index and a newest-valid-Google
reading export view. They do not reset historical research or account records.
The build uses keyset pagination over the export view and retains count/quality
release gates. Google rows and listing samples do not prove Etsy sales.

If the PC or connector is offline, reporting remains readable with a stale
indicator. Private actions fail closed when the heartbeat exceeds150 seconds.
The connector is free and depends on the awake PC and Cloudflare availability;
the system does not promise uninterrupted hosting. Last-known totals must not
be labeled live collection merely because an HTTP request succeeded.
