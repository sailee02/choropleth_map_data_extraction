"""
Homography transformation utilities for mapping shapefile coordinates to pixel coordinates.
Uses 4-point homography to map from geographic bounds to pixel rect4.
"""

import numpy as np
from typing import Tuple, List
from shapely.geometry import Point, LineString, Polygon, MultiLineString, MultiPolygon
from shapely.ops import transform as shp_transform
import geopandas as gpd


def rect_bounds_to_corners(bounds: Tuple[float, float, float, float], is_geographic: bool = True) -> np.ndarray:
    """
    Convert bounding box [xmin, ymin, xmax, ymax] to four corners (clockwise).
    
    Args:
        bounds: [xmin, ymin, xmax, ymax]
        is_geographic: If True, ymax is north (geographic coords). If False, ymin is top (pixel coords).
    
    Returns:
        Corners in order: TL, TR, BR, BL (clockwise)
        For geographic: TL=(xmin, ymax), TR=(xmax, ymax), BR=(xmax, ymin), BL=(xmin, ymin)
        For pixel: TL=(xmin, ymin), TR=(xmax, ymin), BR=(xmax, ymax), BL=(xmin, ymax)
    """
    xmin, ymin, xmax, ymax = bounds
    if is_geographic:
        # Geographic: Y increases northward, so top (north) has larger Y
        return np.array([
            [xmin, ymax],  # Top-left (north-west)
            [xmax, ymax],  # Top-right (north-east)
            [xmax, ymin],  # Bottom-right (south-east)
            [xmin, ymin],  # Bottom-left (south-west)
        ], dtype=float)
    else:
        # Pixel: Y increases downward, so top has smaller Y
        return np.array([
            [xmin, ymin],  # Top-left
            [xmax, ymin],  # Top-right
            [xmax, ymax],  # Bottom-right
            [xmin, ymax],  # Bottom-left
        ], dtype=float)


def affine_from_3pts(src3: np.ndarray, dst3: np.ndarray) -> np.ndarray:
    """
    Compute 2x3 affine transformation matrix from 3 point correspondences.
    
    Args:
        src3: Source points (3x2) in geographic/projected coordinates
        dst3: Destination points (3x2) in pixel coordinates
    
    Returns:
        2x3 affine transformation matrix A such that dst = A @ [src, 1]
    """
    # Build system: [x y 1 0 0 0] [a]   [X]
    #               [0 0 0 x y 1] [b] = [Y]
    #                              [c]
    #                              [d]
    #                              [e]
    #                              [f]
    A_rows = []
    b_vec = []
    for (x, y), (X, Y) in zip(src3, dst3):
        A_rows.append([x, y, 1, 0, 0, 0])
        A_rows.append([0, 0, 0, x, y, 1])
        b_vec.extend([X, Y])
    
    A = np.array(A_rows)
    b = np.array(b_vec)
    
    # Solve Ax = b using least squares
    params = np.linalg.lstsq(A, b, rcond=None)[0]
    
    # Reshape to 2x3 matrix
    affine_matrix = params.reshape(2, 3)
    return affine_matrix


def apply_affine_to_xy(x: float, y: float, A: np.ndarray) -> tuple:
    """Apply 2x3 affine transformation to a point."""
    src_vec = np.array([x, y, 1.0])
    dst_vec = A @ src_vec
    return (dst_vec[0], dst_vec[1])


def apply_affine_to_geometry(geom, A: np.ndarray):
    """Apply 2x3 affine transformation to a Shapely geometry."""
    from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
    
    if geom is None or geom.is_empty:
        return geom
    
    def transform_point(pt):
        x, y = pt.coords[0]
        x_new, y_new = apply_affine_to_xy(x, y, A)
        return Point(x_new, y_new)
    
    def transform_linestring(ls):
        coords = [apply_affine_to_xy(x, y, A) for x, y in ls.coords]
        return LineString(coords)
    
    def transform_polygon(poly):
        exterior = transform_linestring(poly.exterior)
        interiors = [transform_linestring(interior) for interior in poly.interiors]
        return Polygon(exterior, interiors)
    
    geom_type = geom.geom_type
    
    if geom_type == "Point":
        return transform_point(geom)
    elif geom_type == "LineString":
        return transform_linestring(geom)
    elif geom_type == "Polygon":
        return transform_polygon(geom)
    elif geom_type == "MultiPoint":
        return MultiPoint([transform_point(pt) for pt in geom.geoms])
    elif geom_type == "MultiLineString":
        return MultiLineString([transform_linestring(ls) for ls in geom.geoms])
    elif geom_type == "MultiPolygon":
        return MultiPolygon([transform_polygon(poly) for poly in geom.geoms])
    else:
        # Fallback
        coords = [apply_affine_to_xy(x, y, A) for x, y in geom.coords]
        if len(coords) == 1:
            return Point(coords[0])
        elif len(coords) == 2:
            return LineString(coords)
        else:
            return Polygon(coords)


