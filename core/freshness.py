"""
CASCADE Track B - Freshness Checking
Day 5 COMPLETE: Point-of-use staleness detection

Authoritative freshness via provenance join (D1).
NEVER returns a bool - always returns FreshnessResult with stale rule details.

This is THE source of truth for staleness. status_cache is UI convenience only.
"""

from uuid import UUID

from .models import FreshnessResult, StaleRule


async def check_freshness(playbook_id: UUID, db) -> FreshnessResult:
    """
    Check if playbook is fresh via provenance join.
    
    CRITICAL SQL (D1 - authoritative staleness definition):
        SELECT d.rule_key, d.rule_version AS expected, r.version AS actual
        FROM playbook_deps d
        JOIN rules r ON d.rule_key = r.rule_key AND r.valid_to IS NULL
        WHERE d.playbook_id = $1 AND d.rule_version != r.version
    
    Empty result = fresh (all deps match head versions)
    Any rows = stale (at least one dep outdated)
    
    Args:
        playbook_id: Playbook to check
        db: Database connection
    
    Returns:
        FreshnessResult with is_fresh and list of stale rules
    """
    try:
        results = await db.q(
            """
            SELECT 
                d.rule_key,
                d.rule_version AS expected_version,
                r.version AS actual_version
            FROM playbook_deps d
            JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
            WHERE d.playbook_id = %s
              AND r.version != d.rule_version
            """,
            (str(playbook_id),)
        )
        
        if not results:
            # All dependencies match head versions → fresh
            return FreshnessResult(is_fresh=True, stale_rules=[])
        
        # Build stale rules list
        stale_rules = [
            StaleRule(
                rule_key=row["rule_key"],
                expected_version=row["expected_version"],
                actual_version=row["actual_version"]
            )
            for row in results
        ]
        
        return FreshnessResult(is_fresh=False, stale_rules=stale_rules)
    
    except Exception as e:
        # On error, assume stale (fail-safe)
        return FreshnessResult(
            is_fresh=False,
            stale_rules=[
                StaleRule(
                    rule_key="error",
                    expected_version=0,
                    actual_version=0
                )
            ]
        )


async def bulk_check_freshness(playbook_ids: list[UUID], db) -> dict[UUID, FreshnessResult]:
    """
    Check freshness for multiple playbooks in one query.
    Used by worker for status_cache updates.
    
    Args:
        playbook_ids: List of playbooks to check
        db: Database connection
    
    Returns:
        Dict mapping playbook_id → FreshnessResult
    """
    if not playbook_ids:
        return {}
    
    id_strs = [str(pid) for pid in playbook_ids]
    
    try:
        results = await db.q(
            """
            SELECT 
                d.playbook_id,
                d.rule_key,
                d.rule_version AS expected_version,
                r.version AS actual_version
            FROM playbook_deps d
            JOIN rules r ON r.rule_key = d.rule_key AND r.valid_to IS NULL
            WHERE d.playbook_id = ANY(%s)
              AND r.version != d.rule_version
            """,
            (id_strs,)
        )
        
        # Group by playbook_id
        stale_map = {}
        for row in results:
            pid = row["playbook_id"]
            if isinstance(pid, str):
                pid = UUID(pid)
            
            if pid not in stale_map:
                stale_map[pid] = []
            
            stale_map[pid].append(
                StaleRule(
                    rule_key=row["rule_key"],
                    expected_version=row["expected_version"],
                    actual_version=row["actual_version"]
                )
            )
        
        # Build result map
        result_map = {}
        for pid in playbook_ids:
            if pid in stale_map:
                result_map[pid] = FreshnessResult(is_fresh=False, stale_rules=stale_map[pid])
            else:
                result_map[pid] = FreshnessResult(is_fresh=True, stale_rules=[])
        
        return result_map
    
    except Exception:
        # On error, mark all as stale (fail-safe)
        return {
            pid: FreshnessResult(
                is_fresh=False,
                stale_rules=[StaleRule(rule_key="error", expected_version=0, actual_version=0)]
            )
            for pid in playbook_ids
        }
