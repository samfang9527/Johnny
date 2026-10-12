## Purpose
Define the Chinese-first visual and interaction requirements for Johnny's Conversation and pending Recommendation surfaces.

## Requirements

### Requirement: Conversation surface visual hierarchy
The system SHALL render `對話` as a Chinese-first support surface for user-initiated training questions while preserving Today as the primary daily decision cockpit.

#### Scenario: User opens Conversation
- **WHEN** the user opens `對話`
- **THEN** the UI shows a thread list, active message history, and compact composer using `DESIGN.md` visual tokens
- **AND** the composer does not replace Today as the primary app surface

### Requirement: IME-safe message composer
The system SHALL provide an app-owned message composer that supports Traditional Chinese input safely.

#### Scenario: User submits a training question
- **WHEN** the user submits a non-empty training question
- **THEN** the frontend sends the message to the conversation API
- **AND** the UI shows a stable busy state until Johnny's response or run reference returns

#### Scenario: User is composing Chinese text
- **WHEN** the user presses Enter during IME composition
- **THEN** the composer MUST NOT submit the message
- **AND** the composed text remains available for editing

#### Scenario: User submits an empty message
- **WHEN** the user submits an empty or whitespace-only message
- **THEN** the UI shows inline Chinese validation copy
- **AND** the frontend does not call the conversation API

### Requirement: Agent response evidence rendering
The system SHALL render Johnny responses with structured evidence and proposed actions when available.

#### Scenario: Johnny response includes evidence
- **WHEN** a Johnny response includes evidence items
- **THEN** the UI shows the evidence in shared evidence blocks using the `DESIGN.md` data typography
- **AND** evidence remains visually connected to the message it supports

#### Scenario: Johnny response includes proposed actions
- **WHEN** a Johnny response includes proposed actions
- **THEN** the UI shows action cards with stable recommendation action labels where the action changes a training decision

### Requirement: Johnny decision queue
The system SHALL render `Johnny` as a pending Recommendation decision queue separate from Daily Advice and Conversation.

#### Scenario: User views pending recommendations
- **WHEN** pending recommendations exist
- **THEN** Johnny shows each Recommendation with priority, summary, evidence, status, expiration when present, and available approval actions

#### Scenario: User views historical recommendations
- **WHEN** accepted, rejected, edited, expired, or applied recommendations exist
- **THEN** the inbox keeps them visible in a quieter historical state without competing with pending recommendations

#### Scenario: Inbox is empty
- **WHEN** no proactive recommendations exist
- **THEN** the UI shows a Chinese-first empty state explaining that future plan-change proposals will appear here

#### Scenario: Daily Advice appears beside the decision queue
- **WHEN** current Daily Advice exists for the athlete-local date
- **THEN** Johnny may show the same single current advice near the weekly review
- **AND** it does not enter the pending queue or expose accept/reject actions

### Requirement: Linked recommendation discussion
The system SHALL let users discuss a recommendation from Today or Agent Inbox while preserving the recommendation context.

#### Scenario: Discuss from Agent Inbox
- **WHEN** the user chooses `討論原因` on an inbox recommendation
- **THEN** the frontend opens or creates a conversation linked to that recommendation
- **AND** the conversation displays the recommendation title, status, and evidence summary as context

### Requirement: Shared recommendation interaction consistency
The system SHALL keep recommendation actions consistent across Today, Agent Inbox, and Conversation proposed-action cards.

#### Scenario: Recommendation actions appear outside Today
- **WHEN** recommendation actions appear in `Johnny` or a future `對話` proposed-action card
- **THEN** the actions use the same labels, busy behavior, disabled behavior, and focus-visible treatment as Today
- **AND** destructive or rejection actions remain visually distinct without relying on color alone
