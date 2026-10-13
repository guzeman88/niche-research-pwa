# EtGen web and research backend

React/TypeScript PWA, FastAPI research/operator backend, account functions,
Launch Lab and private product-validation workspace. Desktop tooling and host
operations live in the independent [etsy-pipeline repository](https://github.com/guzeman88/etsy-pipeline).

For continuation, read [AGENTS.md](AGENTS.md) and
[docs/current-state.md](docs/current-state.md) before choosing a database target,
collecting evidence, changing accounts or deploying. The installed local app and
public production site do not automatically follow merged source.

Use Node 22 with `npm ci`. Checks: `npm test`, `npm run lint`, `npx tsc -b`,
`npm run build`. Install backend dependencies from `backend/requirements.txt`
with `-c backend/requirements-constraints.txt` to reproduce the tested versions;
run `python -m pytest tests -q` from `backend` with its configured environment.
Builds validate the snapshot contract; choose the intended snapshot source.
Do not use real-provider/live-account tests as routine setup commands.

Implemented workflows: [private validation](docs/product-validation.md),
[Launch Lab](docs/launch-lab.md), [accounts](docs/accounts.md),
[operator workspace](docs/operator-workspace.md). Provider and bulk collection
documents describe separate workflows, not proof of current provider access.
