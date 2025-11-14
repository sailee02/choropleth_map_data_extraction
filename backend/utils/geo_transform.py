import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import transform as shp_transform
from pyproj import Transformer
from typing import List, Tuple
import geopandas as gpd


def rect_bounds_to_corners(bounds) -> np.ndarray:
    """Convert [xmin,ymin,xmax,ymax] to 4 corners clockwise"""
    xmin, ymin, xmax, ymax = bounds
    return np.array([
        [xmin, ymin],  # TL
        [xmax, ymin],  # TR
        [xmax, ymax],  # BR
        [xmin, ymax],  # BL
    ], dtype=float)


def homography_from_4pts(src4: np.ndarray, dst4: np.ndarray) -> np.ndarray:
    """Compute 3x3 homography matrix H such that x' ~ H x (x,y,1)"""
    def A_row(x, y, X, Y):
        return np.array([[x, y, 1, 0, 0, 0, -X*x, -X*y, -X],
                         [0, 0, 0, x, y, 1, -Y*x, -Y*y, -Y]])

    A = np.vstack([A_row(x, y, X, Y) for (x, y), (X, Y) in zip(src4, dst4)])
    # Solve Ah=0 with SVD
    _, _, vh = np.linalg.svd(A)
    H = vh[-1, :].reshape(3, 3)
    return H / H[2, 2]


def apply_H_to_xy(x: float, y: float, H: np.ndarray) -> Tuple[float, float]:
    """Apply homography to a single point"""
    v = np.array([x, y, 1.0])
    w = H @ v
    return (w[0] / w[2], w[1] / w[2])


def transform_geometry_with_homography(geom, H: np.ndarray):
    """Apply homography transformation to any shapely geometry"""
    def transform_coords(x, y):
        return apply_H_to_xy(x, y, H)
    return shp_transform(transform_coords, geom)


def get_region_bounds_from_outline(outline_path: str) -> List[float]:
    """Get tight bounds [xmin,ymin,xmax,ymax] from outline shapefile"""
    gdf = gpd.read_file(outline_path)
    return gdf.total_bounds.tolist()  # [xmin, ymin, xmax, ymax]


def create_homography_for_region(
    outline_shapefile: str,
    rect4_pixels: List[Tuple[int, int]]
) -> np.ndarray:
    """
    Create homography matrix to map from geographic coords to pixel coords

    Args:
        outline_shapefile: Path to outline shapefile
        rect4_pixels: 4 corners in pixel coordinates [(x1,y1),(x2,y2),(x3,y3),(x4,y4)]

    Returns:
        3x3 homography matrix
    """
    # Get source bounds from outline shapefile
    src_bounds = get_region_bounds_from_outline(outline_shapefile)
    src4 = rect_bounds_to_corners(src_bounds)

    # Destination is the rect4 in pixels
    dst4 = np.array(rect4_pixels, dtype=float)

    return homography_from_4pts(src4, dst4)


def transform_geodataframe_with_homography(gdf: gpd.GeoDataFrame, H: np.ndarray) -> gpd.GeoDataFrame:
    """Transform all geometries in a GeoDataFrame using homography"""
    transformed_geoms = gdf.geometry.apply(lambda geom: transform_geometry_with_homography(geom, H))
    return gpd.GeoDataFrame(gdf.drop(columns='geometry'), geometry=transformed_geoms, crs=None)
