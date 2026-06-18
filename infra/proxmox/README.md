# infra/proxmox/ — Proxmox provisioning

Manual-first, then automated. Full topology + rationale in
[../../docs/infrastructure.md](../../docs/infrastructure.md).

## Stand up a stage (manual, summary)
1. **app-host** — create a VM (recommended) or a privileged LXC with nesting:
   - LXC option: `features: nesting=1,keyctl=1`, privileged. Give it a dedicated data disk.
   - Install Docker + the compose plugin.
2. **Deploy the stack:**
   ```sh
   git clone https://github.com/Alobidat/NewTimeLine.git
   cd NewTimeLine
   cp .env.example .env   # set strong secrets
   docker compose up -d
   docker compose ps      # all healthy?
   ```
3. **edge-proxy** (public test only) — small LXC running Caddy/Traefik for TLS; reverse-
   proxy 80/443 → app-host. Add a public DNS record + router port-forward.

## To automate later
- Proxmox cloud-init VM templates / LXC templates for repeatable host creation.
- Optional Terraform (`bpg/proxmox` or `telmate/proxmox`) — stubs in
  [../terraform/](../terraform/).

> Scripts (`pct`/`qm` provisioning, Caddyfile, deploy script) will be added here when we
> first build the `dev`/`test` hosts.
