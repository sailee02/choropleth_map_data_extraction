from typing import List, Optional, Tuple, Literal, Dict

from pydantic import BaseModel, Field


class ImageSize(BaseModel):
    width: int
    height: int


# Point type: (x, y) in pixel coordinates
Point = Tuple[int, int]


class CanvasRect4(BaseModel):
    """Canvas rectangle defined by four corners in pixel coordinates (clockwise)."""
    name: Literal["CONUS", "Alaska", "Hawaii"]
    rect4: List[Point]  # [(x1,y1),(x2,y2),(x3,y3),(x4,y4)] clockwise: TL→TR→BR→BL


class CanvasEntry(BaseModel):
    """Legacy canvas entry for backward compatibility."""
    name: str = Field(..., description="e.g., CONUS, AK, HI")
    bbox: Tuple[int, int, int, int]  # [x0,y0,x1,y1] in pixels (top-left origin)
    polygon: Optional[List[Tuple[int, int]]] = None  # optional outline
    confidence: float
    # New: rect4 for precise four-corner mapping
    rect4: Optional[List[Point]] = None  # [(x1,y1),(x2,y2),(x3,y3),(x4,y4)] clockwise


class BoundsDoc(BaseModel):
    """New bounds document format using rect4."""
    type: Literal["map_canvas_bounds"] = "map_canvas_bounds"
    image_size: ImageSize
    canvases: List[CanvasRect4]


class MapCanvasBounds(BaseModel):
    """Legacy bounds format for backward compatibility."""
    type: Literal["map_canvas_bounds"] = "map_canvas_bounds"
    image_size: ImageSize
    canvases: List[CanvasEntry]


