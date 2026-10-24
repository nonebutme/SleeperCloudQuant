"""Stage 89 data retention policy.

This module is deliberately policy-only.  It never deletes data.  Cleanup jobs
must obtain separate approval and must record the affected asset and version.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RetentionRule:
    category: str
    minimum_days: int | None
    disposition: str
    automatic_cleanup: bool
    notes: str


RETENTION_RULES = (
    RetentionRule(
        "authoritative_business_evidence",
        None,
        "retain",
        False,
        "F1-F6 authoritative facts and results are retained by default.",
    ),
    RetentionRule(
        "task_and_quality_audit",
        365,
        "archive_candidate",
        False,
        "Archive only after an approved job proves that referenced evidence remains available.",
    ),
    RetentionRule(
        "rebuildable_cache",
        30,
        "cleanup_candidate",
        False,
        "Delete only when lineage identifies a reproducible authoritative source.",
    ),
    RetentionRule(
        "deprecated_compatibility",
        None,
        "retain_until_migration_acceptance",
        False,
        "Compatibility data remains until consumer migration and rollback acceptance are complete.",
    ),
    RetentionRule(
        "stage89_runtime_migration_source",
        None,
        "retain_read_only",
        False,
        "Keep the tmp source and pre-promotion backup through formal acceptance; no automatic removal.",
    ),
)


def retention_policy() -> list[dict[str, object]]:
    """Return the auditable, side-effect-free retention policy."""

    return [asdict(rule) for rule in RETENTION_RULES]
