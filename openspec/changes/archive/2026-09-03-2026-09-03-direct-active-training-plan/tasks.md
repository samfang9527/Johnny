## 1. Approval

- [x] 1.1 Confirm product-owner approval to abandon draft -> recommendation -> active-plan flow.
- [x] 1.2 Confirm generated training plans should activate immediately and supersede overlapping active plans for the same race.

## 2. Agent Runtime

- [x] 2.1 Replace generated-plan draft tool usage with `createTrainingPlan`.
- [x] 2.2 Remove recommendation follow-up requirements from `training_plan_generation`.
- [x] 2.3 Update local and OpenAI gateway schemas to match the new tool contract.

## 3. Domain And Persistence

- [x] 3.1 Add active-plan creation repository behavior.
- [x] 3.2 Supersede only overlapping active plans for the same race.
- [x] 3.3 Remove recommendation-driven draft activation from recommendation approval.

## 4. Tests And Docs

- [x] 4.1 Add focused tests for active generation, no recommendation requirement, old recommendation payload rejection, and overlap-based superseding.
- [x] 4.2 Update docs and active specs.
- [x] 4.3 Run focused tests and full backend suite.
