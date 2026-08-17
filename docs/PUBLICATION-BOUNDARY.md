# Public/private boundary

This repository is an independent selected projection, not a mirror of the private engineering repository.

## Included

The public tree prioritizes source and documentation that explain:

- memory identity and provenance;
- Qwen3 embedding-space contracts;
- HNSW rebuild/integrity mechanics;
- planner reranking;
- context-window boundaries;
- model/backend adapters;
- SQLite non-WAL storage discipline;
- the engineering rationale behind those choices.

## Excluded

Operational material is excluded when publication would expose authority rather than architecture:

- self-hosted runner entrypoints;
- unattended development/integration control;
- root/admin trust implementation;
- mail/control-plane internals;
- production deployment contracts;
- host/user/mailbox-specific configuration;
- internal network endpoints;
- credentials and trust material;
- runtime databases and indexes;
- model files, logs, backups and evidence packages;
- private task/handoff history;
- private Git history.

## One-way relationship

The public repository has no workflow, hook, credential, or control path that can operate the private Kven II infrastructure.

It is a review/portfolio surface only. Future synchronization or publishing automation would be separate work and is intentionally absent from this first projection.
