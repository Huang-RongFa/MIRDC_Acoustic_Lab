from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=200)]
Number = Annotated[float, Field(ge=0, le=1000000, allow_inf_nan=False)]


class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    machine_code: Text
    machine_name: Text
    machine_model: Text
    material: Text
    material_spec: Text
    workpiece_code: Text
    tool_type: Text
    tool_material: Text
    tool_diameter_mm: Annotated[float, Field(gt=0, le=1000)]
    tool_flutes: Annotated[int, Field(ge=1, le=100)]
    tool_overhang_mm: Number
    tool_setup: Text
    spindle_rpm: Number
    feed_mm_min: Number
    axial_depth_mm: Number
    radial_width_mm: Number
    process: Text
    coolant: Text
    toolpath: Text
    nc_program: Text


class Finish(BaseModel):
    chunk_count: int = Field(ge=1, le=10000000)
    client_ms: float = Field(ge=0, allow_inf_nan=False)
    interrupted: bool = False
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class CatalogItem(BaseModel):
    kind: Literal['machines','materials','tools','setups','presets']
    name: Text
    values: Conditions
