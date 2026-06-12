from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class MomentAnalysis(BaseModel):
    category: str = "daily"
    title: str = "今日小记录"
    objects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_food: bool = False
    calories_estimate: int | None = None
    portion_guess: str | None = None
    confidence: float = 0
    caption: str = ""
    mood_color: str = "#f3a6a6"
    ai_status: str = "ok"


class MomentRecord(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    title: str
    caption: str = ""
    category: str = "daily"
    is_food: bool = False
    calories_estimate: int | None = None
    portion_guess: str | None = None
    confidence: float = 0
    mood_color: str = "#f3a6a6"
    tags: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    notes: str = ""
    image_url: str
    thumbnail_url: str
    original_url: str
    ai_status: str = "pending"
    raw_analysis: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_analysis(
        cls,
        *,
        record_id: str,
        analysis: MomentAnalysis,
        image_url: str,
        thumbnail_url: str,
        original_url: str,
    ) -> "MomentRecord":
        now = datetime.now(timezone.utc)
        return cls(
            id=record_id,
            created_at=now,
            updated_at=now,
            title=analysis.title,
            caption=analysis.caption,
            category=analysis.category,
            is_food=analysis.is_food,
            calories_estimate=analysis.calories_estimate,
            portion_guess=analysis.portion_guess,
            confidence=analysis.confidence,
            mood_color=analysis.mood_color,
            tags=analysis.tags,
            objects=analysis.objects,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            original_url=original_url,
            ai_status=analysis.ai_status,
            raw_analysis=analysis.model_dump(),
        )


class RecordPatch(BaseModel):
    title: str | None = None
    caption: str | None = None
    category: str | None = None
    calories_estimate: int | None = None
    portion_guess: str | None = None
    tags: list[str] | None = None
    objects: list[str] | None = None
    notes: str | None = None
    mood_color: str | None = None


class SessionRequest(BaseModel):
    passcode: str = ""
