"""Category-name normalization and conservative merge candidates."""

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
import re
import unicodedata
from typing import Mapping, Sequence

from .domain import MediaRecord


class MergeKind(StrEnum):
    AUTO = "auto"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class MergeCandidate:
    names: tuple[str, ...]
    kind: MergeKind


@dataclass(frozen=True, slots=True)
class CanonicalAssignment:
    media_id: str
    category: str


def normalized_key(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip().casefold()
    value = re.sub(r"[_\-\s]+", " ", value)
    return value.rstrip(" ._-")


def select_canonical_name(names: Sequence[str]) -> str:
    counts = Counter(name.strip() for name in names)
    return min(
        counts,
        key=lambda name: (-counts[name], name.count("_") + name.count("-"), len(name), name.casefold()),
    )


def _longest_common_substring(left: str, right: str) -> int:
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, 1):
            value = previous[index - 1] + 1 if left_char == right_char else 0
            current.append(value)
            longest = max(longest, value)
        previous = current
    return longest


def _review_match(left: str, right: str) -> bool:
    left_tokens, right_tokens = set(left.split()), set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0
    ratio = SequenceMatcher(None, left, right).ratio()
    common = _longest_common_substring(left.replace(" ", ""), right.replace(" ", ""))
    return jaccard >= 0.5 or ratio >= 0.72 or common >= 4


def build_merge_candidates(names: Sequence[str]) -> list[MergeCandidate]:
    """Return exact-key auto groups and distinct-key review pairs.

    Review candidates are informational only; callers must explicitly approve
    aliases before persisting them.
    """
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(normalized_key(name), []).append(name)
    result: list[MergeCandidate] = [
        MergeCandidate(tuple(group), MergeKind.AUTO)
        for group in groups.values()
        if len(group) > 1
    ]
    keys = list(groups)
    for index, left_key in enumerate(keys):
        for right_key in keys[index + 1 :]:
            if _review_match(left_key, right_key):
                result.append(MergeCandidate((groups[left_key][0], groups[right_key][0]), MergeKind.REVIEW))
    return result


def apply_aliases(records: Sequence[MediaRecord], aliases: Mapping[str, str]) -> list[CanonicalAssignment]:
    """Project aliases onto records without mutating their immutable source objects."""
    return [
        CanonicalAssignment(record.id, aliases.get(record.existing_category, record.existing_category))
        for record in records
        if record.existing_category is not None
    ]
