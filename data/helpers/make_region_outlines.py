import geopandas as gpd
from pathlib import Path
REGIONS = [('conus', 'cb_2024_us_county_500k_conus'), ('alaska', 'cb_2024_us_county_500k_alaska'), ('hawaii', 'cb_2024_us_county_500k_hawaii')]
PROJS = ['epsg4326', 'epsg5070']
root = Path(__file__).resolve().parent

def outline_from_folder(folder: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(folder)
    gdf['geometry'] = gdf.geometry.boundary
    return gdf

def main():
    for rname, base in REGIONS:
        for proj in PROJS:
            src = root / f'{base}_{proj}'
            if not src.exists():
                print(f'⚠️  Skipping {src} - folder not found')
                continue
            out = root / f'{base}_{proj}_OUTLINE'
            out.mkdir(exist_ok=True)
            print(f'Processing {rname} / {proj}...')
            gdf_line = outline_from_folder(src)
            output_shp = out / f'{rname}_outline.shp'
            try:
                gdf_line.to_file(output_shp)
            except Exception as e:
                print(f'    ⚠️  CRS error, trying without explicit CRS: {e}')
                gdf_no_crs = gdf_line.copy()
                gdf_no_crs.crs = None
                gdf_no_crs.to_file(output_shp)
                import shutil
                src_prj = src / f'{base}_{proj}.prj'
                if src_prj.exists():
                    shutil.copy(src_prj, out / f'{rname}_outline.prj')
                    print(f'    ✓ Copied projection file from source')
            print(f'  ✓ Wrote {output_shp}')
            print(f'    CRS: {gdf_line.crs}')
            print(f'    Counties: {len(gdf_line)}')
            print(f"    Geometry type: {(gdf_line.geometry.iloc[0].geom_type if len(gdf_line) > 0 else 'N/A')}")
            print()
if __name__ == '__main__':
    main()
