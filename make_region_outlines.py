"""
Generate outline shapefiles (linework only) from county polygon shapefiles.
Preserves ALL internal boundaries (county lines) within each region.
Creates 6 outline datasets: conus/alaska/hawaii × epsg4326/epsg5070
"""

import geopandas as gpd
from pathlib import Path

REGIONS = [
    ("conus", "cb_2024_us_county_500k_conus"),
    ("alaska", "cb_2024_us_county_500k_alaska"),
    ("hawaii", "cb_2024_us_county_500k_hawaii"),
]

PROJS = ["epsg4326", "epsg5070"]  # folder suffixes

root = Path(__file__).resolve().parent  # project root


def outline_from_folder(folder: Path) -> gpd.GeoDataFrame:
    """
    Load county polygons and extract boundaries (linework) for ALL counties.
    This preserves all internal county boundaries, not just the outer perimeter.
    """
    gdf = gpd.read_file(folder)  # polygons (counties)
    
    # Extract boundary from EACH county polygon (preserves all internal boundaries)
    # This gives us all county boundaries: both outer edges and shared edges between counties
    gdf["geometry"] = gdf.geometry.boundary  # Convert each polygon to its boundary LineString
    
    # The result is a GeoDataFrame with LineString geometries for each county boundary
    # When rendered, these will show all county lines within the region
    return gdf


def main():
    for rname, base in REGIONS:
        for proj in PROJS:
            src = root / f"{base}_{proj}"
            if not src.exists():
                print(f"⚠️  Skipping {src} - folder not found")
                continue
            
            out = root / f"{base}_{proj}_OUTLINE"
            out.mkdir(exist_ok=True)
            
            print(f"Processing {rname} / {proj}...")
            gdf_line = outline_from_folder(src)
            
            # Save as shapefile
            output_shp = out / f"{rname}_outline.shp"
            # Handle CRS issues - try to save with CRS, fallback to no CRS if needed
            try:
                gdf_line.to_file(output_shp)
            except Exception as e:
                # If CRS causes issues, try saving without CRS (shapefile will still have projection info)
                print(f"    ⚠️  CRS error, trying without explicit CRS: {e}")
                gdf_no_crs = gdf_line.copy()
                gdf_no_crs.crs = None
                gdf_no_crs.to_file(output_shp)
                # Then manually copy the .prj file from source
                import shutil
                src_prj = src / f"{base}_{proj}.prj"
                if src_prj.exists():
                    shutil.copy(src_prj, out / f"{rname}_outline.prj")
                    print(f"    ✓ Copied projection file from source")
            
            print(f"  ✓ Wrote {output_shp}")
            print(f"    CRS: {gdf_line.crs}")
            print(f"    Counties: {len(gdf_line)}")
            print(f"    Geometry type: {gdf_line.geometry.iloc[0].geom_type if len(gdf_line) > 0 else 'N/A'}")
            print()


if __name__ == "__main__":
    main()

