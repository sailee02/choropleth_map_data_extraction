import numpy as np
from typing import Tuple, List
from shapely.geometry import Point, LineString, Polygon, MultiLineString, MultiPolygon
from shapely.ops import transform as shp_transform
import geopandas as gpd

def rect_bounds_to_corners(bounds: Tuple[float, float, float, float], is_geographic: bool=True) -> np.ndarray:
    xmin, ymin, xmax, ymax = bounds
    if is_geographic:
        return np.array([[xmin, ymax], [xmax, ymax], [xmax, ymin], [xmin, ymin]], dtype=float)
    else:
        return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=float)

def affine_from_3pts(src3: np.ndarray, dst3: np.ndarray) -> np.ndarray:
    A_rows = []
    b_vec = []
    for (x, y), (X, Y) in zip(src3, dst3):
        A_rows.append([x, y, 1, 0, 0, 0])
        A_rows.append([0, 0, 0, x, y, 1])
        b_vec.extend([X, Y])
    A = np.array(A_rows)
    b = np.array(b_vec)
    params = np.linalg.lstsq(A, b, rcond=None)[0]
    affine_matrix = params.reshape(2, 3)
    return affine_matrix

def apply_affine_to_xy(x: float, y: float, A: np.ndarray) -> tuple:
    src_vec = np.array([x, y, 1.0])
    dst_vec = A @ src_vec
    return (dst_vec[0], dst_vec[1])

def apply_affine_to_geometry(geom, A: np.ndarray):
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
    if geom_type == 'Point':
        return transform_point(geom)
    elif geom_type == 'LineString':
        return transform_linestring(geom)
    elif geom_type == 'Polygon':
        return transform_polygon(geom)
    elif geom_type == 'MultiPoint':
        return MultiPoint([transform_point(pt) for pt in geom.geoms])
    elif geom_type == 'MultiLineString':
        return MultiLineString([transform_linestring(ls) for ls in geom.geoms])
    elif geom_type == 'MultiPolygon':
        return MultiPolygon([transform_polygon(poly) for poly in geom.geoms])
    else:
        coords = [apply_affine_to_xy(x, y, A) for x, y in geom.coords]
        if len(coords) == 1:
            return Point(coords[0])
        elif len(coords) == 2:
            return LineString(coords)
        else:
            return Polygon(coords)

def homography_from_4pts(src4: np.ndarray, dst4: np.ndarray) -> np.ndarray:

    def A_row(x, y, X, Y):
        return np.array([[x, y, 1, 0, 0, 0, -X * x, -X * y, -X], [0, 0, 0, x, y, 1, -Y * x, -Y * y, -Y]])
    A_rows = []
    for (x, y), (X, Y) in zip(src4, dst4):
        A_rows.append(A_row(x, y, X, Y))
    A = np.vstack(A_rows)
    _, _, vh = np.linalg.svd(A)
    H = vh[-1, :].reshape(3, 3)
    return H / H[2, 2]

def apply_H_to_xy(x: float, y: float, H: np.ndarray) -> Tuple[float, float]:
    v = np.array([x, y, 1.0])
    w = H @ v
    return (w[0] / w[2], w[1] / w[2])

def apply_homography_to_geometry(geom, H: np.ndarray):
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
    if geom_type == 'Point':
        return transform_point(geom)
    elif geom_type == 'LineString':
        return transform_linestring(geom)
    elif geom_type == 'Polygon':
        return transform_polygon(geom)
    elif geom_type == 'MultiPoint':
        return type(geom)([transform_point(pt) for pt in geom.geoms])
    elif geom_type == 'MultiLineString':
        return MultiLineString([transform_linestring(ls) for ls in geom.geoms])
    elif geom_type == 'MultiPolygon':
        return MultiPolygon([transform_polygon(poly) for poly in geom.geoms])
    else:
        coords = [apply_H_to_xy(x, y, H) for x, y in geom.coords]
        if len(coords) == 1:
            return Point(coords[0])
        elif len(coords) == 2:
            return LineString(coords)
        else:
            return Polygon(coords)

def transform_gdf_with_homography(gdf: gpd.GeoDataFrame, src_bounds: Tuple[float, float, float, float], dst_rect4: List[Tuple[int, int]]) -> gpd.GeoDataFrame:
    x1, y1 = dst_rect4[0]
    x2, y2 = dst_rect4[2]
    W_rect = x2 - x1
    H_rect = y2 - y1
    xmin, ymin, xmax, ymax = src_bounds
    src_w = xmax - xmin
    src_h = ymax - ymin
    sx = W_rect / src_w if src_w > 0 else 0
    sy = H_rect / src_h if src_h > 0 else 0
    A = [sx, 0, 0, -sy, x1 - xmin * sx, y2 + ymin * sy]
    from shapely.affinity import affine_transform
    gdf_px = gdf.copy()
    gdf_px['geometry'] = gdf_px.geometry.apply(lambda geom: affine_transform(geom, A))
    gdf_px.crs = None
    return gdf_px
