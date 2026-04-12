import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import transform as shp_transform
from pyproj import Transformer
from typing import List, Tuple
import geopandas as gpd

def rect_bounds_to_corners(bounds) -> np.ndarray:
    xmin, ymin, xmax, ymax = bounds
    return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=float)

def homography_from_4pts(src4: np.ndarray, dst4: np.ndarray) -> np.ndarray:

    def A_row(x, y, X, Y):
        return np.array([[x, y, 1, 0, 0, 0, -X * x, -X * y, -X], [0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y]])
    A = np.vstack([A_row(x, y, X, Y) for (x, y), (X, Y) in zip(src4, dst4)])
    _, _, vh = np.linalg.svd(A)
    H = vh[-1, :].reshape(3, 3)
    return H / H[2, 2]

def apply_H_to_xy(x: float, y: float, H: np.ndarray) -> Tuple[float, float]:
    v = np.array([x, y, 1.0])
    w = H @ v
    return (w[0] / w[2], w[1] / w[2])

def transform_geometry_with_homography(geom, H: np.ndarray):

    def transform_coords(x, y):
        return apply_H_to_xy(x, y, H)
    return shp_transform(transform_coords, geom)

def get_region_bounds_from_outline(outline_path: str) -> List[float]:
    gdf = gpd.read_file(outline_path)
    return gdf.total_bounds.tolist()

def create_homography_for_region(outline_shapefile: str, rect4_pixels: List[Tuple[int, int]]) -> np.ndarray:
    src_bounds = get_region_bounds_from_outline(outline_shapefile)
    src4 = rect_bounds_to_corners(src_bounds)
    dst4 = np.array(rect4_pixels, dtype=float)
    return homography_from_4pts(src4, dst4)

def transform_geodataframe_with_homography(gdf: gpd.GeoDataFrame, H: np.ndarray) -> gpd.GeoDataFrame:
    transformed_geoms = gdf.geometry.apply(lambda geom: transform_geometry_with_homography(geom, H))
    return gpd.GeoDataFrame(gdf.drop(columns='geometry'), geometry=transformed_geoms, crs=None)
