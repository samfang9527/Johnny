# Proposal: Athlete and Race Domain

## Why

Johnny cannot make useful training recommendations without a reliable understanding of who the athlete is and what race they are training for.

## What Changes

- Add domain models for athlete profile, preferences, and race goals.
- Add validation rules for required MVP training context.
- Add simple derived values such as target race pace.

## Capabilities

### New Capabilities

- `athlete-race-domain`

### Modified Capabilities

- `persistence-schema`

## Impact

This creates the first product-level domain behavior used by training planning, analytics, recommendations, API, and frontend onboarding.

