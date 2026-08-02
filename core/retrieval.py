"""
CASCADE Track B - Vector Retrieval
Day 3 COMPLETE: Phase 1 ANN query with Titan embeddings
Day 5: Phases 2-3 (metadata filter + freshness)

Three-phase retrieval to prevent planner risk:
Phase 1: Pure ANN query with <-> operator (MUST use vector index)
Phase 2: PK lookup + metadata filter (status_cache)
Phase 3: Point-of-use freshness check (in freshness.py)

CRITICAL: Use L2 operator (<->) NOT cosine. Titan V2 with normalize=true makes them equivalent.
L2 distance threshold: ≤0.85 for retrieval (tuned in Week 2)
"""

import json
import os
from typing import Optional
from uuid import UUID

from .models import PlaybookCandidate


# Retrieval threshold (L2 distance on unit vectors)
# Starting point: 0.85 ≈ cosine distance 0.36
# Will be tuned in Week 2 against seed task set
L2_RETRIEVAL_THRESHOLD = float(os.getenv("RETRIEVAL_L2_THRESHOLD", "0.85"))

# Dedup threshold for compilation
# 0.40 ≈ cosine distance 0.08 (very similar)
L2_DEDUP_THRESHOLD = float(os.getenv("DEDUP_L2_THRESHOLD", "0.40"))


async def retrieve(task_text: str, db, embed_client=None) -> Optional[PlaybookCandidate]:
    """
    Two-phase retrieval for playbook candidates.
    
    Phase 1: Pure ANN vector search (20 candidates)
    Phase 2: PK lookup + filter by status_cache + re-rank
    Phase 3: Freshness check (caller's responsibility)
    
    Args:
        task_text: Natural language task description
        db: Database connection
        embed_client: Titan embedding client
    
    Returns:
        Best matching playbook or None if no good candidates
    """
    # Embed query text
    if embed_client is None:
        from .llm import EmbedClient
        embed_client = EmbedClient()
    
    try:
        embedding = await embed_client.embed(task_text)
    except NotImplementedError:
        # Stub mode - return None (no retrieval)
        return None
    
    # Phase 1: Pure ANN query
    candidates_with_dist = await _phase1_ann_query(embedding, db, limit=20)
    
    if not candidates_with_dist:
        return None
    
    # Phase 2: PK lookup + filter + re-rank
    playbook_ids = [c["playbook_id"] for c in candidates_with_dist]
    dist_map = {c["playbook_id"]: c["dist"] for c in candidates_with_dist}
    
    filtered = await _phase2_pk_filter(playbook_ids, dist_map, db)
    
    if not filtered:
        return None
    
    # Take top candidate within threshold
    best = filtered[0]
    if best.distance <= L2_RETRIEVAL_THRESHOLD:
        return best
    
    return None


async def _phase1_ann_query(embedding: list[float], db, limit: int = 20) -> list[dict]:
    """
    Phase 1: Pure vector ANN query.
    
    CRITICAL SQL (MUST use <-> to hit index):
        SELECT playbook_id, embedding <-> $1 AS dist 
        FROM playbooks 
        ORDER BY embedding <-> $1 
        LIMIT 20;
    
    Args:
        embedding: 1024-d query vector
        db: Database connection
        limit: Number of candidates
    
    Returns:
        List of dicts with playbook_id and dist
    """
    # Convert embedding to PostgreSQL vector format
    # For psycopg, this would be: embedding_str = f"[{','.join(map(str, embedding))}]"
    
    try:
        results = await db.q(
            """
            SELECT playbook_id, embedding <-> %s::vector AS dist
            FROM playbooks
            ORDER BY embedding <-> %s::vector
            LIMIT %s
            """,
            (embedding, embedding, limit)
        )
        
        return [
            {"playbook_id": row["playbook_id"], "dist": row["dist"]}
            for row in results
        ]
    
    except Exception as e:
        # If vector operations not supported (stub mode), return empty
        if "vector" in str(e).lower() or "type" in str(e).lower():
            return []
        raise


