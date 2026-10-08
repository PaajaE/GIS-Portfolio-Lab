"""Study area, paths, sources and scenario definitions. Single place for every assumption."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
OUT = DATA / "out"
WEB_DATA = ROOT / "web" / "data"
PROVENANCE = ROOT / "provenance"

TOWN_ID = 8  # Amherst, MA (MassGIS town id)
TOWN_NAME = "Amherst"
CRS = "EPSG:26986"  # NAD83 / Massachusetts Mainland, metres
AOI_BUFFER_M = 250  # constraint layers reach beyond the town line (buffers + kernels)
CELL_M = 2.0  # analysis grid; see METHOD.md "Harmonization"

MASSGIS_AGOL = "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services"
MASSGIS_AGS = "https://arcgisserver.digital.mass.gov/arcgisserver/rest/services"

# name -> (layer query URL, where clause, out fields). Geometry filter = AOI envelope
# unless where already restricts to the town.
VECTOR_SOURCES = {
    "town": (f"{MASSGIS_AGOL}/TOWNSSURVEY_POLYM/FeatureServer/0", f"TOWN_ID={TOWN_ID}", "TOWN,TOWN_ID"),
    "parcels": (
        f"{MASSGIS_AGOL}/Massachusetts_Property_Tax_Parcels/FeatureServer/0",
        f"TOWN_ID={TOWN_ID}",
        # Owner names / owner addresses are deliberately not harvested.
        "MAP_PAR_ID,LOC_ID,POLY_TYPE,TOWN_ID,PROP_ID,FY,LOT_SIZE,LOT_UNITS,USE_CODE,USE_DESC,"
        "SITE_ADDR,ZONING,YEAR_BUILT,BLD_AREA,UNITS,TOTAL_VAL",
    ),
    "flood": (
        f"{MASSGIS_AGS}/FEMA/FEMA_National_Flood_Hazard_Layer/FeatureServer/0",
        "1=1",
        "DFIRM_ID,VERSION_ID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,SOURCE_CIT",
    ),
    "wetlands": (
        f"{MASSGIS_AGOL}/DEP_Wetlands/FeatureServer/1",
        "1=1",
        "WETCODE,IT_VALC,IT_VALDESC,POLY_CODE,SOURCE",
    ),
    "streams": (
        f"{MASSGIS_AGOL}/1_25_000_USGS_MassDEP_Hydrography/FeatureServer/0",
        "ARC_CODE IN (4,5,6,11)",
        "ARC_CODE,MINOR_TOT,NAME,RESOLUTION,SOURCE",
    ),
    "waterbodies": (
        f"{MASSGIS_AGOL}/1_25_000_USGS_MassDEP_Hydrography/FeatureServer/1",
        "1=1",
        "NAME,POLY_CODE,MINOR_TOT,PWSID,SOURCE",
    ),
    "openspace": (
        f"{MASSGIS_AGS}/AGOL/openspace/FeatureServer/0",
        "1=1",
        "POLY_ID,SITE_NAME,OWNER_TYPE,PRIM_PURP,PUB_ACCESS,LEV_PROT,ARTICLE97,OS_TYPE,LOC_ID,CAL_DATE_R",
    ),
    "roads": (
        f"{MASSGIS_AGOL}/MassDOTRoads_gdb/FeatureServer/0",
        "1=1",
        "STREETNAME,CLASS,RDTYPE,ADMIN_TYPE,F_CLASS,JURISDICTN,SURFACE_TP,FACILITY,RD_SEG_ID",
    ),
    "buildings": (
        f"{MASSGIS_AGOL}/Building_Structures/FeatureServer/0",
        "1=1",
        "STRUCT_ID,SOURCE,SOURCEDATE,AREA_SQ_FT,ARCHIVED",
    ),
    "sewer": (
        f"{MASSGIS_AGS}/AGOL/DEP_SEWER_SERVICE_AREAS/FeatureServer/2",
        "1=1",
        "SYSTNAME,PERMIT_ID,TOWNNAME,SERVCECONF,SERVCEYEAR",
    ),
}

# NHESP Priority Habitats of Rare Species: statewide shapefile (no hosted layer found).
PRIHAB_URL = "https://s3.us-east-1.amazonaws.com/download.massgis.digital.mass.gov/shapefiles/state/prihab.zip"

# USGS 3DEP 1 m DEM, project MA_Western_B24 (COG tiles, EPSG:26918, NAVD88 m).
DEM_TNM_API = (
    "https://tnmaccess.nationalmap.gov/api/v1/products?"
    "datasets=Digital%20Elevation%20Model%20(DEM)%201%20meter&outputFormat=JSON&max=100&bbox="
)
DEM_PROJECT = "MA_Western_B24"

# ---------------------------------------------------------------------------
# Scenarios: hard-constraint thresholds. Rationale per value is in METHOD.md.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "conservative": {
        "slope_pct": 15.0,
        "wetland_buffer_m": 50.0,
        "perennial_stream_buffer_m": 61.0,  # 200 ft riverfront area
        "other_stream_buffer_m": 30.0,
        "flood": "sfha_and_0.2pct",
        "protection_levels": ("P", "T", "L"),  # in perpetuity, temporary, limited
        "exclude_priority_habitat": True,
        "yard_m": 10.0,
        "exclude_chapter_land": True,
    },
    "moderate": {
        "slope_pct": 25.0,
        "wetland_buffer_m": 30.0,  # ~100 ft Wetlands Protection Act buffer zone
        "perennial_stream_buffer_m": 30.0,
        "other_stream_buffer_m": 15.0,
        "flood": "sfha",
        "protection_levels": ("P",),
        "exclude_priority_habitat": False,
        "yard_m": 6.0,
        "exclude_chapter_land": False,
    },
    "aggressive": {
        "slope_pct": 35.0,
        "wetland_buffer_m": 15.0,  # ~50 ft no-disturb zone common in local bylaws
        "perennial_stream_buffer_m": 15.0,
        "other_stream_buffer_m": 8.0,
        "flood": "floodway",
        "protection_levels": ("P",),
        "exclude_priority_habitat": False,
        "yard_m": 3.0,
        "exclude_chapter_land": False,
    },
}
SCENARIO_ORDER = ("conservative", "moderate", "aggressive")

# Morphology / patch definition (constant across scenarios, varied in sensitivity runs)
OPEN_SIZE_CELLS = 5  # 5 x 5 cells at 2 m = a 10 m x 10 m square must fit
CONNECTIVITY = 4
MIN_PATCH_M2 = 500.0  # a patch smaller than this is not counted as a usable patch
