# Operator workspace

## Private API

Set `PIPELINE_API_TOKEN` to a randomly generated operator secret in the backend environment or ignored `.env.local`. Never set a `VITE_` token: that would embed the credential in the public app. Set `PIPELINE_ALLOWED_ORIGINS` to comma-separated web origins; the default is the production Netlify site. Local browser origins are allowed for development.

Remote settings, stores, scheduler controls, workspace backups, and all mutations require `Authorization: Bearer <token>`. Direct loopback requests are allowed for local CLI operation only when the host and browser origin are local and proxy headers are absent. Public research snapshots remain readable. Settings responses redact secrets.

Open **Workspace & backups** in the app to connect. Connection credentials are stored in session storage for the current tab and excluded from workspace exports. Disconnect clears them.

## Backup and transfer

Download a backup before changing devices. Import previews show added and conflicting records. Merge preserves this browser's version of a conflicting record and adds new records. Keep the original backup file if you need to inspect an alternate version later. A malformed file is rejected before changes are written.

Server backups require a connection. Each save creates a new revision; earlier revisions are retained. On another device, connect, browse server backups, and preview a merge. This is explicit transfer, not background bidirectional synchronization. Back up the server workspace directory as part of machine backups.

## Scanner operation

The backend runs one scanner per process; use a single Uvicorn worker. The watchdog and web heartbeat observe status and never resume an operator pause or stop. Worker failures finalize the run and require an explicit restart. Five consecutive scan failures halt the worker so unavailable providers cannot silently produce an endless retry loop.

Google Suggest can provide source phrases without credentials. It does not supply Etsy price, demand, conversion, or profitability evidence. Market-evidence counts should remain zero until a source provides actual listing data.

`AUTO_START_SCHEDULER=0` keeps startup idle for testing or releases. The local PowerShell launcher uses UTF-8 output. Review `/api/scheduler/status` for health, the last progress timestamp, and failures rather than treating an HTTP 200 as proof of progress.
