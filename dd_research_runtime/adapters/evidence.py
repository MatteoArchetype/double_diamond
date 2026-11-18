from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Protocol

from ..runtime import ResearchInvariantError, ResearchState


@dataclass
class RetrievedDocument:
    source_id: str
    title: str
    publisher: str
    uri: str
    retrieved_at: str
    content: str
    provenance: Dict[str, Any] = field(default_factory=dict)
    independence_cluster: str = ""
    synthetic: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceCandidate:
    evidence_id: str
    source_id: str
    finding: str
    exact_location: str
    evidence_type: str = "observed"
    excerpt: str = ""
    synthetic: bool = False
    claim_fitness: List[str] = field(default_factory=list)
    extraction_notes: str = ""


class RetrievalAdapter(Protocol):
    def retrieve(self, locator: str) -> RetrievedDocument: ...


class EvidenceAdapter:
    """Boundary between retrieval and ResearchState.

    Retrieval adapters return documents; this layer converts bounded findings into
    auditable evidence records. It never turns interpretation into observed fact.
    """

    def __init__(self, state: ResearchState):
        self.state = state

    @staticmethod
    def _fingerprint(source_id: str, finding: str, exact_location: str) -> str:
        raw = f"{source_id}|{finding.strip()}|{exact_location.strip()}".encode("utf-8")
        return sha256(raw).hexdigest()[:16]

    def register_document(self, doc: RetrievedDocument) -> None:
        if not doc.provenance:
            raise ResearchInvariantError("retrieved document requires provenance")
        if not doc.independence_cluster:
            raise ResearchInvariantError("retrieved document requires independence_cluster")
        if doc.synthetic:
            # Synthetic sources are valid test fixtures but remain explicitly marked.
            provenance = dict(doc.provenance)
            provenance.setdefault("status", "synthetic")
        else:
            provenance = dict(doc.provenance)
        self.state.add_source({
            "source_id": doc.source_id,
            "title": doc.title,
            "publisher": doc.publisher,
            "uri": doc.uri,
            "retrieved_at": doc.retrieved_at,
            "provenance": provenance,
            "independence_cluster": doc.independence_cluster,
            "synthetic": doc.synthetic,
            "metadata": doc.metadata,
        })

    def ingest(self, candidates: Iterable[EvidenceCandidate]) -> List[str]:
        added: List[str] = []
        for c in candidates:
            if not c.finding.strip():
                raise ResearchInvariantError("evidence finding cannot be empty")
            if not c.synthetic and not c.exact_location.strip():
                raise ResearchInvariantError("non-synthetic evidence requires exact_location")
            source = self.state.sources.get(c.source_id)
            if not c.synthetic and source is None:
                raise ResearchInvariantError(f"unknown source: {c.source_id}")
            eid = c.evidence_id or f"E-{self._fingerprint(c.source_id,c.finding,c.exact_location)}"
            if eid in self.state.evidence:
                existing = self.state.evidence[eid]
                if existing.get("finding") == c.finding and existing.get("exact_location") == c.exact_location:
                    added.append(eid)
                    continue
                raise ResearchInvariantError(f"evidence id collision: {eid}")
            self.state.add_evidence({
                "evidence_id": eid,
                "source_id": c.source_id,
                "finding": c.finding,
                "exact_location": c.exact_location,
                "evidence_type": c.evidence_type,
                "excerpt": c.excerpt,
                "synthetic": c.synthetic,
                "claim_fitness": list(c.claim_fitness),
                "extraction_notes": c.extraction_notes,
            })
            added.append(eid)
        return added

    def ingest_document_findings(self, doc: RetrievedDocument, candidates: Iterable[EvidenceCandidate]) -> List[str]:
        if doc.source_id not in self.state.sources:
            self.register_document(doc)
        normalized = []
        for c in candidates:
            if c.source_id != doc.source_id:
                raise ResearchInvariantError("candidate source_id does not match document")
            if c.synthetic != doc.synthetic:
                raise ResearchInvariantError("synthetic status must match source")
            normalized.append(c)
        return self.ingest(normalized)
