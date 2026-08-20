from __future__ import annotations

from src.domain.integrations_notifications import LineDeliveryResult, NotificationIntent


class FakeLineDeliveryGateway:
    def __init__(self, result: LineDeliveryResult) -> None:
        self._result = result
        self.delivered_intents: list[NotificationIntent] = []

    def deliver(self, intent: NotificationIntent) -> LineDeliveryResult:
        self.delivered_intents.append(intent)
        return self._result
