from pydantic import BaseModel, Field


class SampleDataStatus(BaseModel):
    available: bool
    counts: dict[str, int] = Field(default_factory=dict)


class SampleDataDelete(BaseModel):
    confirmed: bool