def homography_from_4pts(src4: np.ndarray, dst4: np.ndarray) -> np.ndarray:
    """
    Compute 3x3 homography matrix H that maps src4 → dst4.
    
    Args:
        src4: Source points (4x2) in geographic/projected coordinates
        dst4: Destination points (4x2) in pixel coordinates
    
    Returns:
        3x3 homography matrix H (normalized so H[2,2] = 1)
    """
    def A_row(x, y, X, Y):
        """Build two rows of the A matrix for one point correspondence."""
        return np.array([
            [x, y, 1, 0, 0, 0, -X*x, -X*y, -X],
            [0, 0, 0, x, y, 1, -Y*x, -Y*y, -Y]
        ])
    
    # Build the full A matrix (8x9)
    A_rows = []
    for (x, y), (X, Y) in zip(src4, dst4):
        A_rows.append(A_row(x, y, X, Y))
    A = np.vstack(A_rows)
    
    # Solve Ah=0 using SVD (h is the last column of V^T)
    _, _, vh = np.linalg.svd(A)
    H = vh[-1, :].reshape(3, 3)
    
    # Normalize so H[2,2] = 1
    return H / H[2, 2]


def apply_H_to_xy(x: float, y: float, H: np.ndarray) -> Tuple[float, float]:
    """
    Apply homography H to a single (x, y) point.
    
    Returns:
        (x', y') in pixel coordinates
    """
    v = np.array([x, y, 1.0])
    w = H @ v
    return (w[0] / w[2], w[1] / w[2])


def apply_homography_to_geometry(geom, H: np.ndarray):
    """
    Apply homography H to a Shapely geometry.
    
    Args:
        geom: Shapely geometry (Point, LineString, Polygon, etc.)
        H: 3x3 homography matrix
    
    Returns:
        Transformed geometry
    """
    if geom is None or geom.is_empty:
        return geom
    
    def transform_point(pt):
        x, y = pt.coords[0]
        x_new, y_new = apply_H_to_xy(x, y, H)
        return Point(x_new, y_new)
    
    def transform_linestring(ls):
        coords = [apply_H_to_xy(x, y, H) for x, y in ls.coords]
        return LineString(coords)
    
    def transform_polygon(poly):
        exterior = transform_linestring(poly.exterior)
        interiors = [transform_linestring(interior) for interior in poly.interiors]
        return Polygon(exterior, interiors)
    
    geom_type = geom.geom_type
    
    if geom_type == "Point":
        return transform_point(geom)
    elif geom_type == "LineString":
        return transform_linestring(geom)
    elif geom_type == "Polygon":
        return transform_polygon(geom)
    elif geom_type == "MultiPoint":
        return type(geom)([transform_point(pt) for pt in geom.geoms])
    elif geom_type == "MultiLineString":
        return MultiLineString([transform_linestring(ls) for ls in geom.geoms])
    elif geom_type == "MultiPolygon":
        return MultiPolygon([transform_polygon(poly) for poly in geom.geoms])
    else:
        # Fallback: try to transform coordinates directly
        coords = [apply_H_to_xy(x, y, H) for x, y in geom.coords]
        if len(coords) == 1:
            return Point(coords[0])
        elif len(coords) == 2:
            return LineString(coords)
        else:
            return Polygon(coords)


def transform_gdf_with_homography(
    gdf: gpd.GeoDataFrame,
    src_bounds: Tuple[float, float, float, float],
    dst_rect4: List[Tuple[int, int]],
) -> gpd.GeoDataFrame:
    """
    Transform a GeoDataFrame using homography from source bounds to destination rect4.
    
    CRITICAL: Uses ONLY rect4 dimensions, NOT whole image dimensions.
    This prevents mixing frames that causes global rescaling bugs.
    
    Args:
        gdf: GeoDataFrame in source CRS (should be EPSG:5070 for Albers projection)
        src_bounds: Source bounding box [xmin, ymin, xmax, ymax] in gdf's CRS
        dst_rect4: Destination rectangle as 4 corners [(x1,y1), (x2,y2), (x3,y3), (x4,y4)] clockwise
    
    Returns:
        Transformed GeoDataFrame in pixel coordinates (no CRS)
    """
    # Extract rect4 dimensions (NOT whole image dimensions)
    x1, y1 = dst_rect4[0]  # Top-left
    x2, y2 = dst_rect4[2]  # Bottom-right
    W_rect = x2 - x1
    H_rect = y2 - y1
    
    # Shapefile native projected bounds
    xmin, ymin, xmax, ymax = src_bounds
    src_w = xmax - xmin
    src_h = ymax - ymin
    
    # Compute scale factors using RECT dimensions only
    sx = W_rect / src_w if src_w > 0 else 0
    sy = H_rect / src_h if src_h > 0 else 0
    
    # Affine transformation matrix for shapely.affinity.affine_transform
    # Format: [a, b, d, e, xoff, yoff]
    # [[a, b, xoff],
    #  [d, e, yoff],
    #  [0, 0, 1   ]]
    # Y goes down in image pixels -> flip Y with -sy and anchor at y2 (bottom)
    A = [sx, 0, 0, -sy, x1 - xmin * sx, y2 + ymin * sy]
    
    # Apply affine transformation
    from shapely.affinity import affine_transform
    gdf_px = gdf.copy()
    gdf_px["geometry"] = gdf_px.geometry.apply(
        lambda geom: affine_transform(geom, A)
    )
    gdf_px.crs = None  # Remove CRS since we're in pixel space
    
    return gdf_px

