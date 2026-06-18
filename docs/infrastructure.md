# Infrastructure — Proxmox LXC hosting (local + public testing)

We host on the **on-site Proxmox** cluster using **LXC containers** for local and public
test environments. The application stays cloud-agnostic (standard interfaces only), so the
same Docker images run here now and on any cloud later.

## 1. Key Proxmox decision: where Docker runs

Our local dev stack is `docker compose` (Postgres+PostGIS+pgvector, Redis, RabbitMQ,
MinIO, services). On Proxmox we have two ways to run it:

| Option | What | Trade-off |
|--------|------|-----------|
| **A. Docker host (recommended)** | One **VM** *or* a **nesting-enabled privileged LXC** that runs Docker + our compose stack | Matches local dev exactly; simplest path; one box to manage. Docker-in-LXC needs `nesting=1`, `keyctl=1` and (often) the container privileged — slightly less isolated. A small VM avoids those caveats and is the safest choice for the Docker host. |
| **B. Service-per-LXC** | Each backing service in its own LXC (no Docker): a Postgres LXC, Redis LXC, RabbitMQ LXC, MinIO LXC, plus app LXCs | More "Proxmox-native", better isolation/resource control, but diverges from the compose workflow → more ops + drift risk. |

**Recommendation:** start with **Option A** — a single Docker-host environment per stage
(dev/test) — because it mirrors local dev and minimizes maintenance (token-economy applies
to ops too). Move stateful services (Postgres especially) to dedicated containers/VMs
(Option B style) only when load or backup/HA needs justify it.

> Note on Docker-in-LXC: prefer a **VM** for the Docker host if the cluster has spare RAM.
> If using an LXC, it must be **privileged** with `features: nesting=1,keyctl=1`. Postgres
> is happiest with stable storage — give it a dedicated disk/volume either way.

## 2. Proposed environments (stages)

| Stage | Purpose | Exposure | Notes |
|-------|---------|----------|-------|
| `dev` | Integration sandbox | LAN only | Mirrors local compose; reset freely. |
| `test` (public) | Demo / external testing | Public via reverse proxy + TLS | Stable-ish data; the URL we share. |
| `prod` (later) | Real users | Public, hardened | Out of scope until Phase 7. |

Each stage = one Docker-host (VM/LXC) running the compose stack with its own `.env`.

## 3. Containers / components to create (test stage)

```
┌──────────────────────────────────────────────────────────────┐
│ Proxmox node(s)                                                │
│                                                                │
│  ┌────────────────────────┐   ┌───────────────────────────┐  │
│  │ LXC/VM: edge-proxy      │   │ VM (or nesting LXC):       │  │
│  │  Caddy/Traefik          │   │   app-host (Docker)        │  │
│  │  - TLS (Let's Encrypt)  │──▶│   compose stack:           │  │
│  │  - public entrypoint    │   │   - api (FastAPI)          │  │
│  │  - routes to api/admin  │   │   - agents (workers)       │  │
│  └────────────────────────┘   │   - admin (Flutter Web)    │  │
│                                │   - postgres (PostGIS+pgv) │  │
│                                │   - redis                  │  │
│                                │   - rabbitmq               │  │
│                                │   - minio (S3)             │  │
│                                └───────────────────────────┘  │
│                                                                │
│  ┌────────────────────────┐                                   │
│  │ LXC: backups            │  (optional) pg_dump + MinIO       │
│  │  scheduled dumps → NAS  │   snapshots to on-site storage    │
│  └────────────────────────┘                                   │
└──────────────────────────────────────────────────────────────┘
```

Minimum to stand up the **test** stage:
1. **edge-proxy** (small LXC): Caddy or Traefik for TLS + a public hostname; reverse-proxies
   to the app-host. Needed for "public test" with HTTPS.
2. **app-host** (VM recommended, or nesting LXC): runs the whole compose stack.
3. **DNS**: a public DNS record (or dynamic-DNS) pointing at the edge-proxy; a port-forward
   on the on-site router for 80/443.
4. **(optional) backups** container: scheduled `pg_dump` + MinIO bucket snapshots to NAS.

For the **dev** stage you can skip the edge-proxy/TLS and just expose ports on the LAN.

## 4. Suggested resources (test stage, starting point)
| Component | vCPU | RAM | Disk | Notes |
|-----------|------|-----|------|-------|
| app-host (all services) | 4 | 8 GB | 60 GB SSD | Postgres + workers are the heavy bits; grow as data grows. |
| edge-proxy | 1 | 512 MB | 4 GB | Tiny. |
| backups (optional) | 1 | 512 MB | size of retained dumps | |

Split Postgres onto its own VM/LXC (4 vCPU / 8 GB / dedicated SSD) when the dataset or
query load grows — the schema is built to allow it (standard Postgres connection).

## 5. Networking & security (public test)
- Only the **edge-proxy** is internet-facing; everything else stays on a private Proxmox
  bridge/VLAN.
- TLS terminated at the proxy (Let's Encrypt). Force HTTPS.
- Firewall: expose only 80/443 publicly; admin portal behind auth + optionally IP-allowlist
  or a separate hostname.
- Secrets live in each host's `.env` (not in git). Consider a secrets file with strict
  perms; a real secret manager is a Phase-7 concern.
- Backups encrypted at rest if leaving the premises.

## 6. Provisioning approach (keep it reproducible)
- Document the manual steps first ([infra/proxmox/README.md](../infra/proxmox/README.md)),
  then automate: Proxmox supports cloud-init VM templates and LXC templates; optionally
  `terraform` with the Proxmox provider (`telmate/proxmox` / `bpg/proxmox`) for repeatable
  provisioning — stubbed in [infra/terraform/](../infra/terraform/).
- App deploy on a host = `git pull` + `docker compose up -d` (later: CI builds images →
  push to a registry → host pulls). Keep it simple until it hurts.

## 7. What I need from you (access) — see also the message in chat
To actually *deploy/verify* on Proxmox (vs. just authoring the definitions), I'd need
**one** of:
- **(Preferred) SSH access to a deploy target** (the app-host VM/LXC) so I can run
  `docker compose` and check health; or
- **You run the commands** I provide and paste back output; or
- **Proxmox API access** (token) if you want me to drive container provisioning via
  Terraform/`pct`.

For **Phase 0** I need **none of these** — I'm producing the compose stack + provisioning
docs. Access becomes useful when we first stand up the `dev`/`test` host.

## 8. Open infra questions
- Proxmox version + spare capacity (RAM/CPU/SSD) available for these stages?
- Is a public hostname/domain available for the `test` stage (for TLS)? Static public IP or
  dynamic DNS?
- Preference: **VM** Docker host (safer) vs **nesting LXC** (lighter) for app-host?
- On-site backup target (NAS path) for `pg_dump`/MinIO snapshots?
- Any existing reverse proxy / DNS / cert setup we should reuse?
