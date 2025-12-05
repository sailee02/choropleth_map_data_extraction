"""
Thin-Plate Spline (TPS) transformation utilities for non-linear warping.
TPS handles nonlinear stretching, curved boundaries, mapmaker distortions, 
non-uniform scaling, and slight perspective skew better than homography.
"""

import numpy as np
from typing import Tuple, List
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
from scipy.interpolate import RBFInterpolator
import warnings

# Suppress warnings from scipy
warnings.filterwarnings('ignore', category=RuntimeWarning)


def tps_transform_from_points(src_points: np.ndarray, dst_points: np.ndarray) -> callable:
    """
    Create a Thin-Plate Spline transformation function from control points.
    
    Args:
        src_points: Source control points (Nx2) in geographic/projected coordinates (EPSG:5070)
        dst_points: Destination control points (Nx2) in pixel coordinates
    
    Returns:
        A function f(x, y) -> (x', y') that transforms any point
    """
    # Ensure inputs are numpy arrays with correct shape
    src_points = np.asarray(src_points, dtype=float)
    dst_points = np.asarray(dst_points, dtype=float)
    
    # Validate shapes
    if src_points.ndim != 2 or src_points.shape[1] != 2:
        raise ValueError(f"src_points must be Nx2 array, got shape {src_points.shape}")
    if dst_points.ndim != 2 or dst_points.shape[1] != 2:
        raise ValueError(f"dst_points must be Nx2 array, got shape {dst_points.shape}")
    if len(src_points) != len(dst_points):
        raise ValueError(f"src_points and dst_points must have same length, got {len(src_points)} and {len(dst_points)}")
    if len(src_points) < 3:
        raise ValueError(f"TPS requires at least 3 control points, got {len(src_points)}")
    
    # Check for NaN or Inf values
    if np.any(np.isnan(src_points)) or np.any(np.isinf(src_points)):
        raise ValueError("src_points contains NaN or Inf values")
    if np.any(np.isnan(dst_points)) or np.any(np.isinf(dst_points)):
        raise ValueError("dst_points contains NaN or Inf values")
    
    # Use RBFInterpolator with thin-plate spline kernel
    # The 'thin_plate_spline' kernel is the TPS radial basis function
    try:
        # Extract X and Y coordinates from dst_points
        dst_x = dst_points[:, 0].flatten()
        dst_y = dst_points[:, 1].flatten()
        
        # Debug: Print shapes for troubleshooting
        print(f"  TPS Debug: src_points shape: {src_points.shape}, dst_points shape: {dst_points.shape}")
        print(f"  TPS Debug: dst_x shape: {dst_x.shape}, dst_y shape: {dst_y.shape}")
        
        # Validate extracted coordinates
        if len(dst_x) != len(src_points) or len(dst_y) != len(src_points):
            raise ValueError(f"Coordinate extraction failed: dst_x length {len(dst_x)}, dst_y length {len(dst_y)}, src_points length {len(src_points)}")
        
        # Interpolate X coordinates
        interp_x = RBFInterpolator(
            src_points,
            dst_x,
            kernel='thin_plate_spline',
            smoothing=0.0  # Exact interpolation at control points
        )
        
        # Interpolate Y coordinates
        interp_y = RBFInterpolator(
            src_points,
            dst_y,
            kernel='thin_plate_spline',
            smoothing=0.0  # Exact interpolation at control points
        )
        
        def transform_func(x, y):
            """Transform a single point (x, y) -> (x', y')"""
            point = np.array([[x, y]])
            x_new = interp_x(point)[0]
            y_new = interp_y(point)[0]
            return (float(x_new), float(y_new))
        
        return transform_func
    except Exception as e:
        # Fallback to simpler interpolation if scipy version doesn't support thin_plate_spline
        print(f"  ⚠️  TPS using thin_plate_spline kernel failed: {e}")
        print(f"  Falling back to cubic interpolation")
        
        # Fallback: use cubic RBF
        dst_x = dst_points[:, 0].flatten()
        dst_y = dst_points[:, 1].flatten()
        
        interp_x = RBFInterpolator(
            src_points,
            dst_x,
            kernel='cubic',
            smoothing=0.0
        )
        interp_y = RBFInterpolator(
            src_points,
            dst_y,
            kernel='cubic',
            smoothing=0.0
        )
        
        def transform_func(x, y):
            point = np.array([[x, y]])
            x_new = interp_x(point)[0]
            y_new = interp_y(point)[0]
            return (float(x_new), float(y_new))
        
        return transform_func


def apply_tps_to_xy(x: float, y: float, tps_func: callable) -> Tuple[float, float]:
    """Apply TPS transformation to a single (x, y) point."""
    return tps_func(x, y)


def apply_tps_to_geometry(geom, tps_func: callable):
    """
    Apply TPS transformation to a Shapely geometry.
    
    Args:
        geom: Shapely geometry (Point, LineString, Polygon, etc.)
        tps_func: TPS transformation function from tps_transform_from_points
    
    Returns:
        Transformed geometry
    """
    if geom is None or geom.is_empty:
        return geom
    
    def transform_point(pt):
        x, y = pt.coords[0]
        x_new, y_new = apply_tps_to_xy(x, y, tps_func)
        return Point(x_new, y_new)
    
    def transform_linestring(ls):
        coords = [apply_tps_to_xy(x, y, tps_func) for x, y in ls.coords]
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
        # Fallback: try to transform coordinates directly
        coords = [apply_tps_to_xy(x, y, tps_func) for x, y in geom.coords]
        if len(coords) == 1:
            return Point(coords[0])
        elif len(coords) == 2:
            return LineString(coords)
        else:
            return Polygon(coords)


def verify_tps_accuracy(tps_func: callable, src_points: np.ndarray, dst_points: np.ndarray) -> float:
    """
    Verify TPS transformation accuracy by transforming source points back.
    
    Returns:
        Maximum error in pixels
    """
    max_error = 0.0
    for src, dst in zip(src_points, dst_points):
        x, y = src
        x_transformed, y_transformed = tps_func(x, y)
        error = np.sqrt((x_transformed - dst[0])**2 + (y_transformed - dst[1])**2)
        max_error = max(max_error, error)
    return max_error

