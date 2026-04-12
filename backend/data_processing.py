import os
import re
import json
import copy
import math
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping
from PIL import Image, ImageOps
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from sklearn.metrics import pairwise_distances_argmin
from sklearn.cluster import KMeans
from affine import Affine
from shapely.affinity import translate as shp_translate
try:
    from services.bounds_store import get_bounds as get_bounds_for_upload
except Exception:
    from backend.services.bounds_store import get_bounds as get_bounds_for_upload
try:
    from utils.geo_align import fit_gdf_to_bbox_pixels, refine_alignment_with_edge_matching, fit_with_autoinset
except Exception:
    from backend.utils.geo_align import fit_gdf_to_bbox_pixels, refine_alignment_with_edge_matching, fit_with_autoinset
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_region_shapefile_path(region='conus', projection='4326'):
    shapefile_name = f'cb_2024_us_county_500k_{region}_epsg{projection}'
    return os.path.join(BASE_DIR, shapefile_name, f'{shapefile_name}.shp')

def _get_region_outline_path(region='conus', projection='4326'):
    base_name = f'cb_2024_us_county_500k_{region}_epsg{projection}'
    outline_folder = f'{base_name}_OUTLINE'
    return os.path.join(BASE_DIR, outline_folder, f'{region}_outline.shp')

def _get_shapefile_path(projection='4326', use_full=False):
    if projection == '4326':
        return os.path.join(BASE_DIR, 'cb_2024_us_county_500k_conus_epsg4326', 'cb_2024_us_county_500k_conus_epsg4326.shp')
    else:
        return os.path.join(BASE_DIR, 'cb_2024_us_county_500k_conus_epsg5070', 'cb_2024_us_county_500k_conus_epsg5070.shp')
SHAPEFILE_PATH = os.environ.get('SHAPEFILE_PATH', os.path.join(BASE_DIR, 'cb_2024_us_county_500k_conus', 'cb_2024_us_county_500k_conus.shp'))
FULL_SHAPEFILE_PATH = os.environ.get('FULL_SHAPEFILE_PATH', os.path.join(BASE_DIR, 'cb_2024_us_county_500k', 'cb_2024_us_county_500k.shp'))
DATA_DIR = os.environ.get('DATA_DIR', 'data')

def parse_legend_text(legend_text):
    parsed = []
    for line in legend_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            color_part, label = line.split(':', 1)
            label = label.strip()
        else:
            color_part = line
            label = ''
        color_part = color_part.strip()
        rgb = None
        if color_part.startswith('#'):
            hexval = color_part.lstrip('#')
            if len(hexval) == 6:
                r = int(hexval[0:2], 16)
                g = int(hexval[2:4], 16)
                b = int(hexval[4:6], 16)
                rgb = [r, g, b]
        else:
            parts = color_part.split(',')
            if len(parts) == 3:
                try:
                    rgb = [int(p.strip()) for p in parts]
                except ValueError:
                    continue
        if rgb:
            parsed.append((rgb, label))
    return parsed

def generate_data_driven_legend(rgb_values, n_bins=64):
    valid_rgbs = [rgb for rgb in rgb_values if rgb[0] is not None]
    if not valid_rgbs:
        return np.array([])
    rgb_array = np.array(valid_rgbs)
    quantiles = np.linspace(0, 1, n_bins + 1)
    r_quantiles = np.quantile(rgb_array[:, 0], quantiles)
    g_quantiles = np.quantile(rgb_array[:, 1], quantiles)
    b_quantiles = np.quantile(rgb_array[:, 2], quantiles)
    legend_colors = []
    for i in range(n_bins):
        r_val = int(r_quantiles[i])
        g_val = int(g_quantiles[i])
        b_val = int(b_quantiles[i])
        legend_colors.append([r_val, g_val, b_val])
    return np.array(legend_colors)

def rgb_leg(rgb_values, n_bins=64):
    return generate_data_driven_legend(rgb_values, n_bins)

def _extract_bin_values_from_legend(legend_area, num_bins, ocr_text_cache=None):
    try:
        import pytesseract
        text = ocr_text_cache if ocr_text_cache is not None else _ocr_numpy_rgb_to_string(legend_area)
        print(f'  📖 OCR (preprocessed) legend text: {text[:220]!r}...')
        rv, rl = _ranges_ordered_from_full_ocr_text(text, num_bins)
        if rv and rl and len(rl) == num_bins:
            print(f'  ✓ Ordered range parse ({num_bins} bins): {rl}')
            return (rv, rl)
        percent_range_pattern = r'(\d+\.?\d*)\s*%\s*(?:to|-|—)\s*(\d+\.?\d*)\s*%'
        percent_ranges = re.findall(percent_range_pattern, text, re.IGNORECASE)
        if percent_ranges and len(percent_ranges) >= num_bins:
            bin_values = []
            bin_labels = []
            for low, high in percent_ranges[:num_bins]:
                low_val = float(low)
                high_val = float(high)
                bin_values.append(high_val)
                bin_labels.append(f'{low_val:.2f}% to {high_val:.2f}%')
            print(f'  ✓ Extracted {len(bin_values)} bin values from percentage ranges: {bin_values}')
            print(f'  ✓ Extracted {len(bin_labels)} bin labels: {bin_labels}')
            return (bin_values, bin_labels)
        range_pattern = r'(\d+[.,]\d+)\s*[-–—]\s*(\d+[.,]\d+)'
        ranges = re.findall(range_pattern, text)
        if len(ranges) < num_bins:
            ranges = re.findall(r'(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)', text)
        if ranges and len(ranges) >= num_bins:
            bin_values = []
            bin_labels = []
            for low, high in ranges[:num_bins]:
                low_val = float(str(low).replace(',', '.'))
                high_val = float(str(high).replace(',', '.'))
                bin_values.append(high_val)
                bin_labels.append(_fmt_bin_range_label(low_val, high_val))
            print(f'  ✓ Extracted {len(bin_values)} bin values from legend ranges: {bin_values}')
            print(f'  ✓ Extracted {len(bin_labels)} bin labels: {bin_labels}')
            return (bin_values, bin_labels)
        numbers = re.findall(r'-?\d+[.,]?\d*', text)
        if len(numbers) >= num_bins:
            values = [float(n) for n in numbers[:num_bins]]
            labels = [str(n) for n in numbers[:num_bins]]
            print(f'  ✓ Extracted {len(values)} bin values from legend: {values}')
            print(f'  ✓ Extracted {len(labels)} bin labels: {labels}')
            return (values, labels)
        elif len(numbers) >= 2:
            values = [float(n) for n in numbers]
            min_val = min(values)
            max_val = max(values)
            ev, el = _equal_interval_bin_ranges(num_bins, min_val, max_val)
            if ev is None:
                return (None, None)
            bin_values, bin_labels = ev, el
            print(f'  ✓ Extracted min/max ({min_val}, {max_val}) and built {num_bins} equal bin ranges: {bin_labels}')
            return (bin_values, bin_labels)
    except ImportError:
        print('  ⚠️  pytesseract not available, cannot extract bin values from legend')
    except Exception as e:
        print(f'  ⚠️  Failed to extract bin values from legend: {str(e)}')
    return (None, None)


def _normalize_ocr_text(text):
    if not text:
        return ''
    t = ' '.join(text.split())
    for ch in ('–', '—', '−', '‐', '‑', '‒', '⁃'):
        t = t.replace(ch, '-')
    t = re.sub(r'\s*-\s*', '-', t)
    return t


def _fmt_bin_range_label(lo, hi):
    """Human-readable interval for CSV/geojson (e.g. 6.90-33.10)."""
    return f'{float(lo):.2f}-{float(hi):.2f}'


def _equal_interval_bin_ranges(num_bins, min_val, max_val):
    """
    n equal-width bins covering [min_val, max_val].
    Returns (bin_values, bin_labels) with labels like 'lo-hi' and values = bin upper edge.
    """
    if num_bins < 1 or max_val <= min_val:
        return None, None
    span = max_val - min_val
    bin_values = []
    bin_labels = []
    for i in range(num_bins):
        lo = min_val + span * (i / num_bins)
        hi = min_val + span * ((i + 1) / num_bins)
        bin_labels.append(_fmt_bin_range_label(lo, hi))
        bin_values.append(float(hi))
    return bin_values, bin_labels


def _legend_area_numeric_min_max(legend_area):
    """Use the same OCR pipeline as full-legend parse; return (min, max) over all numbers in the crop, or None."""
    if legend_area.size < 3:
        return None
    try:
        text = _ocr_numpy_rgb_to_string(legend_area)
        nums = re.findall(r'-?\d+[.,]?\d*', text)
        if len(nums) < 2:
            return None
        vals = [float(str(n).replace(',', '.')) for n in nums]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-12:
            return None
        return lo, hi
    except Exception:
        return None


def _all_bin_labels_are_placeholders(bin_labels):
    if not bin_labels:
        return False
    p = re.compile(r'^Bin\s*\d+\s*$', re.I)
    return all(p.match(str(lbl).strip()) for lbl in bin_labels)


def _parse_first_range_in_text(text):
    """Return (label_str, high_end_float_or_none) from OCR snippet next to one swatch."""
    if not text:
        return None, None
    t = _normalize_ocr_text(text)
    pct = re.search(r'(\d+\.?\d*)\s*%\s*(?:to|-)\s*(\d+\.?\d*)\s*%', t, re.IGNORECASE)
    if pct:
        lo, hi = pct.group(1), pct.group(2)
        try:
            return f'{lo}% to {hi}%', float(hi)
        except ValueError:
            return f'{lo}% to {hi}%', None
    to_rng = re.search(r'(\d+[.,]?\d*)\s+to\s+(\d+[.,]?\d*)', t, re.IGNORECASE)
    if to_rng:
        lo, hi = to_rng.group(1).replace(',', '.'), to_rng.group(2).replace(',', '.')
        try:
            lo_n, hi_n = float(lo), float(hi)
            return f'{lo_n:g}-{hi_n:g}', hi_n
        except ValueError:
            return f'{to_rng.group(1)}-{to_rng.group(2)}', None
    for pat in (
        r'(\d+[.,]\d+)\s*-\s*(\d+[.,]\d+)',
        r'(\d+[.,]?\d+)\s*-\s*(\d+[.,]?\d+)',
        r'(\d+[.,]\d+)\s+(\d+[.,]\d+)',
    ):
        rng = re.search(pat, t)
        if rng:
            lo, hi = rng.group(1).replace(',', '.'), rng.group(2).replace(',', '.')
            try:
                lo_n, hi_n = float(lo), float(hi)
                if hi_n < lo_n:
                    lo_n, hi_n = hi_n, lo_n
                return f'{lo_n:g}-{hi_n:g}', hi_n
            except ValueError:
                return f'{rng.group(1)}-{rng.group(2)}', None
    nums = re.findall(r'-?\d+[.,]?\d*', t)
    if nums:
        try:
            v = float(nums[0].replace(',', '.'))
            return nums[0], v
        except ValueError:
            return nums[0], None
    return None, None


