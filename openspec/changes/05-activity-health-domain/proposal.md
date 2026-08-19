# Proposal: Activity and Health Domain

## Why

Johnny needs normalized training and recovery data before deterministic analytics and recommendations can work.

## What Changes

- Add domain models for activities and health metrics.
- Support manual MVP input so development is not blocked by Garmin or Strava access.
- Add basic matching between actual activities and planned workouts.

## Capabilities

### New Capabilities

- `activity-health-domain`

### Modified Capabilities

- `persistence-schema`
- `training-plan-domain`

## Impact

This enables analytics, recommendation evidence, Today context, and future integration ingestion.

