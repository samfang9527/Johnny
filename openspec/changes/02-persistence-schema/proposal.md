# Proposal: Persistence Schema

## Why

Johnny needs durable, auditable data before domain services and agent workflows can be trustworthy.

## What Changes

- Add the MVP database schema and migration workflow.
- Add persistence models and repository boundaries for core MVP entities.
- Support event, recommendation, and agent observability records from the beginning.

## Capabilities

### New Capabilities

- `persistence-schema`

### Modified Capabilities

- `project-foundation` may gain database migration commands if not added earlier.

## Impact

This enables all domain, analytics, API, worker, and frontend features.

