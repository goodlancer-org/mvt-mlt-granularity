"""Canonical semantic taxonomy for profile planning and styling.

The taxonomy keeps dataset-specific source types mapped into a stable set of
cross-dataset semantic kinds consumed by profile planning and UI styling.
"""

from __future__ import annotations

import re
from typing import Iterable


CANONICAL_SEMANTIC_KINDS = (
    "water",
    "land",
    "boundary",
    "transport",
    "place",
    "building",
    "infrastructure",
    "terrain",
    "unknown",
)

TYPE_FIELD_CANDIDATES = (
    "class",
    "fclass",
    "featurecla",
    "feature_class",
    "type",
    "subtype",
    "kind",
    "category",
    "landuse",
    "highway",
    "railway",
    "waterway",
    "natural",
    "place",
    "boundary",
    "admin_level",
)


def _tokenize(values: Iterable[str]) -> str:
    raw = " ".join(str(value or "") for value in values)
    lowered = raw.lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered)


def infer_semantic_kind(*values: str) -> str:
    """Return a canonical semantic kind from free-form source metadata."""
    text = _tokenize(values)
    if not text.strip():
        return "unknown"

    if re.search(r"\b(water|hydro|ocean|sea|lake|river|bay|canal|wetland|marsh|shore|coast)\b", text):
        return "water"
    if re.search(r"\b(boundary|border|admin|claim|jurisdiction|country|province|state)\b", text):
        return "boundary"
    if re.search(r"\b(road|street|route|path|rail|railway|transport|airport|port|harbor|bridge|tunnel)\b", text):
        return "transport"
    if re.search(r"\b(place|city|town|village|capital|settlement|label|locality)\b", text):
        return "place"
    if re.search(r"\b(building|footprint|structure|address)\b", text):
        return "building"
    if re.search(r"\b(infrastructure|utility|power|pipeline|telecom|facility)\b", text):
        return "infrastructure"
    if re.search(r"\b(terrain|relief|elevation|contour|geology|mountain|slope|landform)\b", text):
        return "terrain"
    if re.search(r"\b(land|park|forest|vegetation|urban|desert|grass|soil|ice|glacier|landuse)\b", text):
        return "land"
    return "unknown"
