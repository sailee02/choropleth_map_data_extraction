"""
Generate true outline shapefiles (linework only) from county polygon shapefiles.
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
    """Load county polygons, dissolve into one MultiPolygon, extract boundary as LineString."""
    gdf = gpd.read_file(folder)  # polygons (counties)
    dissolved = gdf.dissolve()  # one MultiPolygon
    outline = dissolved.geometry.boundary  # LineString/MultiLineString
    return gpd.GeoDataFrame(geometry=outline, crs=gdf.crs)


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
            gdf_line.to_file(output_shp)
            print(f"  ✓ Wrote {output_shp}")
            print(f"    CRS: {gdf_line.crs}")
            print(f"    Geometry type: {gdf_line.geometry.iloc[0].geom_type}")
            print()


if __name__ == "__main__":
    main()

