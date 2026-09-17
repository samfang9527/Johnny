# Deterministic Training Plan Skeletons

Johnny generates the complete plan skeleton deterministically before LLM enrichment. The LLM may enrich coaching intent, workout purposes, coach notes, and structured key-session details, but it must not own workout dates, weekly structure, phase coverage, or plan completeness. This keeps active projections complete, quota-safe, and recoverable when model output is partial, while still allowing model-backed coaching nuance inside validated boundaries.

## Consequences

Training plan generation must validate that every active projection covers its requested horizon, every workout belongs to a canonical phase segment, and incomplete model output is repaired before persistence. The system may use completion repair or deterministic templates to fill missing weeks, and it must record those repairs in agent run logs and internal plan metadata.
