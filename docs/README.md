# DiamondManager Docs

Internal documentation for the DiamondManager platform (Django 6.0 + django-ninja API,
Kotlin/Compose Android client).

## Index

### Development
- [Getting Started](development/getting-started.md) — run the backend + Android
  client locally and connect them.
- [Development Accounts](development/accounts.md) — seeded + hand-created logins, roles,
  team access codes, and how to create/reset accounts.

### Streaming
- [Youth Baseball Streaming Architecture](streaming/youth-baseball-streaming-architecture.md)
  — self-hosted SRT → SRS → YouTube live pipeline.

### Operations
- [Deployment & Ops](operations/deployment.md) — relay host (SRS + agent),
  environment variables, reconciler scheduling, and a production checklist.

### Planned / TODO
- Testing guide (pytest layout, fixtures, helpers)
- API overview (base URL, auth, endpoint groups)
- Data model (Organization → Season → Division → Team)