def _representative_numeric_from_bin_label(label, internal_hint=None):
    """
    One number inside the bin for CSV/analysis: midpoint of a parsed interval,
    else a single number from the label, else internal_hint (e.g. class break).
    """
    if label is not None and str(label).strip():
        t = _normalize_ocr_text(str(label))
        pct = re.search(r'(\d+\.?\d*)\s*%\s*(?:to|-)\s*(\d+\.?\d*)\s*%', t, re.IGNORECASE)
        if pct:
            try:
                lo, hi = float(pct.group(1)), float(pct.group(2))
                return (lo + hi) / 2.0
            except ValueError:
                pass
        to_rng = re.search(r'(\d+[.,]?\d*)\s+to\s+(\d+[.,]?\d*)', t, re.IGNORECASE)
        if to_rng:
            try:
                lo, hi = float(to_rng.group(1).replace(',', '.')), float(to_rng.group(2).replace(',', '.'))
                return (lo + hi) / 2.0
            except ValueError:
                pass
        for pat in (
            r'(\d+[.,]\d+)\s*-\s*(\d+[.,]\d+)',
            r'(\d+[.,]?\d+)\s*-\s*(\d+[.,]?\d+)',
            r'(\d+[.,]\d+)\s+(\d+[.,]\d+)',
        ):
            rng = re.search(pat, t)
            if rng:
                try:
                    lo, hi = float(rng.group(1).replace(',', '.')), float(rng.group(2).replace(',', '.'))
                    if hi < lo:
                        lo, hi = hi, lo
                    return (lo + hi) / 2.0
                except ValueError:
                    continue
        for m in re.finditer(r'-?\d+[.,]\d+|-?\d+\.?\d*', t):
            try:
                return float(m.group(0).replace(',', '.'))
            except ValueError:
                continue
    if internal_hint is not None:
        try:
            h = float(internal_hint)
            if math.isfinite(h):
                return h
        except (TypeError, ValueError):
            pass
    return None


def _ranges_ordered_from_full_ocr_text(text, num_bins):
    """
    Pull num_bins range strings in document order (top-to-bottom reading order in OCR string).
    Handles missing dash between decimals (OCR gap).
    """
    if not text or num_bins < 2:
        return None, None
    t = _normalize_ocr_text(text)
    pairs = []
    seen_keys = set()

    def try_add(lo, hi):
        lo, hi = lo.replace(',', '.'), hi.replace(',', '.')
        try:
            lo_n, hi_n = float(lo), float(hi)
        except ValueError:
            return
        if hi_n <= lo_n + 1e-9:
            return
        if hi_n < lo_n:
            lo_n, hi_n = hi_n, lo_n
        key = (round(lo_n, 5), round(hi_n, 5))
        if key in seen_keys:
            return
        seen_keys.add(key)
        pairs.append((_fmt_bin_range_label(lo_n, hi_n), hi_n))

    for m in re.finditer(r'(\d+[.,]\d+)\s*-\s*(\d+[.,]\d+)', t):
        try_add(m.group(1), m.group(2))
    for m in re.finditer(r'(\d+[.,]\d+)\s+(\d+[.,]\d+)', t):
        try_add(m.group(1), m.group(2))
    for m in re.finditer(r'(\d+[.,]?\d+)\s*-\s*(\d+[.,]?\d+)', t):
        try_add(m.group(1), m.group(2))
    if len(pairs) < num_bins:
        return None, None
    pairs = pairs[:num_bins]
    return [p[1] for p in pairs], [p[0] for p in pairs]


def _ensure_tesseract_configured():
    """Point pytesseract at the binary on Windows / PATH."""
    if getattr(_ensure_tesseract_configured, '_done', False):
        return
    try:
        import shutil
        import pytesseract
        if shutil.which('tesseract'):
            _ensure_tesseract_configured._done = True
            return
        for p in (
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ):
            if os.path.isfile(p):
                pytesseract.pytesseract.tesseract_cmd = p
                print(f'  ✓ Using Tesseract: {p}')
                break
    except Exception:
        pass
    _ensure_tesseract_configured._done = True


def _pil_prepare_for_ocr(pil_rgb):
    """Upscale + contrast so small legend text is readable by Tesseract."""
    from PIL import Image as PILImage
    from PIL import ImageEnhance, ImageOps
    g = pil_rgb.convert('L')
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.35)
    w, h = g.size
    target_h = max(120, h * 3)
    target_w = max(280, w * 2)
    if h < 40 or w < 80:
        scale = max(target_h / max(h, 1), target_w / max(w, 1), 2.0)
        scale = min(scale, 6.0)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        g = g.resize((nw, nh), PILImage.Resampling.LANCZOS)
    return g


def _opencv_grayscale_for_ocr(arr_rgb):
    """Binarized, upscaled grayscale (often reads small sans-serif better than RGB)."""
    try:
        import cv2
    except ImportError:
        return None
    rgb = np.ascontiguousarray(arr_rgb.astype(np.uint8))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    scale = max(2.0, 220.0 / max(h, 6), 320.0 / max(w, 6))
    scale = min(scale, 5.0)
    gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    from PIL import Image as PILImage
    return PILImage.fromarray(th)


def _ocr_numpy_rgb_to_string(arr_rgb, psm_list=('6', '11', '7', '13')):
    try:
        import pytesseract
        from PIL import Image as PILImage
    except ImportError:
        return ''
    _ensure_tesseract_configured()
    pil = PILImage.fromarray(np.ascontiguousarray(arr_rgb.astype(np.uint8)))
    variants = [_pil_prepare_for_ocr(pil)]
    cv_pil = _opencv_grayscale_for_ocr(arr_rgb)
    if cv_pil is not None:
        variants.append(cv_pil)
    best = ''
    for prep in variants:
        for psm in psm_list:
            try:
                chunk = pytesseract.image_to_string(prep, config=f'--psm {psm} --oem 1')
            except Exception:
                continue
            if chunk and len(chunk.strip()) > len(best.strip()):
                best = chunk
    return best


def _extract_bin_ranges_per_strip(legend_area, num_bins):
    """
    OCR each bin row/column separately so range text aligns with swatches
    (avoids 'Bin 1' when whole-legend OCR fails or misorders lines).
    """
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return None, None
    if legend_area.size < 3 or num_bins < 2:
        return None, None
    h, w = int(legend_area.shape[0]), int(legend_area.shape[1])
    labels = []
    values = []

    if h >= w * 0.85:
        text_starts = sorted(set(max(0, min(int(w * f), w - 2)) for f in (0.22, 0.28, 0.34, 0.40, 0.48)))
        for i in range(num_bins):
            y0 = int(i * h / num_bins)
            y1 = int((i + 1) * h / num_bins) if i < num_bins - 1 else h
            if y1 <= y0:
                y1 = y0 + 1
            margin_y = max(0, int((y1 - y0) * 0.06))
            ya, yb = y0 + margin_y, y1 - margin_y
            if yb <= ya:
                ya, yb = y0, y1
            lbl, val, best_txt = None, None, ''
            for tx in text_starts:
                band = legend_area[ya:yb, tx:w, :]
                if band.size == 0 or band.shape[1] < 2:
                    continue
                chunk = _ocr_numpy_rgb_to_string(band)
                if len(chunk.strip()) > len(best_txt.strip()):
                    best_txt = chunk
                cand_l, cand_v = _parse_first_range_in_text(chunk)
                if cand_l and '-' in cand_l:
                    lbl, val, best_txt = cand_l, cand_v, chunk
                    break
            if not lbl or '-' not in str(lbl):
                full_strip = legend_area[ya:yb, :, :]
                chunk = _ocr_numpy_rgb_to_string(full_strip)
                if len(chunk.strip()) > len(best_txt.strip()):
                    best_txt = chunk
                cand_l, cand_v = _parse_first_range_in_text(chunk)
                if cand_l:
                    lbl, val = cand_l, cand_v
            print(f'    Strip {i + 1}/{num_bins} OCR: {repr(best_txt[:100])} -> {lbl}')
            labels.append(lbl)
            values.append(val)
        return values, labels

    if w >= h * 0.85:
        text_y_starts = sorted(set(max(0, min(int(h * f), h - 2)) for f in (0.38, 0.45, 0.52, 0.30)))
        for i in range(num_bins):
            x0 = int(i * w / num_bins)
            x1 = int((i + 1) * w / num_bins) if i < num_bins - 1 else w
            if x1 <= x0:
                x1 = x0 + 1
            margin_x = max(0, int((x1 - x0) * 0.06))
            xa, xb = x0 + margin_x, x1 - margin_x
            if xb <= xa:
                xa, xb = x0, x1
            lbl, val, best_txt = None, None, ''
            for ty in text_y_starts:
                band = legend_area[ty:h, xa:xb, :]
                if band.size == 0 or band.shape[0] < 2:
                    continue
                chunk = _ocr_numpy_rgb_to_string(band)
                if len(chunk.strip()) > len(best_txt.strip()):
                    best_txt = chunk
                cand_l, cand_v = _parse_first_range_in_text(chunk)
                if cand_l and '-' in cand_l:
                    lbl, val, best_txt = cand_l, cand_v, chunk
                    break
            if not lbl or '-' not in str(lbl):
                full_strip = legend_area[:, xa:xb, :]
                chunk = _ocr_numpy_rgb_to_string(full_strip)
                if len(chunk.strip()) > len(best_txt.strip()):
                    best_txt = chunk
                cand_l, cand_v = _parse_first_range_in_text(chunk)
                if cand_l:
                    lbl, val = cand_l, cand_v
            print(f'    Strip {i + 1}/{num_bins} OCR: {repr(best_txt[:100])} -> {lbl}')
            labels.append(lbl)
            values.append(val)
        return values, labels

    return None, None


def _merge_strip_and_full_ocr_bin_labels(num_bins, strip_vals, strip_lbls, full_vals, full_lbls, regex_vals=None, regex_lbls=None):
    """Prefer per-strip range; else full-legend row; else ordered regex on full OCR; else Bin i."""

    def _is_range_label(s):
        if not s or not isinstance(s, str):
            return False
        s = s.strip()
        if s.lower().startswith('bin '):
            return False
        return bool(re.search(r'\d', s)) and ('-' in s or 'to' in s.lower() or '%' in s)

    bin_values = []
    bin_labels = []
    for i in range(num_bins):
        sl = strip_lbls[i] if strip_lbls and i < len(strip_lbls) else None
        sv = strip_vals[i] if strip_vals and i < len(strip_vals) else None
        if sl and _is_range_label(sl):
            bin_labels.append(sl)
            bin_values.append(float(sv) if sv is not None else float(i))
            continue
        fl = full_lbls[i] if full_lbls and i < len(full_lbls) else None
        fv = full_vals[i] if full_vals and i < len(full_vals) else None
        if fl and _is_range_label(fl):
            bin_labels.append(fl)
            bin_values.append(float(fv) if fv is not None else float(i))
            continue
        rl = regex_lbls[i] if regex_lbls and i < len(regex_lbls) else None
        rv = regex_vals[i] if regex_vals and i < len(regex_vals) else None
        if rl:
            bin_labels.append(rl)
            bin_values.append(float(rv) if rv is not None else float(i))
            continue
        if sl:
            bin_labels.append(sl)
            bin_values.append(float(sv) if sv is not None else float(i))
            continue
        if fl:
            bin_labels.append(fl)
            bin_values.append(float(fv) if fv is not None else float(i))
            continue
        bin_labels.append(f'Bin {i + 1}')
        bin_values.append(float(i))
    return bin_values, bin_labels


