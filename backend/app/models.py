"""Pydantic models: every agent input and output is structured data."""
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

ItemType = Literal["hotel", "transport", "activity", "food"]


class PlanRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    destination: Optional[str] = Field(default=None, max_length=60)
    budget: Optional[int] = Field(default=None, gt=0, le=10_000_000)
    days: Optional[int] = Field(default=None, ge=1, le=14)
    start_date: Optional[date] = None
    travelers: Optional[int] = Field(default=None, ge=1, le=12)
    interests: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def need_something(self):
        if not self.message.strip() and not self.destination:
            raise ValueError("Provide a message or a destination")
        return self


class ReviseRequest(BaseModel):
    feedback: str = Field(default="", max_length=1000)
    regenerate: bool = False


class ApproveRequest(BaseModel):
    version: Optional[int] = None


class ParsedRequest(BaseModel):
    destination: Optional[str] = None
    budget: Optional[int] = None
    days: int = 3
    travelers: int = 1
    start_date: Optional[str] = None
    stated_interests: list[str] = Field(default_factory=list)    # user said these
    assumed_interests: list[str] = Field(default_factory=list)   # AI / memory assumption
    food_preferences: list[str] = Field(default_factory=list)
    accommodation_style: Optional[str] = None
    missing: list[str] = Field(default_factory=list)

    @property
    def interests(self) -> list[str]:
        return list(dict.fromkeys(self.stated_interests + self.assumed_interests))


class Task(BaseModel):
    id: str
    agent: str
    description: str


class Strategy(BaseModel):
    tasks: list[Task]
    budget_mode: bool = False
    notes: list[str] = Field(default_factory=list)


class Item(BaseModel):
    id: str
    type: ItemType
    name: str
    cost: int
    desc: str = ""
    area: str = ""
    hours: float = 0
    tags: str = ""
    cap: int = 1
    source: str = ""
    estimate: bool = True


class Research(BaseModel):
    destination: str
    overview: str
    best_season: str
    transport_info: str
    tips: list[str]
    candidates: list[Item]
    sources: list[dict]
    disclaimer: str


class DayPick(BaseModel):
    activities: list[str] = Field(default_factory=list)
    meals: list[str] = Field(default_factory=list)


class Picks(BaseModel):
    hotel_id: str
    transport_id: str
    days: list[DayPick]


class ScheduledItem(BaseModel):
    time: str
    kind: Literal["activity", "meal", "travel"]
    item_id: Optional[str] = None
    name: str
    cost: int = 0
    duration_hours: float = 0
    area: str = ""


class DayPlan(BaseModel):
    day: int
    date: Optional[str] = None
    items: list[ScheduledItem]
    total_hours: float
    areas: list[str]
    day_cost: int


class BudgetBreakdown(BaseModel):
    accommodation: int
    transport: int
    food: int
    activities: int
    total: int
    budget: Optional[int]
    remaining: Optional[int]
    within_budget: bool
    expensive: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class Itinerary(BaseModel):
    destination: str
    travelers: int
    days: list[DayPlan]
    hotel: Item
    transport: Item
    picks: Picks
    cost: BudgetBreakdown
    notes: list[str] = Field(default_factory=list)


class Violation(BaseModel):
    kind: Literal["budget", "preference", "schedule"]
    message: str
    blocking: bool = True


class Review(BaseModel):
    approved: bool
    violations: list[Violation]
    feedback: str = ""
