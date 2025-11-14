#!/usr/bin/env python3
"""
Script to create a CONUS-only shapefile from the full US county shapefile.
This excludes Alaska (FIPS starting with 02) and Hawaii (FIPS starting with 15).
"""

import geopandas as gpd
from pathlib import Path

# Get the shapefile paths
BASE_DIR = Path(__file__).parent
INPUT_SHAPEFILE = BASE_DIR / "cb_2024_us_county_500k" / "cb_2024_us_county_500k.shp"
OUTPUT_DIR = BASE_DIR / "cb_2024_us_county_500k_conus"
OUTPUT_SHAPEFILE = OUTPUT_DIR / "cb_2024_us_county_500k_conus.shp"

def create_conus_shapefile():
    """Create a CONUS-only shapefile."""
    
    # Check if input shapefile exists
    if not INPUT_SHAPEFILE.exists():
        raise FileNotFoundError(f"Shapefile not found at {INPUT_SHAPEFILE}")
    
    print(f"Loading shapefile from {INPUT_SHAPEFILE}...")
    
    # Load the shapefile
    gdf = gpd.read_file(INPUT_SHAPEFILE)
    
    print(f"Loaded {len(gdf)} counties")
    print(f"Original CRS: {gdf.crs}")
    print(f"Original bounds: {gdf.total_bounds}")
    
    # Ensure GEOID column exists
    if "GEOID" not in gdf.columns:
        gdf["GEOID"] = gdf.index.astype(str)
    gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(5)
    
    # Filter to CONUS only - exclude:
    # - Alaska (02)
    # - Hawaii (15) 
    # - Territories: American Samoa (60), Guam (66), Northern Mariana Islands (69), 
    #                Puerto Rico (72), US Virgin Islands (78)
    non_conus_states = ("02", "15", "60", "66", "69", "72", "78")
    gdf_conus = gdf[~gdf["GEOID"].str.startswith(non_conus_states)].copy()
    
    print(f"\nCONUS counties: {len(gdf_conus)}")
    print(f"Filtered out {len(gdf) - len(gdf_conus)} counties (Alaska, Hawaii, and territories)")
    print(f"CONUS bounds: {gdf_conus.total_bounds}")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Save the CONUS-only shapefile
    print(f"\nSaving CONUS shapefile to {OUTPUT_SHAPEFILE}...")
    gdf_conus.to_file(OUTPUT_SHAPEFILE)
    
    print(f"✓ CONUS shapefile created successfully!")
    print(f"  Location: {OUTPUT_SHAPEFILE}")
    print(f"  Counties: {len(gdf_conus)}")
    print(f"  CRS: {gdf_conus.crs}")
    
    # Verify the files were created
    required_files = [
        OUTPUT_SHAPEFILE,
        OUTPUT_DIR / "cb_2024_us_county_500k_conus.shx",
        OUTPUT_DIR / "cb_2024_us_county_500k_conus.dbf",
    ]
    
    print("\nCreated files:")
    for f in required_files:
        if f.exists():
            size_kb = f.stat().st_size / 1024
            print(f"  ✓ {f.name} ({size_kb:.1f} KB)")
        else:
            print(f"  ✗ {f.name} (missing!)")
    
    return OUTPUT_SHAPEFILE

if __name__ == "__main__":
    try:
        output_file = create_conus_shapefile()
        print(f"\n✓ Success! CONUS shapefile ready for use.")
        print(f"\nYou can now update your code to use:")
        print(f"  {output_file}")
        print(f"\nOr set the environment variable:")
        print(f"  SHAPEFILE_PATH={output_file}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

