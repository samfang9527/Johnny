# Delta for Frontend Conversation and Agent Inbox

## ADDED Requirements

### Requirement: AI Coach Conversation

The system SHALL let users send training questions and view Johnny's responses with evidence and proposed actions when available.

#### Scenario: Sending a training question

- WHEN the user submits a message in Conversation
- THEN the frontend sends the message to the conversation API
- AND displays Johnny's response when returned

### Requirement: Agent Inbox

The system SHALL display proactive recommendations in an inbox separate from chat.

#### Scenario: Viewing pending recommendations

- GIVEN pending recommendations exist
- WHEN the user opens Agent Inbox
- THEN the frontend displays each recommendation with priority, summary, evidence, and available actions

### Requirement: Discuss Recommendation

The system SHALL allow a user to discuss a recommendation from Today or Agent Inbox.

#### Scenario: Discuss from inbox

- GIVEN a recommendation is shown in Agent Inbox
- WHEN the user chooses Discuss
- THEN the frontend opens or creates a conversation linked to that recommendation

