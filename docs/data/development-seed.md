# Development seed

The opt-in seed is exclusively for local demonstrations and automated tests. Every geography,
observation, signal, warning, playbook, plan, and action it creates is marked
`SYNTHETIC / DEVELOPMENT DATA`. It must never be loaded into production.

Set a local password through `SEED_PASSWORD` and run:

```shell
docker compose --profile seed run --rm seed
```

All accounts use the operator-supplied password:

| Role | Development-only email |
|---|---|
| Platform Super Admin | `super-admin@development.invalid` |
| National Analyst | `national-analyst@development.invalid` |
| Regional Analyst | `regional-analyst@development.invalid` |
| District Officer / Field Reporter | `district-officer@development.invalid` |
| Early Action / Response Coordinator | `response-coordinator@development.invalid` |
| Decision Maker | `decision-maker@development.invalid` |
| Data / ML Scientist | `ml-scientist@development.invalid` |
| Partner / Read-only Viewer | `partner-viewer@development.invalid` |

The service updates declared role capabilities and creates missing records without duplicating
existing seed users or workflow entities. It does not reset existing passwords; delete the local
development volume if a clean credential reset is required.
