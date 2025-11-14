#!/usr/bin/env python3
"""
Script to visualize the US county shapefile and save it as an image.
"""

import os
import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path

# Get the shapefile path - try CONUS shapefile first, fallback to full
BASE_DIR = Path(__file__).parent
CONUS_SHAPEFILE_PATH = BASE_DIR / "cb_2024_us_county_500k_conus" / "cb_2024_us_county_500k_conus.shp"
FULL_SHAPEFILE_PATH = BASE_DIR / "cb_2024_us_county_500k" / "cb_2024_us_county_500k.shp"

def visualize_shapefile(output_path="shapefile_visualization.png", use_conus=True):
    """Load and visualize the shapefile, saving it as an image."""
    
    # Try CONUS shapefile first if requested, otherwise use full
    if use_conus and CONUS_SHAPEFILE_PATH.exists():
        SHAPEFILE_PATH = CONUS_SHAPEFILE_PATH
        print("Using CONUS-only shapefile")
    elif FULL_SHAPEFILE_PATH.exists():
        SHAPEFILE_PATH = FULL_SHAPEFILE_PATH
        print("Using full US shapefile (will filter to CONUS)")
    else:
        raise FileNotFoundError(f"No shapefile found. Checked:\n  {CONUS_SHAPEFILE_PATH}\n  {FULL_SHAPEFILE_PATH}")
    
    print(f"Loading shapefile from {SHAPEFILE_PATH}...")
    
    # Load the shapefile
    gdf = gpd.read_file(SHAPEFILE_PATH)
    
    print(f"Loaded {len(gdf)} counties")
    print(f"CRS: {gdf.crs}")
    print(f"Bounds: {gdf.total_bounds}")
    
    # If using full shapefile, filter to CONUS only
    if SHAPEFILE_PATH == FULL_SHAPEFILE_PATH:
        if "GEOID" not in gdf.columns:
            gdf["GEOID"] = gdf.index.astype(str)
        gdf["GEOID"] = gdf["GEOID"].astype(str).str.zfill(5)
        
        # Filter out Alaska (02) and Hawaii (15)
        gdf = gdf[~gdf["GEOID"].str.startswith(("02", "15"))].copy()
    
    gdf_conus = gdf.copy()
    
    print(f"CONUS counties: {len(gdf_conus)}")
    
    # Project to a nice projection for visualization (Albers Equal Area for CONUS)
    if gdf_conus.crs is None:
        gdf_conus = gdf_conus.set_crs(4269, allow_override=True)  # NAD83
    
    # Use CONUS Albers (EPSG:5070) for better visualization
    gdf_conus = gdf_conus.to_crs(5070)
    
    # Get CONUS bounds for cropping - no margin, tight to bounds
    bounds = gdf_conus.total_bounds
    minx, miny, maxx, maxy = bounds
    
    print(f"CONUS bounds: x=[{minx:.0f}, {maxx:.0f}], y=[{miny:.0f}, {maxy:.0f}]")
    
    # Calculate aspect ratio to eliminate white space
    width = maxx - minx
    height = maxy - miny
    aspect_ratio = width / height
    
    # Create figure with matching aspect ratio (scale to reasonable size)
    base_size = 12
    fig_width = base_size * aspect_ratio
    fig_height = base_size
    
    # Create the visualization with no margins
    fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height))
    
    # Plot the counties with borders
    gdf_conus.plot(
        ax=ax,
        facecolor='lightblue',
        edgecolor='navy',
        linewidth=0.3,
        alpha=0.7
    )
    
    # Crop to CONUS bounds exactly (no margin)
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    
    # Remove axes for cleaner look
    ax.axis('off')
    
    # Remove all margins and padding - set exactly to data bounds
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_aspect('equal')
    ax.margins(0, 0)
    
    # Save the figure with no padding
    output_full_path = BASE_DIR / output_path
    plt.savefig(output_full_path, dpi=300, bbox_inches='tight', pad_inches=0, facecolor='white')
    print(f"\n✓ Image saved to: {output_full_path}")
    print(f"  File size: {output_full_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    plt.close()
    
    return output_full_path

if __name__ == "__main__":
    try:
        output_file = visualize_shapefile("shapefile_visualization.png")
        print(f"\n✓ Success! You can now share '{output_file}' with your professor.")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

