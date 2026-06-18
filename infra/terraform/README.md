# infra/terraform/ — Infrastructure as Code (stubs)

Provider-neutral IaC, filled in when we automate provisioning. Kept minimal until needed
(we provision Proxmox hosts manually first — see
[../proxmox/README.md](../proxmox/README.md)).

Planned modules:
- `proxmox/` — LXC/VM hosts for dev/test stages (`bpg/proxmox` provider).
- `cloud/` — optional cloud target (Postgres, object store, container runtime) if/when we
  move off-prem. Designed to mirror the same standard interfaces.

No state is committed; backend config + `*.tfvars` are gitignored. Add real modules with
the ADR that introduces them ([../../docs/decision-log.md](../../docs/decision-log.md)).
