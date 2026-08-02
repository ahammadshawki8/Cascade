"""
CASCADE Track B - Lambda Worker Handler
Day 9 COMPLETE: Lambda entry point with SQS and sweeper handling

Entry point for AWS Lambda worker.
Handles SQS events and EventBridge sweeper events.
"""

import asyncio
import json
import os
from typing import Any
from uuid import uuid4

from .jobs import job_compile, job_rule_changed, job_relearn, job_recheck


# Job dispatch map
JOB_HANDLERS = {
    "compile": job_compile,
    "rule_changed": job_rule_changed,
    "relearn": job_relearn,
    "recheck": job_recheck
}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    AWS Lambda entry point.
    
    Handles two event types:
    1. SQS events (from outbox publish)
    2. EventBridge sweeper (every 60s)
    
    Args:
        event: Lambda event dict
        context: Lambda context
    
    Returns:
        Response dict with statusCode
    """
    # Detect event type
    if "Records" in event:
        # SQS batch
        return asyncio.run(_handle_sqs_batch(event))
    elif event.get("source") == "aws.events":
        # EventBridge sweeper
        return asyncio.run(_handle_sweeper_event())
    else:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Unknown event type"})
        }


async def _handle_sqs_batch(event: dict) -> dict[str, Any]:
    """
    Process batch of SQS messages.
    
    Args:
        event: SQS batch event
    
    Returns:
        Response with batch failures
    """
    from db import Database
    
    db = Database(os.getenv("DATABASE_URL"))
    batch_failures = []
    
    try:
        for record in event["Records"]:
            try:
                await handle_sqs_event(record, db)
            except Exception as e:
                # Log error and add to batch failures for retry
                print(f"Error processing record {record.get('messageId')}: {e}")
                batch_failures.append({
                    "itemIdentifier": record.get("messageId")
                })
        
        return {
            "statusCode": 200,
            "batchItemFailures": batch_failures
        }
    
    finally:
        await db.close()


async def handle_sqs_event(record: dict, db) -> None:
    """
    Process single SQS message.
    
    Steps:
    1. Parse message body
    2. Claim outbox row (idempotent)
    3. Dispatch to appropriate job
    4. Mark outbox processed
    
    Args:
        record: SQS record
        db: Database connection
    """
    import boto3
    
    # Parse message
    body = json.loads(record["body"])
    event_id = body.get("event_id")
    
    if not event_id:
        raise ValueError("Missing event_id in message")
    
    # Claim outbox row (idempotent)
    worker_id = f"lambda-{record.get('messageId', uuid4())}"
    claimed = await claim_outbox(event_id, worker_id, db)
    
    if not claimed:
        # Already claimed by another worker - skip
        return
    
    # Load outbox row
    rows = await db.q(
        "SELECT kind, payload FROM outbox WHERE event_id = %s",
        (event_id,)
    )
    
    if not rows:
        raise ValueError(f"Outbox row {event_id} not found")
    
    kind = rows[0]["kind"]
    payload = rows[0]["payload"]
    
    # Dispatch to job handler
    if kind not in JOB_HANDLERS:
        raise ValueError(f"Unknown job kind: {kind}")
    
    await JOB_HANDLERS[kind](payload, db)
    
    # Mark processed
    await db.q(
        "UPDATE outbox SET processed_at = NOW() WHERE event_id = %s",
        (event_id,)
    )


async def _handle_sweeper_event() -> dict[str, Any]:
    """
    EventBridge sweeper wrapper.
    
    Returns:
        Response dict
    """
    from db import Database
    
    db = Database(os.getenv("DATABASE_URL"))
    
    try:
        await handle_sweeper(db)
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "sweeper_complete"})
        }
    
    finally:
        await db.close()


async def handle_sweeper(db) -> None:
    """
    EventBridge sweeper: process orphaned outbox rows.
    
    Scans for unprocessed rows >30s old.
    Publishes to SQS.
    
    Args:
        db: Database connection
    """
    import boto3
    
    # Query orphaned outbox rows (unprocessed >30s old)
    rows = await db.q(
        """
        SELECT event_id 
        FROM outbox 
        WHERE processed_at IS NULL 
          AND created_at < NOW() - INTERVAL '30 seconds'
        LIMIT 100
        """
    )
    
    if not rows:
        return
    
    # Publish to SQS
    queue_url = os.getenv("CASCADE_QUEUE_URL")
    if not queue_url:
        # Local mode - no SQS
        return
    
    try:
        sqs = boto3.client('sqs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        
        for row in rows:
            event_id = row["event_id"]
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps({"event_id": event_id})
            )
    
    except Exception as e:
        # Log but don't fail - next sweep will retry
        print(f"Sweeper SQS publish error: {e}")


async def claim_outbox(event_id: str, worker_id: str, db) -> bool:
    """
    Idempotent outbox claim.
    
    SQL:
        UPDATE outbox 
        SET claimed_at = NOW(), claimed_by = $2
        WHERE event_id = $1 AND claimed_at IS NULL
        RETURNING event_id
    
    Args:
        event_id: Event to claim
        worker_id: Worker identifier
        db: Database connection
    
    Returns:
        True if claimed, False if already claimed
    """
    rows = await db.q(
        """
        UPDATE outbox 
        SET claimed_at = NOW(), claimed_by = %s
        WHERE event_id = %s AND claimed_at IS NULL
        RETURNING event_id
        """,
        (worker_id, event_id)
    )
    
    return len(rows) > 0
