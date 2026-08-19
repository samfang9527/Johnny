# Proposal: Backend API

## Why

The MVP needs a coherent API layer after domain behavior exists, so frontend work can depend on stable contracts.

## What Changes

- Add route groups for MVP product workflows.
- Add request and response schemas.
- Add API-level validation and error handling.
- Expose Today, recommendations, conversation, and webhook entry points.

## Capabilities

### New Capabilities

- `backend-api`

### Modified Capabilities

- All earlier MVP backend capabilities become externally reachable through API routes.

## Impact

This creates the integration contract between backend, frontend, and provider webhook workflows.

