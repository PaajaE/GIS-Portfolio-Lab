"""Study area, paths, sources and fixed assumptions. Single place for every constant."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
OUT = DATA / "out"
PROVENANCE = ROOT / "provenance"
VALIDATION = ROOT / "validation"

CRS = "EPSG:26917"  # NAD83 / UTM zone 17N, metres (native CRS of the 3DEP tiles)
CELL_M = 5  # analysis grid (PLAN §3)
BUFFER_M = 2000  # AOI buffer: largest kernel (250 m) + watersheds crossing county lines (PLAN §5)
SEED = 20261008

# Owner decision 2026-10-08: AOI = Buncombe + Yancey; Watauga = separate temporal test.
STATE_FIPS = "37"
REGIONS = {
    "aoi": {"Buncombe County": "021", "Yancey County": "199"},
    "watauga": {"Watauga County": "189"},
}

# Triggered domain (PLAN §0b): MRMS 72 h storm total >= this, mm. Scenario values in sensitivity.
TRIGGER_MM = 250
TRIGGER_MM_SENSITIVITY = (200, 300)

# --- sources -------------------------------------------------------------------------------
TIGER_COUNTIES = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1"
WBD = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer"  # layer 5 = HUC-10, 6 = HUC-12
NCGS_INVENTORY = (
    "https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/NC_Landslide_Inventory/FeatureServer"
)
NCGS_INVENTORY_LAYERS = {0: "observations", 1: "ground_ruptures", 2: "features"}
NCGS_GEOLOGY = (
    "https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/Geologic_Map_of_North_Carolina/FeatureServer/3"
)
NC_BUILDINGS = (
    "https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/"
    "North_Carolina_Composite_Building_Footprints/FeatureServer/0"
)  # licence not stated: local analysis only (DATA_SOURCES.md)
MRMS = "https://noaa-mrms-pds.s3.amazonaws.com/CONUS/MultiSensor_QPE_72H_Pass2_00.00/20240928/"
MRMS_FILES = (  # 72 h windows ending 2024-09-28 00Z and 12Z; cell-wise maximum covers 25 Sep 00Z -> 28 Sep 12Z
    "MRMS_MultiSensor_QPE_72H_Pass2_00.00_20240928-000000.grib2.gz",
    "MRMS_MultiSensor_QPE_72H_Pass2_00.00_20240928-120000.grib2.gz",
)
MRLC_WCS = "https://www.mrlc.gov/geoserver/ows"
MRLC_COVERAGES = {
    "nlcd2021": "mrlc_download__NLCD_2021_Land_Cover_L48",
    "tcc2021": "mrlc_download__nlcd_tcc_conus_2021_v2021-4",
}
SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
TIGER_ROADS = "https://www2.census.gov/geo/tiger/TIGER2024/ROADS/tl_2024_{state}{county}_roads.zip"
TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
DEM_DATASET = "Digital Elevation Model (DEM) 1 meter"
DEM_NODATA = -999999.0
# Mosaic priority where 3DEP projects overlap (all pre-event): the AOI's own 2017 collection first, so the
# Watauga test uses the same lidar collection wherever it exists; then NC Phase 4 (2016-17); then TN (2016).
DEM_PROJECT_PRIORITY = ("NC_Phase5_2018_A18", "NC_Phase4_2017_A17", "TN_Eastern_2_16_B16_Del4_2016")
OUT_NODATA = -9999.0
