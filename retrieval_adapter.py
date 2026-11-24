from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse
import math
import re


SYNTHETIC_PROVENANCE = {'synthetic', 'synthetic_test', 'synthetic-test', 'synthetic_local_document'}


def _json_metadata(value, active=None, depth=0):
    """Copy metadata to finite JSON values; never stringify arbitrary objects."""
    if depth > 100:
        raise ValueError('metadata nesting exceeds 100 levels')
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('metadata numbers must be finite')
        return value
    if not isinstance(value, Mapping) and type(value) is not list:
        raise TypeError('metadata must contain only JSON values')
    active = set() if active is None else active
    identity = id(value)
    if identity in active:
        raise ValueError('metadata cannot contain cycles')
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise TypeError('metadata keys must be strings')
            return {key: _json_metadata(item, active, depth+1) for key,item in value.items()}
        return [_json_metadata(item, active, depth+1) for item in value]
    finally:
        active.remove(identity)


@dataclass(frozen=True)
class RetrievedDocument:
    """Provider-neutral retrieval result; retrieval does not interpret evidence."""
    source_id: str
    title: str
    publisher: str
    url: str
    retrieved_at: str
    passage: str
    content_location: str
    provenance: str
    synthetic: bool = False
    published_at: str | None = None
    independence_cluster: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        fields = {
            "source_id": self.source_id,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "passage": self.passage,
            "content_location": self.content_location,
            "provenance": self.provenance,
        }
        wrong_types = [k for k,v in fields.items() if not isinstance(v,str)]
        if wrong_types:
            raise TypeError('required fields must be strings: '+', '.join(wrong_types))
        missing = [k for k, v in fields.items() if not v.strip()]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        parsed = urlparse(self.url)
        local_reference = (
            self.provenance in {'operator_reviewed_local_document', 'synthetic_local_document'}
            and isinstance(self.metadata, Mapping)
            and re.fullmatch(r'urn:sha256:[0-9a-f]{64}', self.url)
            and self.metadata.get('document_sha256') == self.url.removeprefix('urn:sha256:')
        )
        if not local_reference and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
            raise ValueError("url must be an absolute HTTP(S) URL")
        if type(self.synthetic) is not bool:
            raise TypeError('synthetic must be an explicit boolean')
        labelled_synthetic = self.provenance.strip().lower() in SYNTHETIC_PROVENANCE
        if self.synthetic and not labelled_synthetic:
            raise ValueError('synthetic documents must declare synthetic provenance')
        if labelled_synthetic and not self.synthetic:
            raise ValueError('synthetic provenance requires synthetic=True')
        for name in ('published_at','independence_cluster'):
            value = getattr(self,name)
            if value is not None and (not isinstance(value,str) or not value.strip()):
                raise TypeError(name+' must be a nonblank string or None')
        if not isinstance(self.metadata, Mapping):
            raise TypeError('metadata must be a mapping')
        metadata = _json_metadata(self.metadata)
        from dd_research_runtime.payload_limits import check_document
        size_fields = dict(fields)
        for name in ('published_at','independence_cluster'):
            if getattr(self,name) is not None:
                size_fields[name] = getattr(self,name)
        check_document(size_fields,metadata)

    def to_evidence_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "source_id": self.source_id,
            "finding": self.passage,
            "location": self.content_location,
            "provenance": self.provenance,
            "synthetic": self.synthetic,
            "independence_cluster": self.independence_cluster,
            "metadata": {
                **_json_metadata(self.metadata),
                "title": self.title,
                "publisher": self.publisher,
                "url": self.url,
                "retrieved_at": self.retrieved_at,
                "published_at": self.published_at,
            },
        }
