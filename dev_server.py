"""
CASCADE Track B - Development Server
Minimal FastAPI server for testing core modules independently
"""

import os
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import core modules
from core import contracts
from core.models import ImpactResult, CopilotAnswer

app = FastAPI(title="CASCADE Track B Dev Server")


# ============================================================================
# Request/Response Models
# ============================================================================

class TaskRequest(BaseModel):
    input: str


class TaskResponse(BaseModel):
    task_id: str
    status: str


class RuleChangeRequest(BaseModel):
    rule_key: str
    new_body: str
    new_params: dict
    actor: str


class CopilotRequest(BaseModel):
    question: str


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    stub_mode = os.getenv("CASCADE_STUB_MODE", "true").lower() == "true"
    return {
        "service": "CASCADE Track B",
        "version": "0.1.0",
        "stub_mode": stub_mode,
        "status": "ok"
    }


@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(req: TaskRequest):
    """Create and optionally run a task"""
    from uuid import uuid4
    
    task_id = uuid4()
    
    # Check for candidate playbook
    candidate = await contracts.retrieve(req.input)
    
    if candidate:
        # Check freshness
        freshness = await contracts.check_freshness(candidate.playbook_id)
        mode = "guided" if freshness.is_fresh else "explore"
    else:
        mode = "explore"
    
    return TaskResponse(
        task_id=str(task_id),
        status="queued",
    )


@app.post("/api/tasks/{task_id}/run")
async def run_task(task_id: str):
    """Execute a task"""
    try:
        task_uuid = UUID(task_id)
        await contracts.run_task(task_uuid)
        return {"status": "running", "task_id": task_id}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id")


@app.post("/api/rules/change", response_model=ImpactResult)
async def change_rule(req: RuleChangeRequest):
    """Change a policy rule"""
    result = await contracts.change_rule(
        req.rule_key,
        req.new_body,
        req.new_params,
        req.actor
    )
    return result


@app.post("/api/copilot/ask", response_model=CopilotAnswer)
async def ask_copilot(req: CopilotRequest):
    """Ask Ops Copilot a question"""
    result = await contracts.answer_analytics_question(req.question)
    return result


@app.get("/api/health/db")
async def health_db():
    """Check database connectivity"""
    try:
        import psycopg
        conn_str = os.getenv("DATABASE_URL")
        if not conn_str:
            return {"status": "error", "message": "DATABASE_URL not set"}
        
        conn = psycopg.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
