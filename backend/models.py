from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=200)]
Number = Annotated[float, Field(ge=0, le=1000000, allow_inf_nan=False)]


class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    machine_type: Text | None = None
    machine_id: UUID | None = None
    machine_code: Text | None = None
    machine_name: Text | None = None
    machine_model: Text | None = None
    material: Text | None = None
    material_spec: Text | None = None
    workpiece_code: Text | None = None
    tool_type: Text | None = None
    tool_material: Text | None = None
    tool_diameter_mm: Annotated[float, Field(gt=0, le=1000)] | None = None
    tool_flutes: Annotated[int, Field(ge=1, le=100)] | None = None
    tool_overhang_mm: Number | None = None
    tool_setup: Text | None = None
    spindle_rpm: Number | None = None
    feed_mm_min: Number | None = None
    axial_depth_mm: Number | None = None
    radial_width_mm: Number | None = None
    process: Text | None = None
    coolant: Text | None = None
    toolpath: Text | None = None
    nc_program: Text | None = None


class Finish(BaseModel):
    chunk_count: int = Field(ge=1, le=10000000)
    client_ms: float = Field(ge=0, allow_inf_nan=False)
    interrupted: bool = False
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class CatalogItem(BaseModel):
    kind: Literal['machines','materials','tools','setups','presets']
    name: Text
    values: Conditions
