# Use JSONL for Phase 2A dry-run order intents

Phase 2A is intended to prove a deterministic local loop through the real websocket boundary, not to build a dry-run product surface. Dry-run order intents will therefore be emitted as structured JSONL on stdout first, instead of being persisted through PostgreSQL, FastAPI, and the frontend dashboard; persistence and display can be added after the local loop is stable.

**Considered Options**

- JSONL on stdout for the first deterministic loop
- Persist order intents to PostgreSQL and expose them through FastAPI/dashboard immediately

**Consequences**

- The first slice stays small enough to debug from command-line output and tests.
- Dashboard visibility is deferred deliberately, not forgotten.
