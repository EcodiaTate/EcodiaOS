# api/endpoints/simula/github.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from systems.simula.git.pr_annotations import (
    format_proposal_comment,
    post_pr_comment,
    set_commit_status,
)

router = APIRouter(tags=["integrations"])


class PRCommentReq(BaseModel):
    repo: str = Field(..., description="owner/name")
    pr_number: int
    body: str | None = None
    proposal: dict[str, Any] | None = None  # if provided, body will be synthesized


@router.post("/integrations/github/comment")
async def gh_comment(req: PRCommentReq) -> dict[str, Any]:
    body = req.body
    if not body and req.proposal:
        try:
            body = format_proposal_comment(req.proposal)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"format failed: {e!r}")
    if not body:
        raise HTTPException(status_code=400, detail="body or proposal required")
    try:
        out = await post_pr_comment(req.repo, req.pr_number, body)
        return {"status": "success", "result": out}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"post failed: {e!r}")


class CommitStatusReq(BaseModel):
    repo: str = Field(..., description="owner/name")
    sha: str
    state: str = Field(..., pattern="^(error|failure|pending|success)$")
    context: str = "simula/hygiene"
    description: str = ""
    target_url: str | None = None


@router.post("/integrations/github/status")
async def gh_status(req: CommitStatusReq) -> dict[str, Any]:
    try:
        out = await set_commit_status(
            repo=req.repo,
            sha=req.sha,
            state=req.state,
            context=req.context,
            description=req.description,
            target_url=req.target_url,
        )
        return {"status": "success", "result": out}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"status failed: {e!r}")