def _mask_swatch_like_pixels(pixels_rgb):
    """
    Keep pixels likely from filled swatches; drop page background, gaps, and text/borders.
    pixels_rgb: (N, 3) float or uint8.
    """
    p = np.asarray(pixels_rgb, dtype=np.float64)
    if len(p) == 0:
        return np.array([], dtype=bool)
    mx = p.max(axis=1)
    mn = p.min(axis=1)
    chroma = mx - mn
    luma = 0.299 * p[:, 0] + 0.587 * p[:, 1] + 0.114 * p[:, 2]
    ok = np.ones(len(p), dtype=bool)
    ok &= luma >= 28
    ok &= ~((luma >= 252) & (chroma <= 8))
    ok &= ~((luma >= 253) & (chroma <= 14))
    return ok


def _binned_colors_spatial_strips(legend_area, num_bins):
    """
    One median color per bin using horizontal strips (vertical legend) or vertical strips
    (horizontal legend). Samples only the swatch side of the crop so numeric labels are ignored.
    Preserves top-to-bottom (or left-to-right) order — do not luminance-sort.
    """
    if legend_area.size < 3 or num_bins < 2:
        return None
    h, w = int(legend_area.shape[0]), int(legend_area.shape[1])
    colors_out = []

    if h >= w * 0.85:
        swatch_w = max(3, min(w, int(w * 0.52)))
        region = np.ascontiguousarray(legend_area[:, :swatch_w, :])
        for i in range(num_bins):
            y0 = int(i * h / num_bins)
            y1 = int((i + 1) * h / num_bins) if i < num_bins - 1 else h
            if y1 <= y0:
                y1 = y0 + 1
            margin = max(0, int((y1 - y0) * 0.14))
            ya, yb = y0 + margin, y1 - margin
            if yb <= ya:
                ya, yb = y0, y1
            strip = region[ya:yb, :, :]
            if strip.size == 0:
                return None
            p = strip.reshape(-1, 3).astype(np.float64)
            mask = _mask_swatch_like_pixels(p)
            good = p[mask]
            if len(good) < 10:
                good = p
            med = np.median(good, axis=0)
            colors_out.append(np.clip(np.round(med), 0, 255).astype(int))
        return [c.tolist() for c in colors_out]

    if w >= h * 0.85:
        swatch_h = max(3, min(h, int(h * 0.52)))
        region = np.ascontiguousarray(legend_area[:swatch_h, :, :])
        hh, ww = region.shape[0], region.shape[1]
        for i in range(num_bins):
            x0 = int(i * ww / num_bins)
            x1 = int((i + 1) * ww / num_bins) if i < num_bins - 1 else ww
            if x1 <= x0:
                x1 = x0 + 1
            margin = max(0, int((x1 - x0) * 0.14))
            xa, xb = x0 + margin, x1 - margin
            if xb <= xa:
                xa, xb = x0, x1
            strip = region[:, xa:xb, :]
            if strip.size == 0:
                return None
            p = strip.reshape(-1, 3).astype(np.float64)
            mask = _mask_swatch_like_pixels(p)
            good = p[mask]
            if len(good) < 10:
                good = p
            med = np.median(good, axis=0)
            colors_out.append(np.clip(np.round(med), 0, 255).astype(int))
        return [c.tolist() for c in colors_out]

    return None


