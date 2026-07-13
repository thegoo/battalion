"""Mission intake synthesis boundaries.

Intake synthesis only structures human mission text. Plan generation remains
owned by the deterministic mission analyst and plan renderer.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Protocol


AI_ASSISTED_INTAKE_FLAG = "--ai-assisted-intake"
TOO_COMPLEX_MESSAGE = (
    "Deterministic intake cannot structure this mission confidently. "
    f"Rerun with {AI_ASSISTED_INTAKE_FLAG} to opt in to AI-assisted intake synthesis."
)


@dataclass(frozen=True)
class RequestedArtifact:
    path: str
    artifact_type: str
    source_excerpt: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "path": self.path,
            "artifact_type": self.artifact_type,
            "source_excerpt": self.source_excerpt,
        }


@dataclass(frozen=True)
class IntakeSynthesis:
    mode: str
    original_requirement: str
    requested_artifacts: List[RequestedArtifact] = field(default_factory=list)
    traceability: Dict[str, str] = field(default_factory=dict)
    provider: str = "deterministic"

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": "battalion.intake.v1",
            "mode": self.mode,
            "provider": self.provider,
            "original_requirement": self.original_requirement,
            "requested_artifacts": [artifact.to_dict() for artifact in self.requested_artifacts],
            "traceability": dict(self.traceability),
        }


class MissionIntakeSynthesizer(Protocol):
    def synthesize(self, requirement: str) -> IntakeSynthesis:
        """Return structured mission intent without changing the human text."""


@dataclass(frozen=True)
class MarkdownArtifactReference:
    path: str
    source_excerpt: str
    is_example: bool = False


EXAMPLE_ARTIFACT_MARKER = re.compile(r"\b(?:such as|for example|e\.g\.)(?:\s*,)?\s*", flags=re.IGNORECASE)
MARKDOWN_ARTIFACT_PATTERN = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9_.-]*\.md\b")


def _sentence_start(text: str, index: int) -> int:
    boundary = 0
    for match in re.finditer(r"[.!?]\s+(?=[A-Z])", text[:index]):
        if text[max(0, match.start() - 3):match.start() + 1].lower() == "e.g.":
            continue
        boundary = match.end()
    return boundary


def _is_example_artifact(requirement: str, artifact_start: int) -> bool:
    sentence_prefix = requirement[_sentence_start(requirement, artifact_start):artifact_start]
    return EXAMPLE_ARTIFACT_MARKER.search(sentence_prefix) is not None


def markdown_artifact_references(requirement: str) -> List[MarkdownArtifactReference]:
    references = []
    seen = set()
    for match in MARKDOWN_ARTIFACT_PATTERN.finditer(requirement):
        path = match.group(0)
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        references.append(MarkdownArtifactReference(
            path=path,
            source_excerpt=requirement,
            is_example=_is_example_artifact(requirement, match.start()),
        ))
    return references


def requested_markdown_artifact_paths(requirement: str) -> List[str]:
    return [reference.path for reference in markdown_artifact_references(requirement) if not reference.is_example]


def example_markdown_artifact_paths(requirement: str) -> List[str]:
    return [reference.path for reference in markdown_artifact_references(requirement) if reference.is_example]


def _markdown_artifacts(requirement: str) -> List[RequestedArtifact]:
    artifacts = []
    for reference in markdown_artifact_references(requirement):
        if reference.is_example:
            continue
        artifacts.append(RequestedArtifact(
            path=reference.path,
            artifact_type="markdown_document",
            source_excerpt=reference.source_excerpt,
        ))
    return artifacts


def deterministic_intake_too_complex(requirement: str) -> bool:
    text = " ".join(requirement.split())
    if len(text) > 900:
        return True
    clause_count = len(re.findall(r"\b(?:and|or|but|especially|expected|preserve|required|include)\b", text, flags=re.IGNORECASE))
    return clause_count >= 16


class DeterministicMissionIntakeSynthesizer:
    def synthesize(self, requirement: str) -> IntakeSynthesis:
        if deterministic_intake_too_complex(requirement):
            raise ValueError(TOO_COMPLEX_MESSAGE)
        traceability = {"source": "mission_prompt", "prompt_excerpt": requirement}
        example_artifacts = example_markdown_artifact_paths(requirement)
        if example_artifacts:
            traceability["example_references"] = ", ".join(example_artifacts)
        return IntakeSynthesis(
            mode="deterministic",
            original_requirement=requirement,
            requested_artifacts=_markdown_artifacts(requirement),
            traceability=traceability,
        )


class StubAiAssistedMissionIntakeSynthesizer:
    """Provider boundary for future AI-assisted synthesis.

    The stub deliberately performs only deterministic local extraction. It proves
    the opt-in route and records the boundary without requiring an AI provider.
    """

    def synthesize(self, requirement: str) -> IntakeSynthesis:
        traceability = {"source": "mission_prompt", "prompt_excerpt": requirement}
        example_artifacts = example_markdown_artifact_paths(requirement)
        if example_artifacts:
            traceability["example_references"] = ", ".join(example_artifacts)
        return IntakeSynthesis(
            mode="ai_assisted",
            provider="stub",
            original_requirement=requirement,
            requested_artifacts=_markdown_artifacts(requirement),
            traceability=traceability,
        )


def synthesize_mission_intake(requirement: str, ai_assisted: bool = False) -> IntakeSynthesis:
    synthesizer: MissionIntakeSynthesizer
    if ai_assisted:
        synthesizer = StubAiAssistedMissionIntakeSynthesizer()
    else:
        synthesizer = DeterministicMissionIntakeSynthesizer()
    return synthesizer.synthesize(requirement)
