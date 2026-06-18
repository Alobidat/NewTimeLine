# infra/ — Infrastructure

Everything to run Chronos locally and on the on-site **Proxmox** cluster. The app is
cloud-agnostic, so the same images run anywhere.

| Path | What |
|------|------|
| `compose/postgres/` | Custom Postgres image (PostGIS + pgvector) + init SQL used by the root `docker-compose.yml`. |
| `proxmox/` | Provisioning notes/scripts for LXC/VM hosts (dev/test stages). |
| `terraform/` | Provider-neutral IaC stubs (filled when the cloud/Proxmox provider is wired). |

Local stack lives in the **root** [`docker-compose.yml`](../docker-compose.yml). Hosting
topology + the Proxmox plan: [../docs/infrastructure.md](../docs/infrastructure.md).
