import numpy as np
from typing import Tuple, List
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon, GeometryCollection
from scipy.interpolate import RBFInterpolator
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

def tps_transform_from_points(src_points: np.ndarray, dst_points: np.ndarray) -> callable:
    src_points = np.asarray(src_points, dtype=float)
    dst_points = np.asarray(dst_points, dtype=float)
    if src_points.ndim != 2 or src_points.shape[1] != 2:
        raise ValueError(f'src_points must be Nx2 array, got shape {src_points.shape}')
    if dst_points.ndim != 2 or dst_points.shape[1] != 2:
        raise ValueError(f'dst_points must be Nx2 array, got shape {dst_points.shape}')
    if len(src_points) != len(dst_points):
        raise ValueError(f'src_points and dst_points must have same length, got {len(src_points)} and {len(dst_points)}')
    if len(src_points) < 3:
        raise ValueError(f'TPS requires at least 3 control points, got {len(src_points)}')
    if np.any(np.isnan(src_points)) or np.any(np.isinf(src_points)):
        raise ValueError('src_points contains NaN or Inf values')
    if np.any(np.isnan(dst_points)) or np.any(np.isinf(dst_points)):
        raise ValueError('dst_points contains NaN or Inf values')
    dst_x = dst_points[:, 0].flatten()
    dst_y = dst_points[:, 1].flatten()
    print(f'  TPS Debug: src_points shape: {src_points.shape}, dst_points shape: {dst_points.shape}')
    print(f'  TPS Debug: dst_x shape: {dst_x.shape}, dst_y shape: {dst_y.shape}')
    if len(dst_x) != len(src_points) or len(dst_y) != len(src_points):
        raise ValueError(f'Coordinate extraction failed: dst_x length {len(dst_x)}, dst_y length {len(dst_y)}, src_points length {len(src_points)}')
    kernels_to_try = [('thin_plate_spline', 'Thin-Plate Spline (optimal for map distortions)'), ('multiquadric', 'Multiquadric RBF (good for non-uniform scaling)'), ('inverse_multiquadric', 'Inverse Multiquadric RBF (smooth interpolation)'), ('gaussian', 'Gaussian RBF (local distortions)'), ('cubic', 'Cubic RBF (fallback)')]
    last_error = None
    for kernel_name, kernel_desc in kernels_to_try:
        try:
            print(f'  🔄 Trying {kernel_desc}...')
            interp_x = RBFInterpolator(src_points, dst_x, kernel=kernel_name, smoothing=0.0)
            interp_y = RBFInterpolator(src_points, dst_y, kernel=kernel_name, smoothing=0.0)
            test_points = src_points
            test_x = interp_x(test_points)
            test_y = interp_y(test_points)
            max_error = 0.0
            for i, (expected_x, expected_y) in enumerate(dst_points):
                actual_x = test_x[i]
                actual_y = test_y[i]
                error = np.sqrt((actual_x - expected_x) ** 2 + (actual_y - expected_y) ** 2)
                max_error = max(max_error, error)
            if max_error < 1e-06:
                print(f'  ✓ Successfully using {kernel_desc}')
                print(f'    Interpolation accuracy: {max_error:.2e} pixels')

                def transform_func(x, y):
                    point = np.array([[x, y]])
                    x_new = interp_x(point)[0]
                    y_new = interp_y(point)[0]
                    return (float(x_new), float(y_new))
                return transform_func
            else:
                print(f'  ⚠️  {kernel_desc} interpolation error: {max_error:.2e} pixels (trying next method)')
                last_error = f'{kernel_name}: {max_error:.2e} pixels'
                continue
        except Exception as e:
            print(f'  ⚠️  {kernel_desc} failed: {str(e)}')
            last_error = f'{kernel_name}: {str(e)}'
            continue
    raise RuntimeError(f'All non-linear warping methods failed. Last error: {last_error}')

def apply_tps_to_xy(x: float, y: float, tps_func: callable) -> Tuple[float, float]:
    return tps_func(x, y)

def apply_tps_to_geometry(geom, tps_func: callable):
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
    elif geom_type == 'GeometryCollection':
        transformed = [apply_tps_to_geometry(g, tps_func) for g in geom.geoms if g is not None and (not g.is_empty)]
        if not transformed:
            return geom
        return GeometryCollection(transformed)
    else:
        if not hasattr(geom, 'coords') or geom.coords is None:
            return geom
        coords = [apply_tps_to_xy(x, y, tps_func) for x, y in geom.coords]
        if len(coords) == 1:
            return Point(coords[0])
        elif len(coords) == 2:
            return LineString(coords)
        else:
            return Polygon(coords)

def verify_tps_accuracy(tps_func: callable, src_points: np.ndarray, dst_points: np.ndarray) -> float:
    max_error = 0.0
    for src, dst in zip(src_points, dst_points):
        x, y = src
        x_transformed, y_transformed = tps_func(x, y)
        error = np.sqrt((x_transformed - dst[0]) ** 2 + (y_transformed - dst[1]) ** 2)
        max_error = max(max_error, error)
    return max_error