def _kmeans_legend_colors(legend_area, num_clusters, vertical_hint=None):
    """Pick representative RGBs via K-means; prefer masked swatch pixels to avoid bg/text."""
    if legend_area.size < 3:
        return []
    pixels = legend_area.reshape(-1, 3).astype(np.float64)
    n = pixels.shape[0]
    h, w = legend_area.shape[0], legend_area.shape[1]
    mask = _mask_swatch_like_pixels(pixels)
    if mask.sum() >= max(80, min(500, n // 5)):
        pixels = pixels[mask]
        n = len(pixels)
    if n < 2:
        pixels = legend_area.reshape(-1, 3).astype(np.float64)
        n = len(pixels)
    k = int(max(2, min(int(num_clusters), n)))
    max_samples = 50000
    if n > max_samples:
        rng = np.random.default_rng(42)
        pixels_fit = pixels[rng.choice(n, max_samples, replace=False)]
    else:
        pixels_fit = pixels
    k_fit = min(k, len(pixels_fit))
    if k_fit < 2:
        return []
    try:
        km = KMeans(n_clusters=k_fit, n_init=10, random_state=42, max_iter=200)
        km.fit(pixels_fit)
    except Exception as e:
        print(f'  ⚠️  KMeans legend colors failed: {e}')
        return []
    centers = np.clip(np.round(km.cluster_centers_), 0, 255).astype(int)

    def luminance_row(rgb):
        r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
        return 0.299 * r + 0.587 * g + 0.114 * b

    if vertical_hint is True or (vertical_hint is None and h >= w * 0.85):
        flat = legend_area.reshape(-1, 3).astype(np.float64)
        labels = km.predict(flat)
        ys = np.repeat(np.arange(h, dtype=np.float64), w)
        mean_y = []
        for ci in range(k_fit):
            sel = labels == ci
            if np.any(sel):
                mean_y.append(float(np.mean(ys[sel])))
            else:
                mean_y.append(1e9)
        order = sorted(range(k_fit), key=lambda i: mean_y[i])
        return [centers[i].tolist() for i in order]

    if vertical_hint is False or (vertical_hint is None and w >= h * 0.85):
        flat = legend_area.reshape(-1, 3).astype(np.float64)
        labels = km.predict(flat)
        xs = np.tile(np.arange(w, dtype=np.float64), h)
        mean_x = []
        for ci in range(k_fit):
            sel = labels == ci
            if np.any(sel):
                mean_x.append(float(np.mean(xs[sel])))
            else:
                mean_x.append(1e9)
        order = sorted(range(k_fit), key=lambda i: mean_x[i])
        return [centers[i].tolist() for i in order]

    order = sorted(range(k_fit), key=lambda i: -luminance_row(centers[i]))
    return [centers[i].tolist() for i in order]


def _unique_colors_pixel_walk(legend_area, merge_dist=30):
    pixels = legend_area.reshape(-1, 3)
    unique_colors = []
    for pixel in pixels:
        is_unique = True
        for existing_color in unique_colors:
            distance = np.sqrt(np.sum((pixel.astype(np.float64) - existing_color.astype(np.float64)) ** 2))
            if distance < merge_dist:
                is_unique = False
                break
        if is_unique:
            unique_colors.append(pixel)
    return unique_colors


def extract_legend_from_selection(image_path, legend_selection, legend_type_info=None):
    if not legend_selection:
        return None
    img = ImageOps.exif_transpose(Image.open(image_path)).convert('RGB')
    img_arr = np.array(img)
    x = int(legend_selection['x'])
    y = int(legend_selection['y'])
    width = int(legend_selection['width'])
    height = int(legend_selection['height'])
    x = max(0, min(x, img_arr.shape[1] - 1))
    y = max(0, min(y, img_arr.shape[0] - 1))
    width = min(width, img_arr.shape[1] - x)
    height = min(height, img_arr.shape[0] - y)
    legend_area = img_arr[y:y + height, x:x + width]
    if legend_type_info and legend_type_info.get('type') == 'continuous':
        is_vertical = height > width
        if is_vertical:
            num_samples = 100
            step = max(1, height // num_samples)
            colors = []
            for i in range(0, height, step):
                row = legend_area[i, :]
                avg_color = row.mean(axis=0).astype(int)
                colors.append(avg_color.tolist())
        else:
            num_samples = 100
            step = max(1, width // num_samples)
            colors = []
            for i in range(0, width, step):
                col = legend_area[:, i]
                avg_color = col.mean(axis=0).astype(int)
                colors.append(avg_color.tolist())
        unique_colors = []
        for color in colors:
            is_unique = True
            for existing in unique_colors:
                distance = np.sqrt(np.sum((np.array(color) - np.array(existing)) ** 2))
                if distance < 20:
                    is_unique = False
                    break
            if is_unique:
                unique_colors.append(color)
        if is_vertical:
            unique_colors = unique_colors[::-1]
        min_val = legend_type_info.get('minValue', 0)
        max_val = legend_type_info.get('maxValue', 100)
        legend = []
        for i, color in enumerate(unique_colors):
            if len(unique_colors) > 1:
                value = min_val + (max_val - min_val) * (i / (len(unique_colors) - 1))
            else:
                value = min_val
            legend.append((color, value))
        return legend if len(legend) >= 2 else None
    else:
        lti = legend_type_info or {}
        is_binned = lti.get('type') == 'binned'
        nb_req = lti.get('numBins')
        if isinstance(nb_req, (int, float)):
            nb_req = int(nb_req)
        else:
            nb_req = None

        h_leg, w_leg = int(legend_area.shape[0]), int(legend_area.shape[1])
        vertical_legend = h_leg >= w_leg * 0.85
        horizontal_legend = w_leg >= h_leg * 0.85
        km_vertical_hint = True if vertical_legend else (False if horizontal_legend else None)

        unique_colors = []
        skip_luminance_sort = False
        used_spatial_strips = False
        if is_binned and nb_req is not None and nb_req >= 2:
            sc = _binned_colors_spatial_strips(legend_area, nb_req)
            if sc is not None and len(sc) == nb_req:
                unique_colors = [np.array(c, dtype=np.float64) for c in sc]
                used_spatial_strips = True
                skip_luminance_sort = True

        if not used_spatial_strips and is_binned and nb_req is not None and nb_req >= 2:
            km_cols = _kmeans_legend_colors(legend_area, nb_req, vertical_hint=km_vertical_hint)
            unique_colors = [np.array(c, dtype=np.float64) for c in km_cols]
            skip_luminance_sort = True

        if len(unique_colors) < 2:
            unique_colors = _unique_colors_pixel_walk(legend_area, merge_dist=28)
            skip_luminance_sort = False
        if len(unique_colors) < 2:
            unique_colors = _unique_colors_pixel_walk(legend_area, merge_dist=14)
            skip_luminance_sort = False
        if len(unique_colors) < 2:
            n_px = int(legend_area.shape[0] * legend_area.shape[1])
            k_fb = max(2, min(nb_req or 6, 12, max(2, n_px)))
            km2 = _kmeans_legend_colors(legend_area, k_fb, vertical_hint=km_vertical_hint)
            unique_colors = [np.array(c, dtype=np.float64) for c in km2]
            skip_luminance_sort = True

        def luminance(rgb):
            return 0.299 * float(rgb[0]) + 0.587 * float(rgb[1]) + 0.114 * float(rgb[2])

        if not skip_luminance_sort:
            unique_colors.sort(key=lambda c: luminance(c), reverse=True)

        if is_binned and nb_req is not None and nb_req >= 2:
            if len(unique_colors) > nb_req:
                step = len(unique_colors) / nb_req
                unique_colors = [unique_colors[int(i * step)] for i in range(nb_req)]

        num_bins = len(unique_colors)
        global_ocr_txt = _ocr_numpy_rgb_to_string(legend_area)
        regex_vals, regex_lbls = _ranges_ordered_from_full_ocr_text(global_ocr_txt, num_bins)
        strip_vals, strip_lbls = _extract_bin_ranges_per_strip(legend_area, num_bins)
        if strip_vals is None:
            strip_vals = []
        if strip_lbls is None:
            strip_lbls = []
        full_extraction = _extract_bin_values_from_legend(legend_area, num_bins, ocr_text_cache=global_ocr_txt)
        fv, fl = ([], [])
        if full_extraction and full_extraction[0] is not None:
            fv, fl = full_extraction
        bin_values, bin_labels = _merge_strip_and_full_ocr_bin_labels(
            num_bins, strip_vals, strip_lbls, fv, fl, regex_vals, regex_lbls
        )
        if _all_bin_labels_are_placeholders(bin_labels):
            mm = _legend_area_numeric_min_max(legend_area)
            if mm:
                lo_mm, hi_mm = mm
                ev, el = _equal_interval_bin_ranges(num_bins, lo_mm, hi_mm)
                if ev is not None:
                    bin_values, bin_labels = ev, el
                    print(f'  ✓ Replaced Bin placeholders with equal-width ranges from OCR min/max ({lo_mm:g}–{hi_mm:g})')
        legend = []
        for i, color in enumerate(unique_colors):
            label = bin_labels[i]
            value = float(bin_values[i])
            print(f'    Bin {i + 1}: label={label!r}, internal_value={value}')
            legend.append((color.tolist(), label, value))
        if bin_values and legend_type_info is not None:
            legend_type_info['binValues'] = bin_values
        if bin_labels and legend_type_info is not None:
            legend_type_info['binLabels'] = bin_labels
            if len(bin_values) >= 2:
                legend_type_info['minValue'] = min(bin_values)
                legend_type_info['maxValue'] = max(bin_values)
        if legend_type_info is not None:
            bo = legend_type_info.get('binValuesOverride')
            bl = legend_type_info.get('binLabelsOverride')
            label_override = isinstance(bl, list) and len(bl) == len(legend)
            value_override = isinstance(bo, list) and len(bo) == len(legend)
            if label_override or value_override:
                new_legend = []
                for i, (rgb, label, val) in enumerate(legend):
                    nl = label
                    if label_override:
                        s = str(bl[i]).strip() if bl[i] is not None else ''
                        if s:
                            nl = s
                    nv = float(val)
                    if value_override:
                        nv = float(bo[i])
                    new_legend.append((rgb, nl, nv))
                legend = new_legend
                legend_type_info['binLabels'] = [t[1] for t in legend]
                if value_override:
                    legend_type_info['binValues'] = [t[2] for t in legend]
                    vals = legend_type_info['binValues']
                    if len(vals) >= 2:
                        legend_type_info['minValue'] = min(vals)
                        legend_type_info['maxValue'] = max(vals)
    return legend if len(legend) >= 2 else None


def preview_legend_extraction(image_path, legend_selection, legend_type_info=None):
    """Run legend extraction for UI preview; returns serializable bins and updated type info."""
    lti = copy.deepcopy(legend_type_info) if legend_type_info else {}
    lti.pop('binValuesOverride', None)
    lti.pop('binLabelsOverride', None)
    legend = extract_legend_from_selection(image_path, legend_selection, lti)
    if not legend:
        return None, 'Could not detect at least two legend colors. Tighten the box around the color swatches or gradient.'
    lt = lti.get('type', 'binned')
    if lt == 'continuous':
        bins = []
        for item in legend:
            if len(item) == 2:
                color, value = item
                rgb = color if isinstance(color, list) else np.asarray(color).astype(int).tolist()
                v = float(value)
                bins.append({'rgb': rgb, 'label': f'{v:g}', 'value': v})
        return {'legendType': 'continuous', 'bins': bins, 'legendTypeInfo': lti}, None
    bins = []
    for item in legend:
        if len(item) == 3:
            rgb, lbl, _val = item
            br = str(lbl).strip() or 'Bin'
            bins.append({'rgb': [int(c) for c in rgb], 'binRange': br, 'label': br})
    return {'legendType': 'binned', 'bins': bins, 'legendTypeInfo': lti}, None


def _ensure_shapefile_exists():
    paths_to_check = [_get_region_shapefile_path('conus', '4326'), _get_region_shapefile_path('conus', '5070'), _get_shapefile_path('4326', False), _get_shapefile_path('5070', False), SHAPEFILE_PATH]
    for path in paths_to_check:
        if os.path.exists(path):
            return
    raise FileNotFoundError(f'No shapefile found. Checked: {paths_to_check}. Make sure .shp, .shx, and .dbf files are in the folder.')

def _raster_transform_for_image_and_shp(shp, img_w, img_h):
    minx, miny, maxx, maxy = shp.total_bounds
    return from_bounds(minx, miny, maxx, maxy, img_w, img_h)

def _hawaii_user_rgb_overrides(region_selections):
    if not region_selections or not isinstance(region_selections, dict):
        return {}
    hi = region_selections.get('hawaii')
    if not hi or not isinstance(hi, dict):
        return {}
    selections = hi.get('countySelections') or hi.get('county_selections')
    if not selections or not isinstance(selections, list):
        return {}
    out = {}
    for item in selections:
        if not isinstance(item, dict):
            continue
        raw_gid = item.get('geoid')
        if raw_gid is None:
            continue
        geoid = str(raw_gid).strip().zfill(5)
        cc = item.get('countyClick') or item.get('county_click')
        if not geoid or not cc or (not isinstance(cc, dict)):
            continue
        rgb_obj = cc.get('rgb')
        if not rgb_obj or not isinstance(rgb_obj, dict):
            continue
        try:
            r = int(rgb_obj['r'])
            g = int(rgb_obj['g'])
            b = int(rgb_obj['b'])
        except (KeyError, TypeError, ValueError):
            continue
        out[geoid] = [r, g, b]
    return out

def process_uploaded_image(image_path, layer_name='uploaded', out_dir='data', legend_selection=None, n_bins=64, upload_id=None, region_selections=None, projection='4326', legend_type_info=None, csv_basename=None):
    os.makedirs(out_dir, exist_ok=True)
    if upload_id is None:
        raise ValueError('upload_id required; run /api/detect-bounds first.')
    has_alaska = region_selections and region_selections.get('alaska')
    has_hawaii = region_selections and region_selections.get('hawaii')
    print('=' * 70)
    print('REGION SELECTION:')
    print(f'  Alaska: {has_alaska}')
    print(f'  Hawaii: {has_hawaii}')
    print(f'  Selected Projection: EPSG:{projection}')
    print('=' * 70)
    regions_to_load = ['conus']
    if has_alaska:
        regions_to_load.append('alaska')
    if has_hawaii:
        regions_to_load.append('hawaii')
    print(f'\n📂 LOADING SEPARATE REGION SHAPEFILES:')
    print(f"  Regions to load: {', '.join(regions_to_load)}")
    shp_regions = {}
    shp_regions_for_geojson = {}
    for region in regions_to_load:
        shapefile_path = _get_region_shapefile_path(region=region, projection=projection)
        if not os.path.exists(shapefile_path) and region == 'conus':
            shapefile_path = SHAPEFILE_PATH
            print(f'  ⚠️  {region.upper()} shapefile not found at new path, using fallback: {shapefile_path}')
        if not os.path.exists(shapefile_path):
            raise FileNotFoundError(f'Shapefile not found for {region} at {shapefile_path}')
        print(f'  ✓ Loading {region.upper()}: {shapefile_path}')
        shp_region = gpd.read_file(shapefile_path)
        if 'GEOID' not in shp_region.columns:
            shp_region['GEOID'] = shp_region.index.astype(str)
        shp_region['GEOID'] = shp_region['GEOID'].astype(str).str.zfill(5)
        print(f'    Counties: {len(shp_region)}')
        print(f'    CRS: {shp_region.crs}')
        print(f'    Bounds: {shp_region.total_bounds}')
        if shp_region.crs is None:
            if projection == '4326':
                shp_region = shp_region.set_crs(4326, allow_override=True)
            elif projection == '5070':
                shp_region = shp_region.set_crs(5070, allow_override=True)
            else:
                shp_region = shp_region.set_crs(4269, allow_override=True)
            print(f'    ⚠️  CRS was None, set to: {shp_region.crs}')
        target_crs = 5070
        if shp_region.crs.to_epsg() != target_crs:
            print(f'    🔄 Reprojecting to EPSG:{target_crs} for alignment')
            shp_region_projected = shp_region.to_crs(target_crs)
        else:
            shp_region_projected = shp_region.copy()
        shp_regions[region] = shp_region_projected
        shp_regions_for_geojson[region] = shp_region.copy()
    print('=' * 70)
    county_data_path = os.path.join(BASE_DIR, 'cb_2024_us_county_500k', 'county_data.csv')
    county_names = {}
    state_names = {}
    if os.path.exists(county_data_path):
        county_df = pd.read_csv(county_data_path, dtype=str)
        county_df['fips_padded'] = county_df['fips'].str.zfill(5)
        county_names = dict(zip(county_df['fips_padded'], county_df['name']))
        state_names = dict(zip(county_df['fips_padded'], county_df['state']))
    if shp_regions:
        first_region = list(shp_regions.keys())[0]
        first_shp = shp_regions[first_region]
        if 'NAME' in first_shp.columns:
            for region, shp_region in shp_regions.items():
                if 'NAME' in shp_region.columns and 'GEOID' in shp_region.columns:
                    for _, row in shp_region.iterrows():
                        geoid = str(row['GEOID']).zfill(5)
                        if geoid not in county_names:
                            county_names[geoid] = row['NAME']
        if 'STUSPS' in first_shp.columns or 'STATE_NAME' in first_shp.columns:
            state_fips_to_name = {}
            for region, shp_region in shp_regions.items():
                if 'GEOID' in shp_region.columns:
                    for _, row in shp_region.iterrows():
                        geoid = str(row['GEOID']).zfill(5)
                        state_fips = geoid[:2]
                        if state_fips not in state_fips_to_name:
                            if 'STATE_NAME' in row:
                                state_fips_to_name[state_fips] = row['STATE_NAME']
                            elif 'STUSPS' in row:
                                state_fips_to_name[state_fips] = row.get('STUSPS', '')
            for region, shp_region in shp_regions.items():
                if 'GEOID' in shp_region.columns:
                    for _, row in shp_region.iterrows():
                        geoid = str(row['GEOID']).zfill(5)
                        if geoid not in state_names:
                            state_fips = geoid[:2]
                            if state_fips in state_fips_to_name:
                                state_names[geoid] = state_fips_to_name[state_fips]
                            elif 'STATE_NAME' in row:
                                state_names[geoid] = row['STATE_NAME']
                            elif 'STUSPS' in row:
                                state_names[geoid] = row['STUSPS']
    img = Image.open(image_path).convert('RGB')
    img_w, img_h = img.size
    img_arr = np.array(img)
    print('\n' + '=' * 70)
    print('IMAGE INFORMATION:')
    print(f'  Upload ID: {upload_id}')
    print(f'  Image Size: {img_w} x {img_h} pixels')
    print('=' * 70)
    bounds = None
    try:
        bounds = get_bounds_for_upload(upload_id)
        if bounds:
            print(f"✓ Loaded bounds for '{upload_id}'")
    except Exception as e:
        print(f"⚠️  Failed to load bounds for '{upload_id}': {e}")
        import traceback
        traceback.print_exc()
        bounds = None
    if not bounds or not getattr(bounds, 'canvases', None):
        emergency_bounds = {'map1': (41, 23, 825, 504, [(41, 23), (825, 23), (825, 504), (41, 504)]), 'avg income-1': (20, 35, 840, 510, [(20, 35), (840, 35), (840, 510), (20, 510)]), 'map2': (70, 110, 790, 640, [(70, 110), (790, 110), (790, 640), (70, 640)]), 'pharma-1': (40, 35, 820, 585, [(40, 35), (820, 35), (820, 585), (40, 585)]), 'unclassed_choropleth_map': (20, 12, 410, 290, [(20, 12), (410, 12), (410, 290), (20, 290)]), 'unemployment-1': (80, 70, 1770, 1100, [(80, 70), (1770, 70), (1770, 1100), (80, 1100)])}
        if upload_id.lower() in emergency_bounds:
            x0, y0, x1, y1, poly_list = emergency_bounds[upload_id.lower()]
            bbox = (x0, y0, x1, y1)
            poly = poly_list
            print(f"\n⚠️  Using emergency manual bounds for '{upload_id}': bbox={bbox}")
        else:
            assert False, f"No bounds for uploadId '{upload_id}'. Save bounds first."
    else:
        assert bounds and getattr(bounds, 'canvases', None), 'No bounds for this uploadId. Save bounds first.'
        conus = next((c for c in bounds.canvases if c.name.upper() == 'CONUS'), bounds.canvases[0])
        x0, y0, x1, y1 = map(int, conus.bbox)
        poly = conus.polygon if conus.polygon and len(conus.polygon) >= 3 else [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        bbox = (x0, y0, x1, y1)
        if not region_selections:
            region_selections = {}
        alaska_canvas = next((c for c in bounds.canvases if c.name.upper() in ('ALASKA', 'AK')), None)
        if alaska_canvas and (not region_selections.get('alaska')):
            ak_x0, ak_y0, ak_x1, ak_y1 = map(int, alaska_canvas.bbox)
            region_selections['alaska'] = {'x': ak_x0, 'y': ak_y0, 'width': ak_x1 - ak_x0, 'height': ak_y1 - ak_y0}
            print(f'✓ Using Alaska bounds from detected bounds: {alaska_canvas.bbox}')
        hawaii_canvas = next((c for c in bounds.canvases if c.name.upper() in ('HAWAII', 'HI')), None)
        if hawaii_canvas and (not region_selections.get('hawaii')):
            hi_x0, hi_y0, hi_x1, hi_y1 = map(int, hawaii_canvas.bbox)
            region_selections['hawaii'] = {'x': hi_x0, 'y': hi_y0, 'width': hi_x1 - hi_x0, 'height': hi_y1 - hi_y0}
            print(f'✓ Using Hawaii bounds from detected bounds: {hawaii_canvas.bbox}')
    print(f'\n📐 MAP BOUNDS:')
    print(f'  Bounding Box: ({x0}, {y0}) to ({x1}, {y1})')
    print(f'  Bbox Size: {x1 - x0} x {y1 - y0} pixels')
    print(f'  Polygon Points: {len(poly)}')
    print('=' * 70)
    print(f'\n🔧 ALIGNING REGIONS WITH AFFINE TRANSFORMATIONS:')
    print('=' * 70)
    aligned_regions = []
    print(f'\n📍 CONUS Alignment:')
    shp_conus = shp_regions['conus']
    print(f'  Shapefile bounds (EPSG:5070): {shp_conus.total_bounds}')
    user_conus_rect4 = None
    used_manual_alignment = False
    print(f"\n  🔍 REQUIRING user's manual CONUS alignment (rect4)...")
    if not region_selections:
        raise ValueError('❌ ERROR: region_selections is required. User must manually align CONUS shapefile.')
    if not region_selections.get('conus'):
        raise ValueError('❌ ERROR: CONUS region selection is required. User must manually align CONUS shapefile.')
    conus_selection = region_selections['conus']
    if not isinstance(conus_selection, dict):
        raise ValueError(f'❌ ERROR: CONUS selection must be a dict, got {type(conus_selection)}')
    use_tps = False
    tps_src_points = None
    tps_dst_points = None
    user_conus_rect4 = None
    if conus_selection.get('alignmentParams'):
        alignment_params = conus_selection['alignmentParams']
        if isinstance(alignment_params, dict):
            if alignment_params.get('transform_type') == 'tps':
                tps_src_points = alignment_params.get('tps_src_points')
                tps_dst_points = alignment_params.get('tps_dst_points')
                if tps_src_points and tps_dst_points:
                    use_tps = True
                    print(f"  ✓✓✓ FOUND: TPS transformation data from user's selected county points")
                    print(f'  ✓✓✓ Using ACTUAL user-selected points (not rect4 bounding box)')
                    if alignment_params.get('rect4'):
                        user_conus_rect4 = alignment_params['rect4']
                        print(f'  ✓✓✓ Also found rect4 for bounds validation: {user_conus_rect4}')
            elif alignment_params.get('rect4'):
                user_conus_rect4 = alignment_params['rect4']
                print(f"  ✓✓✓ FOUND: Using user's manually aligned CONUS rect4 from alignmentParams: {user_conus_rect4}")
    if not use_tps:
        if conus_selection.get('rect4'):
            user_conus_rect4 = conus_selection['rect4']
            print(f"  ✓✓✓ FOUND: Using user's manually aligned CONUS rect4: {user_conus_rect4}")
        elif conus_selection.get('overlayParams'):
            overlay_params = conus_selection['overlayParams']
            if isinstance(overlay_params, dict) and overlay_params.get('rect4'):
                user_conus_rect4 = overlay_params['rect4']
                print(f"  ✓✓✓ FOUND: Using user's manually aligned CONUS rect4 from overlayParams: {user_conus_rect4}")
    if not use_tps and (not user_conus_rect4):
        raise ValueError("❌ ERROR: User's manually aligned CONUS rect4 is required. User must complete the manual alignment step.")
    if user_conus_rect4:
        if not isinstance(user_conus_rect4, list) or len(user_conus_rect4) != 4:
            raise ValueError(f"❌ ERROR: User's CONUS rect4 must be a list of 4 points, got: {user_conus_rect4}")
        for i, corner in enumerate(user_conus_rect4):
            if not isinstance(corner, (list, tuple)) or len(corner) != 2:
                raise ValueError(f'❌ ERROR: CONUS rect4 corner {i} must be [x, y], got: {corner}')
    if True:
        try:
            if use_tps:
                from utils.tps import tps_transform_from_points, apply_tps_to_geometry
            else:
                from utils.homography import rect_bounds_to_corners, homography_from_4pts, apply_homography_to_geometry
        except ImportError:
            if use_tps:
                from backend.utils.tps import tps_transform_from_points, apply_tps_to_geometry
            else:
                from backend.utils.homography import rect_bounds_to_corners, homography_from_4pts, apply_homography_to_geometry
        try:
            img_check = Image.open(image_path)
            img_w, img_h = img_check.size
            img_check.close()
            print(f"\n  🔍 VERIFYING USER'S MANUAL ALIGNMENT:")
            print(f'  ✓ Image dimensions: {img_w} x {img_h} (natural pixels - SAME image user aligned on)')
            if user_conus_rect4:
                print(f"  ✓ User's rect4 (natural pixels from frontend): {user_conus_rect4}")
                all_in_bounds = True
                rect4_x_coords = [corner[0] for corner in user_conus_rect4]
                rect4_y_coords = [corner[1] for corner in user_conus_rect4]
                rect4_width = max(rect4_x_coords) - min(rect4_x_coords)
                rect4_height = max(rect4_y_coords) - min(rect4_y_coords)
                for i, (x, y) in enumerate(user_conus_rect4):
                    if x < 0 or x > img_w or y < 0 or (y > img_h):
                        print(f'  ⚠️  WARNING: rect4 corner {i} ({x}, {y}) is outside image bounds ({img_w} x {img_h})')
                        all_in_bounds = False
                if all_in_bounds:
                    print(f'  ✓ All rect4 corners are within image bounds')
                print(f"  ✓ User's rect4 dimensions: {rect4_width} x {rect4_height} pixels")
                print(f'  ✓ Image dimensions: {img_w} x {img_h} pixels')
                print(f'  ✓ Rect4 coverage: {rect4_width / img_w * 100:.1f}% width, {rect4_height / img_h * 100:.1f}% height')
                if rect4_width < img_w * 0.5 or rect4_height < img_h * 0.5:
                    print(f"  ⚠️  WARNING: User's rect4 seems small ({rect4_width / img_w * 100:.1f}% x {rect4_height / img_h * 100:.1f}%)")
                    print(f'  ⚠️  This might not cover the full CONUS map area!')
            if use_tps and tps_src_points and tps_dst_points:
                print(f'  ✓ Using Thin-Plate Spline (TPS) transformation for non-linear warping')
                print(f'  ✓ Shapefile is already in EPSG:5070 (flat projection) - good for TPS')
                tps_src_array = np.array(tps_src_points, dtype=float)
                tps_dst_array = np.array(tps_dst_points, dtype=float)
                tps_func = tps_transform_from_points(tps_src_array, tps_dst_array)
                gdf_conus_px = shp_conus.copy()
                gdf_conus_px['geometry'] = gdf_conus_px.geometry.apply(lambda geom: apply_tps_to_geometry(geom, tps_func))
                gdf_conus_px.crs = None
                print(f"  ✓ TPS transformation applied to all geometries using user's selected points")
            else:
                if not user_conus_rect4:
                    raise ValueError('❌ ERROR: Cannot compute homography without rect4. TPS transformation data is required.')
                xmin, ymin, xmax, ymax = shp_conus.total_bounds
                src_bounds = (xmin, ymin, xmax, ymax)
                src4 = rect_bounds_to_corners(src_bounds, is_geographic=True)
                print(f'  ✓ Shapefile bounds (EPSG:5070): {src_bounds}')
                print(f'  ✓ Source corners (geographic):')
                for i, corner in enumerate(src4):
                    print(f'      Corner {i}: ({corner[0]:.2f}, {corner[1]:.2f})')
                dst4 = np.array(user_conus_rect4, dtype=float)
                print(f"  ✓ Destination corners (pixels from user's alignment):")
                for i, corner in enumerate(dst4):
                    print(f'      Corner {i}: ({corner[0]:.2f}, {corner[1]:.2f})')
                H = homography_from_4pts(src4, dst4)
                print(f'  ✓ Homography matrix computed (same method as interactive overlay)')
                gdf_conus_px = shp_conus.copy()
                gdf_conus_px['geometry'] = gdf_conus_px.geometry.apply(lambda geom: apply_homography_to_geometry(geom, H))
                gdf_conus_px.crs = None
            tf_xmin, tf_ymin, tf_xmax, tf_ymax = gdf_conus_px.total_bounds
            print(f"\n  ✓✓✓ SUCCESS: Using user's manual alignment for processing")
            if use_tps:
                print(f"    - Using TPS transformation from user's selected county points")
                print(f'    - TPS source points (shapefile centroids): {len(tps_src_points)} points')
                print(f'    - TPS destination points (user clicks): {len(tps_dst_points)} points')
            else:
                print(f'    - Using homography transformation from rect4')
                print(f'    - User aligned rect4: {user_conus_rect4}')
            print(f'    - Transformed shapefile bounds: ({tf_xmin:.1f}, {tf_ymin:.1f}) to ({tf_xmax:.1f}, {tf_ymax:.1f})')
            if user_conus_rect4:
                rect4_x_coords = [corner[0] for corner in user_conus_rect4]
                rect4_y_coords = [corner[1] for corner in user_conus_rect4]
                rect4_xmin = min(rect4_x_coords)
                rect4_ymin = min(rect4_y_coords)
                rect4_xmax = max(rect4_x_coords)
                rect4_ymax = max(rect4_y_coords)
                print(f'    - User rect4 bounds: ({rect4_xmin:.1f}, {rect4_ymin:.1f}) to ({rect4_xmax:.1f}, {rect4_ymax:.1f})')
                tolerance = 5.0
                bounds_match = abs(tf_xmin - rect4_xmin) < tolerance and abs(tf_ymin - rect4_ymin) < tolerance and (abs(tf_xmax - rect4_xmax) < tolerance) and (abs(tf_ymax - rect4_ymax) < tolerance)
                if bounds_match:
                    print(f"    ✓ Transformed shapefile bounds match user's rect4 (within {tolerance}px)")
                else:
                    print(f"    ⚠️  WARNING: Transformed shapefile bounds don't match user's rect4!")
                    print(f'       Difference: X={abs(tf_xmin - rect4_xmin):.1f}, Y={abs(tf_ymin - rect4_ymin):.1f}')
            print(f'    - This is the EXACT same transformation the user saw in the preview')
            print(f'    - RGB extraction will use FULL IMAGE (not cropped) with this exact alignment\n')
            aligned_regions.append(gdf_conus_px)
            used_manual_alignment = True
        except Exception as homography_err:
            import traceback
            error_trace = traceback.format_exc()
            print(f'\n  ❌ ERROR in homography transformation:')
            print(f'  Error: {str(homography_err)}')
            print(f'  Traceback:\n{error_trace}')
            raise ValueError(f"Failed to apply user's manual CONUS alignment: {str(homography_err)}")
    if has_alaska and 'alaska' in shp_regions:
        print(f'\n📍 Alaska Alignment:')
        shp_alaska = shp_regions['alaska']
        user_alaska_rect4 = None
        print(f"  🔍 REQUIRING user's manual Alaska alignment (rect4)...")
        if not region_selections or not region_selections.get('alaska'):
            raise ValueError('❌ ERROR: Alaska region selection is required. User must manually align Alaska shapefile.')
        alaska_selection = region_selections['alaska']
        if not isinstance(alaska_selection, dict):
            raise ValueError(f'❌ ERROR: Alaska selection must be a dict, got {type(alaska_selection)}')
        if alaska_selection.get('alignmentParams'):
            alignment_params = alaska_selection['alignmentParams']
            if isinstance(alignment_params, dict) and alignment_params.get('rect4'):
                user_alaska_rect4 = alignment_params['rect4']
                print(f'  ✓✓✓ FOUND: Alaska rect4 from alignmentParams: {user_alaska_rect4}')
        if not user_alaska_rect4 and alaska_selection.get('rect4'):
            user_alaska_rect4 = alaska_selection['rect4']
            print(f"  ✓✓✓ FOUND: Using user's Alaska rect4: {user_alaska_rect4}")
        if not user_alaska_rect4 and alaska_selection.get('overlayParams'):
            overlay_params = alaska_selection['overlayParams']
            if isinstance(overlay_params, dict) and overlay_params.get('rect4'):
                user_alaska_rect4 = overlay_params['rect4']
                print(f'  ✓✓✓ FOUND: Alaska rect4 from overlayParams: {user_alaska_rect4}')
        if not user_alaska_rect4:
            raise ValueError("❌ ERROR: User's Alaska rect4 is required. User must complete the alignment step.")
        if user_alaska_rect4:
            if not isinstance(user_alaska_rect4, list) or len(user_alaska_rect4) != 4:
                raise ValueError(f"❌ ERROR: User's Alaska rect4 must be a list of 4 points, got: {user_alaska_rect4}")
            for i, corner in enumerate(user_alaska_rect4):
                if not isinstance(corner, (list, tuple)) or len(corner) != 2:
                    raise ValueError(f'❌ ERROR: Alaska rect4 corner {i} must be [x, y], got: {corner}')
        try:
            from utils.homography import rect_bounds_to_corners, homography_from_4pts, apply_homography_to_geometry
        except ImportError:
            from backend.utils.homography import rect_bounds_to_corners, homography_from_4pts, apply_homography_to_geometry
        try:
            img_check = Image.open(image_path)
            img_w, img_h = img_check.size
            img_check.close()
            print(f"\n  🔍 VERIFYING USER'S MANUAL ALIGNMENT:")
            print(f'  ✓ Image dimensions: {img_w} x {img_h} (natural pixels - SAME image user aligned on)')
            if user_alaska_rect4:
                print(f"  ✓ User's rect4 (natural pixels from frontend): {user_alaska_rect4}")
                all_in_bounds = True
                rect4_x_coords = [corner[0] for corner in user_alaska_rect4]
                rect4_y_coords = [corner[1] for corner in user_alaska_rect4]
                rect4_width = max(rect4_x_coords) - min(rect4_x_coords)
                rect4_height = max(rect4_y_coords) - min(rect4_y_coords)
                for i, (x, y) in enumerate(user_alaska_rect4):
                    if x < 0 or x > img_w or y < 0 or (y > img_h):
                        print(f'  ⚠️  WARNING: rect4 corner {i} ({x}, {y}) is outside image bounds ({img_w} x {img_h})')
                        all_in_bounds = False
                if all_in_bounds:
                    print(f'  ✓ All rect4 corners are within image bounds')
                print(f"  ✓ User's rect4 dimensions: {rect4_width} x {rect4_height} pixels")
                print(f'  ✓ Image dimensions: {img_w} x {img_h} pixels')
                print(f'  ✓ Rect4 coverage: {rect4_width / img_w * 100:.1f}% width, {rect4_height / img_h * 100:.1f}% height')
            xmin, ymin, xmax, ymax = shp_alaska.total_bounds
            src_bounds = (xmin, ymin, xmax, ymax)
            src4 = rect_bounds_to_corners(src_bounds, is_geographic=True)
            print(f'  ✓ Shapefile bounds (EPSG:5070): {src_bounds}')
            print(f'  ✓ Source corners (geographic):')
            for i, corner in enumerate(src4):
                print(f'      Corner {i}: ({corner[0]:.2f}, {corner[1]:.2f})')
            dst4 = np.array(user_alaska_rect4, dtype=float)
            print(f"  ✓ Destination corners (pixels from user's alignment):")
            for i, corner in enumerate(dst4):
                print(f'      Corner {i}: ({corner[0]:.2f}, {corner[1]:.2f})')
            H = homography_from_4pts(src4, dst4)
            print(f'  ✓ Homography matrix computed (same method as interactive overlay preview)')
            gdf_ak_px = shp_alaska.copy()
            gdf_ak_px['geometry'] = gdf_ak_px.geometry.apply(lambda geom: apply_homography_to_geometry(geom, H))
            gdf_ak_px.crs = None
            tf_xmin, tf_ymin, tf_xmax, tf_ymax = gdf_ak_px.total_bounds
            print(f'\n  ✓✓✓ SUCCESS: Alaska aligned with homography (CONUS-equivalent overlay logic)')
            print(f'    - User rect4: {user_alaska_rect4}')
            print(f'    - Transformed shapefile bounds: ({tf_xmin:.1f}, {tf_ymin:.1f}) to ({tf_xmax:.1f}, {tf_ymax:.1f})')
            if user_alaska_rect4:
                rect4_x_coords = [corner[0] for corner in user_alaska_rect4]
                rect4_y_coords = [corner[1] for corner in user_alaska_rect4]
                rect4_xmin = min(rect4_x_coords)
                rect4_ymin = min(rect4_y_coords)
                rect4_xmax = max(rect4_x_coords)
                rect4_ymax = max(rect4_y_coords)
                print(f'    - User rect4 bounds: ({rect4_xmin:.1f}, {rect4_ymin:.1f}) to ({rect4_xmax:.1f}, {rect4_ymax:.1f})')
                tolerance = 5.0
                bounds_match = abs(tf_xmin - rect4_xmin) < tolerance and abs(tf_ymin - rect4_ymin) < tolerance and (abs(tf_xmax - rect4_xmax) < tolerance) and (abs(tf_ymax - rect4_ymax) < tolerance)
                if bounds_match:
                    print(f"    ✓ Transformed shapefile bounds match user's rect4 (within {tolerance}px)")
                else:
                    print(f"    ⚠️  WARNING: Transformed shapefile bounds don't match user's rect4!")
                    print(f'       Difference: X={abs(tf_xmin - rect4_xmin):.1f}, Y={abs(tf_ymin - rect4_ymin):.1f}')
            print(f'    - This is the EXACT same transformation the user saw in the preview')
            print(f'    - RGB extraction will use FULL IMAGE (not cropped) with this exact alignment\n')
            aligned_regions.append(gdf_ak_px)
            used_manual_alignment = True
        except Exception as homography_err:
            import traceback
            error_trace = traceback.format_exc()
            print(f'\n  ❌ ERROR in homography transformation:')
            print(f'  Error: {str(homography_err)}')
            print(f'  Traceback:\n{error_trace}')
            raise ValueError(f"Failed to apply user's manual Alaska alignment: {str(homography_err)}")
    if has_hawaii and 'hawaii' in shp_regions:
        print(f'\n📍 Hawaii Alignment:')
        shp_hawaii = shp_regions['hawaii']
        hawaii_bbox = region_selections['hawaii']
        hi_x0 = int(hawaii_bbox['x'])
        hi_y0 = int(hawaii_bbox['y'])
        hi_x1 = int(hawaii_bbox['x'] + hawaii_bbox['width'])
        hi_y1 = int(hawaii_bbox['y'] + hawaii_bbox['height'])
        hi_bbox = (hi_x0, hi_y0, hi_x1, hi_y1)
        print(f'  Shapefile bounds (EPSG:5070): {shp_hawaii.total_bounds}')
        print(f'  Image bbox: {hi_bbox}')
        gdf_hi_px = fit_gdf_to_bbox_pixels(shp_hawaii, bbox=hi_bbox, polygon=None, keep_aspect=True, inset_px=2)
        if hi_x1 - hi_x0 > 50 and hi_y1 - hi_y0 > 50:
            try:
                gdf_hi_px = refine_alignment_with_edge_matching(gdf_hi_px, image_path=image_path, bbox=hi_bbox)
                print(f'  ✓ Edge detection refinement applied')
            except Exception as refine_err:
                print(f'  - Edge refinement skipped: {refine_err}')
        print(f'  ✓ Hawaii aligned bounds: {gdf_hi_px.total_bounds}')
        aligned_regions.append(gdf_hi_px)
    if len(aligned_regions) == 1:
        gdf_px = aligned_regions[0]
    else:
        gdf_px = gpd.GeoDataFrame(pd.concat(aligned_regions, ignore_index=True), crs=None)
    print(f'\n✅ FINAL ALIGNMENT SUMMARY:')
    print(f'  Regions aligned: {len(aligned_regions)}')
    print(f'  Total counties aligned: {len(gdf_px)}')
    print(f'  Final pixel bounds: {gdf_px.total_bounds}')
    print('=' * 70 + '\n')
    xmin, ymin, xmax, ymax = gdf_px.total_bounds
    if not (has_alaska or has_hawaii):
        tolerance = 20
        if not (xmin >= x0 - tolerance and xmax <= x1 + tolerance and (ymin >= y0 - tolerance) and (ymax <= y1 + tolerance)):
            print(f'  ⚠️  WARNING: Pixel-fit bounds slightly outside bbox:')
            print(f'     Pixel-fit: [{xmin:.2f}, {ymin:.2f}, {xmax:.2f}, {ymax:.2f}]')
            print(f'     Expected bbox: ({x0}, {y0}, {x1}, {y1})')
            print(f'     Tolerance: ±{tolerance}px')
    print(f'Final pixel bounds: ({xmin:.1f}, {ymin:.1f}, {xmax:.1f}, {ymax:.1f})')
    try:
        from PIL import ImageDraw
        base = Image.open(image_path).convert('RGBA')
        draw = ImageDraw.Draw(base)
        for geom in gdf_px.geometry:
            if geom is None or geom.is_empty:
                continue
            polys = geom.geoms if geom.geom_type == 'MultiPolygon' else [geom]
            for P in polys:
                draw.line(list(P.exterior.coords), fill=(255, 0, 0, 255), width=2)
        overlay_path = os.path.join(out_dir, f'{layer_name}_overlay.png')
        base.save(overlay_path)
        print(f'Saved overlay preview: {overlay_path}')
    except Exception as preview_err:
        print(f'Warning: Could not save overlay preview: {preview_err}')
        overlay_path = None
    img_full = np.array(Image.open(image_path).convert('RGB'))
    if used_manual_alignment:
        print(f"\n  🔍 Using FULL IMAGE for RGB extraction (user's manual alignment)")
        print(f'    - Shapefile is already in full image pixel coordinates')
        print(f'    - No cropping or translation needed\n')
        img_arr = img_full
        gdf_px_for_rgb = gdf_px
    else:
        print(f'\n  🔍 Using CROPPED IMAGE for RGB extraction (detected bbox)')
        print(f'    - Cropping image to bbox: ({x0}, {y0}) to ({x1}, {y1})')
        print(f'    - Translating shapefile by (-{x0}, -{y0})\n')
        img_arr = img_full[y0:y1, x0:x1]
        gdf_px_for_rgb = gdf_px.copy()
        gdf_px_for_rgb['geometry'] = gdf_px_for_rgb.geometry.apply(lambda g: shp_translate(g, xoff=-x0, yoff=-y0))
    use_panel_fit = True
    results = []
    avg_rgbs = []
    if use_panel_fit and gdf_px_for_rgb is not None and (img_arr is not None):
        h = img_arr.shape[0]
        w = img_arr.shape[1]
        print(f'  RGB extraction: Image size = {w} x {h} pixels')
        for idx, row in gdf_px_for_rgb.iterrows():
            geom = row.geometry
            gid = row['GEOID']
            if geom is None or geom.is_empty:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            try:
                mask = rasterize([(geom, 1)], out_shape=(h, w), transform=Affine.identity(), fill=0, dtype='uint8')
            except Exception:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            ys, xs = np.where(mask == 1)
            if ys.size == 0:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            pixels = img_arr[ys, xs]
            mask_valid = ~((pixels <= 5).all(axis=1) | (pixels >= 250).all(axis=1))
            if mask_valid.any():
                pixels = pixels[mask_valid]
            if pixels.size == 0:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            mean_rgb = pixels.mean(axis=0)
            rgb_list = [int(mean_rgb[0]), int(mean_rgb[1]), int(mean_rgb[2])]
            results.append({'GEOID': gid, 'rgb': rgb_list})
            avg_rgbs.append(rgb_list)
    elif aligned_regions:
        gdf_combined = gpd.GeoDataFrame(pd.concat(aligned_regions, ignore_index=True))
        transform = _raster_transform_for_image_and_shp(gdf_combined, img_w, img_h)
        for idx, row in gdf_combined.iterrows():
            geom = row.geometry
            gid = row['GEOID']
            if geom is None or geom.is_empty:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            try:
                mask = rasterize([(geom, 1)], out_shape=(img_h, img_w), transform=transform, fill=0, dtype='uint8')
            except Exception:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            ys, xs = np.where(mask == 1)
            if ys.size == 0:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            pixels = img_arr[ys, xs]
            mask_valid = ~((pixels <= 5).all(axis=1) | (pixels >= 250).all(axis=1))
            if mask_valid.any():
                pixels = pixels[mask_valid]
            if pixels.size == 0:
                results.append({'GEOID': gid, 'rgb': [None, None, None]})
                avg_rgbs.append([0, 0, 0])
                continue
            mean_rgb = pixels.mean(axis=0)
            rgb_list = [int(mean_rgb[0]), int(mean_rgb[1]), int(mean_rgb[2])]
            results.append({'GEOID': gid, 'rgb': rgb_list})
            avg_rgbs.append(rgb_list)
    for r in results:
        r['GEOID'] = str(r['GEOID']).strip().zfill(5)
    hi_pick = _hawaii_user_rgb_overrides(region_selections)
    if hi_pick:
        print(f'\n  🌺 Hawaii: applying user-picked RGB for {len(hi_pick)} counties (mark-Hawaii clicks): {list(hi_pick.keys())}')
        for i, r in enumerate(results):
            gid = r['GEOID']
            if gid not in hi_pick:
                continue
            rgb = hi_pick[gid]
            r['rgb'] = list(rgb)
            if i < len(avg_rgbs):
                avg_rgbs[i] = list(rgb)
    elif region_selections and isinstance(region_selections.get('hawaii'), dict):
        hi = region_selections['hawaii']
        has_sel = hi.get('countySelections') or hi.get('county_selections')
        if has_sel:
            print(f'\n  ⚠️  Hawaii countySelections present ({len(has_sel)} items) but no RGB parsed — check countyClick.rgb / geoid shape')
    all_rgb_values = [r['rgb'] for r in results]
    user_legend = None
    is_continuous = legend_type_info and legend_type_info.get('type') == 'continuous'
    export_bin_range_column = False
    if legend_selection:
        user_legend = extract_legend_from_selection(image_path, legend_selection, legend_type_info)
    if user_legend and len(user_legend) >= 2:
        if is_continuous:
            legend_colors = np.array([rgb for rgb, _ in user_legend])
            legend_values = [value for _, value in user_legend]
            legend_labels = [f'{value:.2f}' for _, value in user_legend]
        elif len(user_legend[0]) == 3:
            export_bin_range_column = True
            legend_colors = np.array([rgb for rgb, _, _ in user_legend])
            legend_labels = [label for _, label, _ in user_legend]
            legend_values = [value for _, _, value in user_legend]
            print(f'  ✓ Binned legend: CSV uses midpoint (or hint) per bin; GeoJSON keeps range text on bin_range: {legend_labels}')
        else:
            legend_colors = np.array([rgb for rgb, _, _ in user_legend])
            legend_labels = [label for _, label, _ in user_legend]
            legend_values = [value for _, _, value in user_legend]
            print(f'  ✓ Using bin labels from legend: {legend_labels}')
            print(f'  ✓ Using bin values from legend: {legend_values}')
            if not legend_values and legend_type_info and (legend_type_info.get('minValue') is not None) and (legend_type_info.get('maxValue') is not None):
                min_val = legend_type_info.get('minValue')
                max_val = legend_type_info.get('maxValue')
                num_bins = len(legend_colors)
                legend_values = []
                for i in range(num_bins):
                    if num_bins > 1:
                        value = min_val + (max_val - min_val) * (i / (num_bins - 1))
                    else:
                        value = min_val
                    legend_values.append(value)
                print(f'  ✓ Interpolated values from min/max: {legend_values}')
            if not legend_values:
                legend_values = list(range(len(legend_colors)))
                print(f'  ⚠️  No bin values extracted, using bin indices as values: {legend_values}')
    else:
        legend_colors = rgb_leg(all_rgb_values, n_bins)
        legend_labels = [f'Bin {i + 1}' for i in range(len(legend_colors))]
        legend_values = None
    rgb_array = np.array([r['rgb'] for r in results if r['rgb'][0] is not None])
    if len(rgb_array) > 0 and len(legend_colors) > 0:
        bin_indices = pairwise_distances_argmin(rgb_array, legend_colors)
        result_idx = 0
        for r in results:
            if r['rgb'][0] is not None:
                bin_idx = int(bin_indices[result_idx])
                if is_continuous:
                    if legend_values is not None and len(legend_values) > 0 and (bin_idx < len(legend_values)):
                        r['value'] = legend_values[bin_idx]
                    else:
                        r['value'] = None
                elif export_bin_range_column and legend_labels is not None and len(legend_labels) > 0 and (bin_idx < len(legend_labels)):
                    lbl = legend_labels[bin_idx]
                    hint = legend_values[bin_idx] if legend_values is not None and bin_idx < len(legend_values) else None
                    r['value'] = _representative_numeric_from_bin_label(lbl, hint)
                    r['bin_range_label'] = lbl
                elif legend_labels is not None and len(legend_labels) > 0 and (bin_idx < len(legend_labels)):
                    r['value'] = legend_labels[bin_idx]
                else:
                    r['value'] = None
                    if export_bin_range_column:
                        r['bin_range_label'] = None
                result_idx += 1
            else:
                r['value'] = None
                if export_bin_range_column:
                    r['bin_range_label'] = None
    else:
        for r in results:
            r['value'] = None
            if export_bin_range_column:
                r['bin_range_label'] = None
    csv_stem = (csv_basename or layer_name).strip()
    csv_stem = ''.join((c for c in csv_stem if c.isalnum() or c in ('_', '-'))) or layer_name
    csv_path = os.path.join(out_dir, f'{csv_stem}.csv')
    df_data = []
    for r in results:
        geoid = r['GEOID']
        county_name = county_names.get(geoid, geoid)
        state_name = state_names.get(geoid, '')
        if county_name == geoid or not state_name:
            for region, shp_region in shp_regions.items():
                if 'GEOID' in shp_region.columns:
                    matching = shp_region[shp_region['GEOID'].astype(str).str.zfill(5) == geoid]
                    if len(matching) > 0:
                        row_data = matching.iloc[0]
                        if county_name == geoid and 'NAME' in row_data:
                            county_name = row_data['NAME']
                        if not state_name:
                            if 'STATE_NAME' in row_data:
                                state_name = row_data['STATE_NAME']
                            elif 'STUSPS' in row_data:
                                state_name = row_data['STUSPS']
                        break
        row = {'GEOID': geoid, 'state_name': state_name, 'county_name': county_name, 'value': r.get('value')}
        df_data.append(row)
    df_out = pd.DataFrame(df_data)
    df_out = df_out.rename(columns={'GEOID': 'FIPS'})
    df_out['FIPS'] = df_out['FIPS'].astype(str).str.strip().str.zfill(5)
    df_out = df_out.sort_values('FIPS', ascending=True, kind='mergesort')
    df_out.to_csv(csv_path, index=False)
    print(f'\n🌐 EXPORTING GEOJSON:')
    shp_for_geojson_list = []
    for region in regions_to_load:
        shp_region = shp_regions_for_geojson[region].copy()
        try:
            if shp_region.crs.to_epsg() != 4326:
                shp_region = shp_region.to_crs(4326)
        except Exception:
            pass
        shp_region['GEOID'] = shp_region['GEOID'].astype(str).str.zfill(5)
        shp_for_geojson_list.append(shp_region)
        print(f'  ✓ {region.upper()}: {len(shp_region)} counties')
    if len(shp_for_geojson_list) == 1:
        shp4326 = shp_for_geojson_list[0]
    else:
        shp4326 = gpd.GeoDataFrame(pd.concat(shp_for_geojson_list, ignore_index=True), crs=4326)
    print(f'  Total counties in GeoJSON: {len(shp4326)}')
    rgb_map = {r['GEOID']: list(r['rgb']) if r.get('rgb') is not None else [None, None, None] for r in results}
    value_map = {r['GEOID']: r.get('value') for r in results}
    bin_label_map = {r['GEOID']: r.get('bin_range_label') for r in results}
    hi_pick_final = _hawaii_user_rgb_overrides(region_selections)
    for gid, rgb in hi_pick_final.items():
        rgb_map[str(gid).strip().zfill(5)] = list(rgb)
    features = []
    for _, row in shp4326.iterrows():
        row_gid = str(row['GEOID']).strip().zfill(5)
        rgb = rgb_map.get(row_gid, [None, None, None])
        county_name = county_names.get(row_gid, row_gid)
        state_name = state_names.get(row_gid, '')
        state_abbr = row.get('STUSPS', '') if 'STUSPS' in row else ''
        v_out = value_map.get(row_gid)
        props = {'GEOID': row_gid, 'name': county_name, 'state_name': state_name, 'state_abbr': state_abbr, 'STUSPS': state_abbr, 'rgb': rgb, 'value': v_out}
        if export_bin_range_column:
            br_lbl = bin_label_map.get(row_gid)
            if br_lbl is not None and str(br_lbl).strip():
                props['bin_range'] = br_lbl
        features.append({'type': 'Feature', 'geometry': mapping(row.geometry), 'properties': props})
    geojson_path = os.path.join(out_dir, f'{layer_name}.geojson')
    with open(geojson_path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f)
    if len(rgb_array) > 0:
        min_r, max_r = (rgb_array[:, 0].min(), rgb_array[:, 0].max())
        min_g, max_g = (rgb_array[:, 1].min(), rgb_array[:, 1].max())
        min_b, max_b = (rgb_array[:, 2].min(), rgb_array[:, 2].max())
    else:
        min_r = min_g = min_b = 0
        max_r = max_g = max_b = 255
    value_ranges = []
    for i, lbl in enumerate(legend_labels):
        value_ranges.append({'min': i / len(legend_labels), 'max': (i + 1) / len(legend_labels), 'label': lbl})
    legend_path = os.path.join(out_dir, f'{layer_name}_legend.json')
    with open(legend_path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'user_defined_legend' if user_legend else 'data_driven_legend', 'n_bins': len(legend_colors), 'colors': legend_colors.tolist(), 'labels': legend_labels, 'value_ranges': value_ranges, 'data_range': {'r_min': int(min_r), 'r_max': int(max_r), 'g_min': int(min_g), 'g_max': int(max_g), 'b_min': int(min_b), 'b_max': int(max_b)}}, f)
    return (csv_path, geojson_path)

def load_or_generate_geojson(layer, out_dir='data'):
    os.makedirs(out_dir, exist_ok=True)
    geojson_path = os.path.join(out_dir, f'{layer}.geojson')
    csv_path = os.path.join(out_dir, f'{layer}.csv')
    if os.path.exists(geojson_path):
        return geojson_path
    if os.path.exists(csv_path):
        _ensure_shapefile_exists()
        shp = gpd.read_file(SHAPEFILE_PATH)
        if 'GEOID' not in shp.columns:
            shp['GEOID'] = shp.index.astype(str)
        shp['GEOID'] = shp['GEOID'].astype(str).str.zfill(5)
        try:
            shp = shp.to_crs(4326)
        except Exception:
            pass
        county_data_path = os.path.join(BASE_DIR, 'cb_2024_us_county_500k', 'county_data.csv')
        county_names = {}
        state_names = {}
        if os.path.exists(county_data_path):
            county_df = pd.read_csv(county_data_path, dtype=str)
            county_df['fips_padded'] = county_df['fips'].str.zfill(5)
            county_names = dict(zip(county_df['fips_padded'], county_df['name']))
            state_names = dict(zip(county_df['fips_padded'], county_df['state']))
        df_in = pd.read_csv(csv_path, dtype=str)
        used_fips_header = 'GEOID' not in df_in.columns and 'FIPS' in df_in.columns
        if 'GEOID' not in df_in.columns and 'FIPS' in df_in.columns:
            df = df_in.rename(columns={'FIPS': 'GEOID'}).copy()
        else:
            df = df_in.copy()
        if all((col in df.columns for col in ['r', 'g', 'b'])):
            df['r'] = pd.to_numeric(df['r'], errors='coerce')
            df['g'] = pd.to_numeric(df['g'], errors='coerce')
            df['b'] = pd.to_numeric(df['b'], errors='coerce')
        if 'bin_index' in df.columns:
            df['bin_index'] = pd.to_numeric(df['bin_index'], errors='coerce')
        df['GEOID'] = df['GEOID'].astype(str).str.zfill(5)
        if 'county_name' not in df.columns:
            df['county_name'] = df['GEOID'].map(lambda x: county_names.get(x, x))
        merged = shp.merge(df, on='GEOID', how='left')
        features = []
        for _, row in merged.iterrows():
            county_name = county_names.get(row['GEOID'], row['GEOID'])
            state_name = row.get('state_name', '')
            if not state_name:
                state_name = state_names.get(row['GEOID'], '')
            props = {'GEOID': row['GEOID'], 'name': county_name, 'state_name': state_name, 'rgb': [row['r'], row['g'], row['b']] if all((col in row for col in ['r', 'g', 'b'])) else [None, None, None]}
            br_cell = row.get('bin_range') if 'bin_range' in row.index else None
            if br_cell is not None and str(br_cell).strip() != '' and str(br_cell).lower() != 'nan':
                props['bin_range'] = str(br_cell).strip()
            val_cell = row.get('value') if 'value' in row.index else None
            if val_cell is not None and str(val_cell).strip() != '' and str(val_cell).lower() != 'nan':
                vn = pd.to_numeric(pd.Series([val_cell]), errors='coerce').iloc[0]
                if pd.notna(vn):
                    props['value'] = float(vn)
                else:
                    props['value'] = str(val_cell).strip()
            elif br_cell is not None and str(br_cell).strip() != '' and str(br_cell).lower() != 'nan':
                # Legacy CSV: only bin_range (interval text), no value column
                props['value'] = str(br_cell).strip()
            features.append({'type': 'Feature', 'geometry': mapping(row.geometry), 'properties': props})
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump({'type': 'FeatureCollection', 'features': features}, f)
        if 'county_name' in df.columns:
            if 'state_name' not in df.columns:
                county_data_path = os.path.join(BASE_DIR, 'cb_2024_us_county_500k', 'county_data.csv')
                if os.path.exists(county_data_path):
                    county_df = pd.read_csv(county_data_path, dtype=str)
                    county_df['fips_padded'] = county_df['fips'].str.zfill(5)
                    state_names_map = dict(zip(county_df['fips_padded'], county_df['state']))
                    df['state_name'] = df['GEOID'].map(lambda x: state_names_map.get(x, ''))
            df_to_save = df.copy()
            if used_fips_header and 'GEOID' in df_to_save.columns:
                df_to_save = df_to_save.rename(columns={'GEOID': 'FIPS'})
            df_to_save.to_csv(csv_path, index=False)
        return geojson_path
    placeholder = {'type': 'FeatureCollection', 'features': []}
    with open(geojson_path, 'w', encoding='utf-8') as f:
        json.dump(placeholder, f)
    return geojson_path
