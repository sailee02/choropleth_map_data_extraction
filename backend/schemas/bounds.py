from typing import List, Optional, Tuple, Literal, Dict
from pydantic import BaseModel, Field

class ImageSize(BaseModel):
    width: int
    height: int
Point = Tuple[int, int]

class CanvasRect4(BaseModel):
    name: Literal['CONUS', 'Alaska', 'Hawaii']
    rect4: List[Point]

class CanvasEntry(BaseModel):
    name: str = Field(..., description='e.g., CONUS, AK, HI')
    bbox: Tuple[int, int, int, int]
    polygon: Optional[List[Tuple[int, int]]] = None
    confidence: float
    rect4: Optional[List[Point]] = None

class BoundsDoc(BaseModel):
    type: Literal['map_canvas_bounds'] = 'map_canvas_bounds'
    image_size: ImageSize
    canvases: List[CanvasRect4]

class MapCanvasBounds(BaseModel):
    type: Literal['map_canvas_bounds'] = 'map_canvas_bounds'
    image_size: ImageSize
    canvases: List[CanvasEntry]