async def _phase2_pk_filter(
    playbook_ids: list[UUID],
    dist_map: dict[UUID, float],
    db
) -> list[PlaybookCandidate]:
    """
    Phase 2: PK lookup + metadata filtering.
    
    Filter by status_cache IN ('active', 'candidate', 'suspect').
    Re-rank by distance ascending, then confidence descending.
    
    Args:
        playbook_ids: Candidates from Phase 1
        dist_map: Mapping of playbook_id → L2 distance
        db: Database connection
    
    Returns:
        Filtered and ranked candidates
    """
    if not playbook_ids:
        return []
    
    # Convert UUIDs to strings for SQL
    id_strs = [str(pid) for pid in playbook_ids]
    
    try:
        results = await db.q(
            """
            SELECT playbook_id, name, version, confidence, status_cache, domain
            FROM playbooks
            WHERE playbook_id = ANY(%s)
              AND status_cache IN ('active', 'candidate', 'suspect')
            """,
            (id_strs,)
        )
        
        # Build candidates with distance
        candidates = []
        for row in results:
            pid = row["playbook_id"]
            # Handle UUID type (might be string or UUID depending on driver)
            if isinstance(pid, str):
                pid = UUID(pid)
            
            distance = dist_map.get(pid, 999.0)
            
            candidates.append(PlaybookCandidate(
                playbook_id=pid,
                name=row["name"],
                version=row["version"],
                confidence=row["confidence"],
                distance=distance,
                status_cache=row["status_cache"]
            ))
        
        # Sort by distance ascending, then confidence descending
        candidates.sort(key=lambda c: (c.distance, -c.confidence))
        
        return candidates
    
    except Exception as e:
        # Graceful degradation
        return []


async def dedup_check(embedding: list[float], domain: str, db, embed_client=None) -> Optional[UUID]:
    """
    Check if a very similar playbook already exists.
    Used during compilation to prevent duplicates.
    
    Args:
        embedding: New playbook's embedding
        domain: Playbook domain
        db: Database connection
        embed_client: Not used (embedding already computed)
    
    Returns:
        Existing playbook_id if duplicate found, else None
    """
    try:
        # Find top-1 most similar in same domain
        results = await db.q(
            """
            SELECT playbook_id, embedding <-> %s::vector AS dist
            FROM playbooks
            WHERE domain = %s
            ORDER BY embedding <-> %s::vector
            LIMIT 1
            """,
            (embedding, domain, embedding)
        )
        
        if results and results[0]["dist"] < L2_DEDUP_THRESHOLD:
            return results[0]["playbook_id"]
        
        return None
    
    except Exception as e:
        # If vector ops not supported, skip dedup
        return None


# Utility: Generate EXPLAIN output for verification (Day 3 gate)
async def verify_vector_index(db) -> dict:
    """
    Run EXPLAIN on Phase 1 query to verify index usage.
    
    Returns:
        {"uses_index": bool, "plan": str, "error": str}
    """
    dummy_embedding = [0.0] * 1024  # Dummy vector for EXPLAIN
    
    try:
        # Get query plan
        results = await db.q(
            """
            EXPLAIN
            SELECT playbook_id, embedding <-> %s::vector AS dist
            FROM playbooks
            ORDER BY embedding <-> %s::vector
            LIMIT 20
            """,
            (dummy_embedding, dummy_embedding)
        )
        
        # Parse EXPLAIN output
        plan_text = "\n".join(row.get("QUERY PLAN", str(row)) for row in results)
        
        # Check if pb_embed_idx appears
        uses_index = "pb_embed_idx" in plan_text
        
        return {
            "uses_index": uses_index,
            "plan": plan_text,
            "error": None if uses_index else "Index pb_embed_idx NOT found in plan"
        }
    
    except Exception as e:
        return {
            "uses_index": False,
            "plan": "",
            "error": str(e)
        }
