# Proposal: Training Plan Domain

## Why

Johnny's recommendations need a concrete plan to evaluate and adjust. The MVP should first model plans reliably before generating or modifying them intelligently.

## What Changes

- Add training plan and workout domain behavior.
- Add controlled status transitions.
- Add adjustment proposal records that preserve before/after changes.

## Capabilities

### New Capabilities

- `training-plan-domain`

### Modified Capabilities

- `persistence-schema`
- `athlete-race-domain`

## Impact

This provides the core schedule that Today, analytics, recommendations, and frontend calendar views depend on.

