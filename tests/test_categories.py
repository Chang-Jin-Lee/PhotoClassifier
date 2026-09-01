from dataclasses import replace

from photoclassifier.categories import (
    CanonicalAssignment,
    MergeKind,
    apply_aliases,
    build_merge_candidates,
    normalized_key,
    select_canonical_name,
)


def test_exact_normalization_is_auto_merge() -> None:
    result = build_merge_candidates(["넥서스아니마", " 넥서스아니마 ", "NEXUS-ANIMA", "NEXUS_ANIMA"])
    groups = [set(item.names) for item in result if item.kind is MergeKind.AUTO]
    assert {"NEXUS-ANIMA", "NEXUS_ANIMA"} in groups
    assert {"넥서스아니마", " 넥서스아니마 "} in groups


def test_related_but_distinct_names_require_review() -> None:
    result = build_merge_candidates(["KOCCA 한국 공동관", "한국공동관인터뷰"])
    candidate = next(item for item in result if set(item.names) == {"KOCCA 한국 공동관", "한국공동관인터뷰"})
    assert candidate.kind is MergeKind.REVIEW


def test_aliases_are_applied_without_changing_source_record(scanned_media) -> None:
    media_record = replace(scanned_media[0], existing_category="실버 팰리스")
    mapped = apply_aliases([media_record], {"실버 팰리스": "실버팰리스"})
    assert mapped == [CanonicalAssignment("media-1", "실버팰리스")]
    assert media_record.existing_category == "실버 팰리스"


def test_normalization_and_canonical_selection() -> None:
    assert normalized_key(" NEXUS__-ANIMA. ") == "nexus anima"
    assert select_canonical_name([" foo-bar ", "foo bar", "foo-bar"]) == "foo-bar"
