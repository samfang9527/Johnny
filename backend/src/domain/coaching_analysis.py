"""Versioned, display-ready interpretation of bounded coaching evidence."""

from __future__ import annotations

from dataclasses import dataclass


SCHEMA_VERSION = 'coaching-analysis-v2'
FALLBACK_REASONS = frozenset({
    'disabled', 'timeout', 'provider_error', 'invalid_schema',
    'invalid_evidence', 'unsupported_claim',
})


@dataclass(frozen=True)
class CoachingFinding:
    observation: str
    interpretation: str
    evidence_refs: tuple[str, ...]

    def to_payload(self) -> dict:
        return {'observation': self.observation, 'interpretation': self.interpretation,
                'evidence_refs': list(self.evidence_refs)}


@dataclass(frozen=True)
class CoachingAction:
    action_id: str
    text: str
    evidence_refs: tuple[str, ...]
    recommendation_id: str | None = None

    def to_payload(self) -> dict:
        return {'action_id': self.action_id, 'text': self.text,
                'evidence_refs': list(self.evidence_refs),
                'recommendation_id': self.recommendation_id}


@dataclass(frozen=True)
class CoachingAnalysis:
    headline: str
    summary: str
    findings: tuple[CoachingFinding, ...]
    actions: tuple[CoachingAction, ...]
    limitations: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    analysis_mode: str
    fallback_reason: str | None
    input_fingerprint: str
    versions: dict[str, str]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.analysis_mode not in {'llm', 'rules'}:
            raise ValueError('unsupported coaching analysis mode')
        if (self.analysis_mode == 'llm' and self.fallback_reason is not None or
                self.analysis_mode == 'rules' and self.fallback_reason not in FALLBACK_REASONS):
            raise ValueError('invalid coaching fallback reason')

    def to_payload(self) -> dict:
        return {'schema_version': self.schema_version, 'headline': self.headline,
                'summary': self.summary, 'findings': [f.to_payload() for f in self.findings],
                'actions': [a.to_payload() for a in self.actions],
                'limitations': list(self.limitations), 'evidence_refs': list(self.evidence_refs),
                'analysis_mode': self.analysis_mode, 'fallback_reason': self.fallback_reason,
                'input_fingerprint': self.input_fingerprint, 'versions': dict(self.versions)}
