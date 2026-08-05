"""
Stage 2 Pydantic Schemas: Sub-Query to Chapter Candidate Batched Mapping
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Stage2VerificationIssue(BaseModel):
    target: str = Field(description="Target sub-query ID or legal concept")
    issue: str = Field(description="Detailed explanation of Stage 2 mapping verification issue")
    feedback: str = Field(description="Actionable feedback for Stage 2 mapping agent correction")


class Stage2VerificationResult(BaseModel):
    status: str = Field(description="Status: 'VERIFIED' or 'RETRY'")
    issues: List[Stage2VerificationIssue] = Field(default_factory=list, description="List of mapping audit issues")
    feedback: str = Field(default="Stage 2 sub-query mapping audit complete.", description="Overall summary feedback")
    batched_mapping_response: Optional[Any] = Field(default=None, description="Verified Stage2BatchedMappingResponse")
