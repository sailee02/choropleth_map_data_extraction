#!/usr/bin/env python3
"""
Script to create shapefiles in different projections (EPSG:4326 and EPSG:5070).
Creates both CONUS-only versions in each projection.
"""

import geopandas as gpd
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONUS_SHAPEFILE = BASE_DIR / "cb_2024_us_county_500k_conus" / "cb_2024_us_county_500k_conus.shp"
FULL_SHAPEFILE = BASE_DIR / "cb_2024_us_county_500k" / "cb_2024_us_county_500k.shp"

def create_projected_shapefiles():
    """Create shapefiles in EPSG:4326 and EPSG:5070 projections."""
    
    # Load CONUS shapefile (currently in EPSG:4269)
    if not CONUS_SHAPEFILE.exists():
        raise FileNotFoundError(f"CONUS shapefile not found at {CONUS_SHAPEFILE}")
    
    print(f"Loading CONUS shapefile from {CONUS_SHAPEFILE}...")
    gdf_conus = gpd.read_file(CONUS_SHAPEFILE)
    
    print(f"Original CRS: {gdf_conus.crs}")
    print(f"Counties: {len(gdf_conus)}")
    
    # Ensure we have a CRS
    if gdf_conus.crs is None:
        gdf_conus = gdf_conus.set_crs(4269, allow_override=True)
    
    # Create EPSG:4326 version
    print("\nCreating EPSG:4326 (WGS84) version...")
    gdf_4326 = gdf_conus.to_crs(4326)
    
    output_dir_4326 = BASE_DIR / "cb_2024_us_county_500k_conus_epsg4326"
    output_dir_4326.mkdir(exist_ok=True)
    output_file_4326 = output_dir_4326 / "cb_2024_us_county_500k_conus_epsg4326.shp"
    
    gdf_4326.to_file(output_file_4326)
    print(f"✓ Saved: {output_file_4326}")
    print(f"  CRS: {gdf_4326.crs}")
    print(f"  Bounds: {gdf_4326.total_bounds}")
    
    # Create EPSG:5070 version
    print("\nCreating EPSG:5070 (CONUS Albers) version...")
    gdf_5070 = gdf_conus.to_crs(5070)
    
    output_dir_5070 = BASE_DIR / "cb_2024_us_county_500k_conus_epsg5070"
    output_dir_5070.mkdir(exist_ok=True)
    output_file_5070 = output_dir_5070 / "cb_2024_us_county_500k_conus_epsg5070.shp"
    
    gdf_5070.to_file(output_file_5070)
    print(f"✓ Saved: {output_file_5070}")
    print(f"  CRS: {gdf_5070.crs}")
    print(f"  Bounds: {gdf_5070.total_bounds}")
    
    # Also create full versions if full shapefile exists
    if FULL_SHAPEFILE.exists():
        print(f"\nCreating full shapefile versions (including Alaska/Hawaii)...")
        gdf_full = gpd.read_file(FULL_SHAPEFILE)
        
        if gdf_full.crs is None:
            gdf_full = gdf_full.set_crs(4269, allow_override=True)
        
        # Filter to CONUS + Alaska + Hawaii (exclude territories)
        if "GEOID" not in gdf_full.columns:
            gdf_full["GEOID"] = gdf_full.index.astype(str)
        gdf_full["GEOID"] = gdf_full["GEOID"].astype(str).str.zfill(5)
        gdf_full_us = gdf_full[~gdf_full["GEOID"].str.startswith(("60", "66", "69", "72", "78"))].copy()
        
        # EPSG:4326 full version (CONUS + Alaska + Hawaii)
        gdf_full_4326 = gdf_full_us.to_crs(4326)
        output_dir_full_4326 = BASE_DIR / "cb_2024_us_county_500k_full_epsg4326"
        output_dir_full_4326.mkdir(exist_ok=True)
        output_file_full_4326 = output_dir_full_4326 / "cb_2024_us_county_500k_full_epsg4326.shp"
        gdf_full_4326.to_file(output_file_full_4326)
        print(f"✓ Saved full (US): {output_file_full_4326}")
        
        # EPSG:5070 full version (CONUS + Alaska + Hawaii)
        gdf_full_5070 = gdf_full_us.to_crs(5070)
        output_dir_full_5070 = BASE_DIR / "cb_2024_us_county_500k_full_epsg5070"
        output_dir_full_5070.mkdir(exist_ok=True)
        output_file_full_5070 = output_dir_full_5070 / "cb_2024_us_county_500k_full_epsg5070.shp"
        gdf_full_5070.to_file(output_file_full_5070)
        print(f"✓ Saved full (US): {output_file_full_5070}")
    
    print("\n✓ All projected shapefiles created successfully!")
    return True

if __name__ == "__main__":
    try:
        create_projected_shapefiles()
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

