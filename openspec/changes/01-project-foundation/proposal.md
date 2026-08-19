# Proposal: Project Foundation

## Why

The MVP needs a stable development base before feature work begins. Without agreed commands, configuration, and package boundaries, later features will drift.

## What Changes

- Establish backend, frontend, and infrastructure conventions for MVP work.
- Select Vue/Vite/TypeScript as the MVP frontend stack.
- Select PostgreSQL as the MVP database.
- Define local environment configuration and test commands.
- Keep the existing scaffold unless the design review explicitly decides otherwise.
- Prepare database migration support if approved during design review.

## Capabilities

### New Capabilities

- `project-foundation`

### Modified Capabilities

- None

## Impact

This is a foundation change. It should not create product behavior, but later MVP changes depend on it.
