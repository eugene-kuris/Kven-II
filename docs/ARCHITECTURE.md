# Architecture

Kven II is organized around a distinction between **intelligence** and **continuity**.

A model call can provide intelligence for a moment. Continuity requires surrounding state that survives the call and remains causally connected to later calls.

## Functional layers

```mermaid
flowchart LR
    Clients[Authenticated clients and transports] --> Principal[Trusted person binding]
    Principal --> Context[Continuous conversation context]
    Context --> Runtime[Inference runtime]
    Runtime --> Memory[Durable memory and typed retrieval]
    Memory --> SQLite[(Authoritative SQLite)]
    Memory --> HNSW[Rebuildable HNSW projection]
    Runtime --> Policy[Bounded trusted evidence tools]
    Policy --> INFRA[Typed derived INFRA]
    Lab[Owner-lab read-only collector] --> INFRA
    Policy --> Archive[Read-only historical archive evidence]
    INFRA --> Runtime
    Archive --> Runtime
    Runtime --> Model[Replaceable model adapters]
```

### Conversation state

Transport should not be the sole owner of history. Conversation state needs stable interlocutor/thread identity, ordered messages, restart-safe persistence, and a deliberate context-window policy.

### Unified memory

Different interlocutors do not imply different artificial personalities. The system uses one memory substrate with typed records, provenance, relationship-aware retrieval, and disclosure boundaries above storage.

SQLite is authoritative. Vector indexes are derived and rebuildable.

### Retrieval

The accepted retrieval generation uses Qwen3-Embedding-8B normalized 4096-dimensional vectors. A typed HNSW map prevents ambiguous integer IDs across episodic and semantic tables. Planner reranking filters approximate-neighbor candidates through a strict relevance protocol.

### Model boundary

Model and server choices are replaceable components. Backend-specific normalization belongs in adapters. This public tree includes a concrete Qwen/llama.cpp stream adapter.

### Tool ownership and continuation

Tool semantics belong to Kven, not to the model or client. Structured requests execute through a trusted boundary or fail closed; protocol-shaped client/model text is not evidence that execution occurred.

Continuations are bounded state transitions. The representative public path accepts a trusted web search, permits at most one fetch selected from its results, and then terminates in an ordinary semantic answer. It has no recursive browsing state. Current-time questions likewise depend on authoritative time execution and server-owned request-time grounding rather than client claims.

### Transports and durable identity

UI, social, and mail connections are transports around the same Kven-owned context, person/binding, memory, and retrieval state. A transport account identifier is durable routing evidence, not by itself authorization or a separate artificial personality. Private endpoints, concrete identities, ledgers, cursors, and session/control details are excluded here.

### Accepted infrastructure evidence slices

**INFRA-01** is an accepted, typed, provenance-preserving, rebuildable derived projection. Source observations remain authoritative; facts can be historical, contradictory, superseded, unknown or independently verified. Unsupported exact claims fail closed.

**INFRA-02** adds bounded read-only source collection and deterministic drift comparison, accepted on a hypervisor in the owner's private lab. Source-native identities and immutable observation digests preserve origin. COMPLETE/PARTIAL/FAILED scope coverage prevents false removals, while fact-specific re-verification distinguishes fresh observations from old state. This is not SSI production monitoring.

### Historical evidence and authority

The accepted historical-owner-archive capability is a fixed-source, owner-scoped read-only search/read/attachment evidence tool. Message provenance and RFC822/MIME evidence are retained; attachment metadata includes verified decoded size and SHA-256. Mail headers and content are untrusted historical observations, not current-state proof, authenticated identity or authorization to execute actions. The public repository includes no live archive credentials, messages or binary data.

### Administration roadmap and current limits

Kven II's long-term architecture is to perform bounded administration under explicit owner authority, not only to advise humans. Incident/change workspaces, generated infrastructure documents, guarded write/execution authority, asynchronous Deep Worker, and ChatGPT task delegation remain future work. Kven has **no granted SSI production access**; no private operational execution path is published here.

### Persistent-state discipline

Kven-owned SQLite is intentionally non-WAL. `journal_mode=DELETE` is part of the accepted design rather than an incidental default.

## What this public projection is not

It is not the production topology. It omits live runner/control-plane entrypoints, host-specific deployment configuration, credentials, runtime state, and administrative trust mechanics. Those omissions do not change the architecture described above; they remove operational authority from the public surface.
