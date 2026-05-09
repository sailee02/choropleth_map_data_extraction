#!/usr/bin/env python3
import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union
from pathlib import Path
BASE_DIR = Path(__file__).parent
INPUT_SHAPEFILE = BASE_DIR / 'cb_2024_us_county_500k_conus' / 'cb_2024_us_county_500k_conus.shp'
OUTPUT_DIR = BASE_DIR / 'cb_2024_us_county_500k_conus'
OUTPUT_SHAPEFILE = OUTPUT_DIR / 'cb_2024_us_county_500k_conus.shp'

def clip_conus_shapefile():
    if not INPUT_SHAPEFILE.exists():
        raise FileNotFoundError(f'Shapefile not found at {INPUT_SHAPEFILE}')
    print(f'Loading shapefile from {INPUT_SHAPEFILE}...')
    gdf = gpd.read_file(INPUT_SHAPEFILE)
    print(f'Loaded {len(gdf)} counties')
    print(f'Original CRS: {gdf.crs}')
    print(f'Original bounds: {gdf.total_bounds}')
    print('\nCreating CONUS boundary from union of all counties...')
    print('  (This may take a moment...)')
    conus_boundary = unary_union(gdf.geometry)
    print(f'CONUS boundary created (type: {conus_boundary.geom_type})')
    print('\nClipping county geometries to CONUS boundary...')
    gdf_clipped = gdf.copy()
    gdf_clipped['geometry'] = gdf_clipped.geometry.intersection(conus_boundary)
    gdf_clipped = gdf_clipped[~gdf_clipped.geometry.is_empty]
    print(f'After clipping: {len(gdf_clipped)} counties')
    print(f'New bounds: {gdf_clipped.total_bounds}')
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f'\nSaving clipped CONUS shapefile to {OUTPUT_SHAPEFILE}...')
    gdf_clipped.to_file(OUTPUT_SHAPEFILE)
    print(f'✓ CONUS shapefile clipped successfully!')
    print(f'  Location: {OUTPUT_SHAPEFILE}')
    print(f'  Counties: {len(gdf_clipped)}')
    print(f'  CRS: {gdf_clipped.crs}')
    required_files = [OUTPUT_SHAPEFILE, OUTPUT_DIR / 'cb_2024_us_county_500k_conus.shx', OUTPUT_DIR / 'cb_2024_us_county_500k_conus.dbf']
    print('\nUpdated files:')
    for f in required_files:
        if f.exists():
            size_kb = f.stat().st_size / 1024
            print(f'  ✓ {f.name} ({size_kb:.1f} KB)')
        else:
            print(f'  ✗ {f.name} (missing!)')
    return OUTPUT_SHAPEFILE
if __name__ == '__main__':
    try:
        output_file = clip_conus_shapefile()
        print(f'\n✓ Success! CONUS shapefile clipped - extra borders removed.')
        print(f'\nThe shapefile at {output_file} is now ready for use.')
    except Exception as e:
        print(f'✗ Error: {e}')
        import traceback
        traceback.print_exc()
