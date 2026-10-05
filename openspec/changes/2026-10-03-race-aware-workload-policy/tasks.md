## 1. Design gate

- [x] 1.1 Receive explicit product-owner approval of `design.md` (approved 2026-10-05).
- [ ] 1.2 Confirm the provisional numerical policy thresholds through coaching review before release. The approved implementation keeps them versioned and reviewable.

## 2. Capacity and Race Strategy data

- [x] 2.1 Add optional structured course and goal fields to Race Goal, persistence mapping, and API; verify legacy race round trips.
- [x] 2.2 Add the optional fields to Race Goal entry and read views with frontend validation and compatibility coverage.
- [x] 2.3 Add a complete 56-day user-scoped running activity query and deterministic capacity snapshot; verify activity filtering, sparse data, and source confidence.

## 3. Workload policy and skeleton

- [x] 3.1 Implement the versioned weekly workload prescription and preparation assessment as pure application/domain logic with fixed time and capacity fixtures.
- [x] 3.2 Make the Plan Skeleton consume the prescription; cover phase progression, 40 km and >50 km differentiation, hard-session/injury limits, short horizon, and continuity.

## 4. Generation contract

- [x] 4.1 Pass policy output through the generation request and revise the LLM prompt and local provider to use it.
- [x] 4.2 Validate step totals above and below prescribed duration, then verify one model repair and policy-aligned Completion Repair/fallback.
- [x] 4.3 Persist and expose public assessment plus private policy/provenance metadata while retaining old/manual plan compatibility.

## 5. Athlete experience and verification

- [x] 5.1 Render preparation assessment in the Plan view with Traditional Chinese gap/unknown copy and accessibility checks.
- [x] 5.2 Run focused backend/frontend tests, the original 40 km reproduction, full relevant suites, and a local queued generation through the production worker path.
- [x] 5.3 Update active specs and domain documentation to resolve the older LLM-ownership wording; mark tasks only after verification.
