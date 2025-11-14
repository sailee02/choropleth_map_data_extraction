#!/usr/bin/env python3
"""
Script to create separate shapefiles for CONUS, Alaska, and Hawaii.
Creates shapefiles in both EPSG:4326 and EPSG:5070 projections.
"""

import geopandas as gpd
from pathlib import Path

BASE_DIR = Path(__file__).parent
FULL_SHAPEFILE = BASE_DIR / "cb_2024_us_county_500k" / "cb_2024_us_county_500k.shp"

def create_separate_region_shapefiles():
    """Create separate CONUS, Alaska, and Hawaii shapefiles in both projections."""
    
    if not FULL_SHAPEFILE.exists():
        raise FileNotFoundError(f"Full shapefile not found at {FULL_SHAPEFILE}")
    
    print(f"Loading full shapefile from {FULL_SHAPEFILE}...")
    gdf = gpd.read_file(FULL_SHAPEFILE)
    
    # Ensure GEOID column exists
    if "GEOID" not in gdf.columns:
        gdf["GEOID"] = gdf.index.astype(str)
    gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(5)
    
    print(f"Total counties: {len(gdf)}")
    print(f"Original CRS: {gdf.crs}")
    
    # Separate regions
    gdf_conus = gdf[~gdf["GEOID"].str.startswith(("02", "15", "60", "66", "69", "72", "78"))].copy()
    gdf_alaska = gdf[gdf["GEOID"].str.startswith("02")].copy()
    gdf_hawaii = gdf[gdf["GEOID"].str.startswith("15")].copy()
    
    print(f"\nSeparated regions:")
    print(f"  CONUS: {len(gdf_conus)} counties")
    print(f"  Alaska: {len(gdf_alaska)} counties")
    print(f"  Hawaii: {len(gdf_hawaii)} counties")
    
    # Ensure CRS is set
    if gdf.crs is None:
        gdf_conus = gdf_conus.set_crs(4269, allow_override=True)
        gdf_alaska = gdf_alaska.set_crs(4269, allow_override=True)
        gdf_hawaii = gdf_hawaii.set_crs(4269, allow_override=True)
    
    regions = {
        "conus": gdf_conus,
        "alaska": gdf_alaska,
        "hawaii": gdf_hawaii
    }
    
    projections = {
        "4326": 4326,
        "5070": 5070
    }
    
    print("\n" + "=" * 70)
    print("CREATING SEPARATE REGION SHAPEFILES")
    print("=" * 70)
    
    for region_name, gdf_region in regions.items():
        if len(gdf_region) == 0:
            print(f"\n⚠️  Skipping {region_name.upper()} (no counties)")
            continue
            
        print(f"\n📂 Processing {region_name.upper()}:")
        print(f"  Counties: {len(gdf_region)}")
        print(f"  Bounds: {gdf_region.total_bounds}")
        
        for proj_name, epsg_code in projections.items():
            # Create directory
            output_dir = BASE_DIR / f"cb_2024_us_county_500k_{region_name}_epsg{proj_name}"
            output_dir.mkdir(exist_ok=True)
            
            # Project to target CRS
            gdf_projected = gdf_region.to_crs(epsg_code)
            
            # Save shapefile
            output_file = output_dir / f"cb_2024_us_county_500k_{region_name}_epsg{proj_name}.shp"
            gdf_projected.to_file(output_file)
            
            print(f"  ✓ EPSG:{epsg_code} → {output_file}")
            print(f"    Bounds: {gdf_projected.total_bounds}")
    
    print("\n" + "=" * 70)
    print("✅ All separate region shapefiles created successfully!")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    try:
        create_separate_region_shapefiles()
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

