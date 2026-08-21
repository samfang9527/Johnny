## 1. Agent Contracts

- [x] 1.1 Add agent runtime domain/application value objects for run metadata, tool calls, model requests/responses, token usage, context sources, and safety decisions.
- [x] 1.2 Add application-facing protocols for `AgentRunStore`, `AgentTool`, `AgentToolRegistry`, and `ModelGateway`.
- [x] 1.3 Add unit tests for contract validation, tenant-scoped tool inputs, ordered tool-call records, and safe serialization of summaries.

## 2. Agent Run Persistence

- [x] 2.1 Implement `SqlAlchemyAgentRunRepository` over existing `agent_runs`, `agent_run_steps`, and `agent_context_sources` models.
- [x] 2.2 Add repository tests for creating, completing, failing, and linking agent runs to recommendations.
- [x] 2.3 Add repository tests for ordered tool steps, context sources, latency, token usage, and safe error summaries.

## 3. Read Tools

- [x] 3.1 Implement athlete context and memory read tools using application-facing stores/providers.
- [x] 3.2 Implement training plan, today workout, recent activities, recovery state, and training metrics tools.
- [x] 3.3 Add tool contract tests proving read tools return structured, user-scoped payloads and do not expose raw database models.
- [x] 3.4 Add tests proving deterministic analytics are produced through existing analytics handlers/services rather than model output.

## 4. Proposal Write Tools

- [x] 4.1 Implement recommendation creation and workout adjustment proposal tools over recommendation approval/application handlers.
- [x] 4.2 Implement memory candidate storage as a proposal-style tool result without directly mutating durable athlete facts.
- [x] 4.3 Add tests proving write tools create pending recommendations or candidate records and do not directly mutate training plans.

## 5. Runtime Orchestration

- [x] 5.1 Implement the Running Companion Agent handler with prompt version, trigger metadata, tool registry, model gateway, and run store dependencies.
- [x] 5.2 Implement a fake model gateway for offline orchestration tests.
- [x] 5.3 Add daily recommendation orchestration tests that build today context, call tools, create a recommendation, record run steps, and link the recommendation to the run.
- [x] 5.4 Add failure-path orchestration tests proving failed tools or model calls mark the run failed and avoid successful recommendation links.

## 6. Safety Boundaries

- [x] 6.1 Add safety classification for pain, injury-adjacent, illness, and medical-style prompts.
- [x] 6.2 Add output/action guards that reject or downgrade aggressive workout increases under unsafe or recovery-limited context.
- [x] 6.3 Add tests for conservative non-diagnostic responses and professional-care escalation language.

## 7. Verification

- [x] 7.1 Run focused agent runtime, tool, safety, and persistence tests.
- [x] 7.2 Run the full backend test suite.
- [x] 7.3 Update any affected architecture or schema documentation if implementation reveals naming or observability changes.
