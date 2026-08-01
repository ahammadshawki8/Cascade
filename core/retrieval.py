"""
CASCADE Track B - Vector Retrieval
Day 3 implementation target (Phase 1)
Day 5 completion (Phases 2-3)

Three-phase retrieval to prevent planner risk:
Phase 1: Pure ANN query with <-> operator (MUST use vector index)
Phase 2: PK lookup + metadata filter (status_cache)
Phase 3: Point-of-use freshness check

CRITICAL: Use L2 operator (<->) NOT cosine. Titan V2 with normalize=true makes them equivalent.
"""

from typing import Optional
from uuid import UUID

from .models import PlaybookCandidate


async def retrieve(task_text: str) -> Optional[PlaybookCandidate]:
    """
    Two-phase retrieval for playbook candidates.
    
    Phase 1: Pure ANN vector search (20 candidates)
    Phase 2: PK lookup + filter by status_cache
    
    Args:
        task_text: Natural language task description
    
    Returns:
        Best matching playbook or None if no good candidates
    """
    raise NotImplementedError("retrieve() - Day 3")


async def _phase1_ann_query(embedding: list[float], limit: int = 20) -> list[UUID]:
    """
    Phase 1: Pure vector ANN query.
    
    CRITICAL SQL:
        SELECT playbook_id, embedding <-> $1 AS dist 
        FROM playbooks 
        ORDER BY embedding <-> $1 
        LIMIT 20;
    
    MUST use <-> operator to hit pb_embed_idx index.
    
    Args:
        embedding: 1024-d query vector
        limit: Number of candidates
    
    Returns:
        List of playbook_ids ordered by distance
    """
    raise NotImplementedError("_phase1_ann_query() - Day 3")


async def _phase2_pk_filter(
    playbook_ids: list[UUID]
) -> list[PlaybookCandidate]:
    """
    Phase 2: PK lookup + metadata filtering.
    
    Filter by status_cache IN ('active', 'candidate', 'suspect').
    Calculate final distance for ranking.
    
    Args:
        playbook_ids: Candidates from Phase 1
    
    Returns:
        Filtered and scored candidates
    """
    raise NotImplementedError("_phase2_pk_filter() - Day 5")


async def dedup_check(embedding: list[float], threshold: float = 0.40) -> Optional[UUID]:
    """
    Check if a very similar playbook already exists.
    Used during compilation to prevent duplicates.
    
    Args:
        embedding: New playbook's embedding
        threshold: L2 distance threshold for "too similar"
    
    Returns:
        Existing playbook_id if duplicate found, else None
    """
    raise NotImplementedError("dedup_check() - Day 4")
