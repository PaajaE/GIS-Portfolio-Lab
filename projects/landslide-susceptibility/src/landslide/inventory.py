"""NCGS inventory attribute normalisation and the positive / exclusion rules (PLAN §6).

The service mixes spellings ("2024/09/27 Helene", "2024-09-27 Helene", "Helene 09/27/2024") and stores
confidence as long coded strings ("High: Mapper has high confidence ..."). Everything downstream uses the
normalised columns defined here, so the rule is written once and tested on a fixture.
"""

from __future__ import annotations

import re

import pandas as pd

CONF_LEVELS = ("High", "Moderate", "Low")


def storm_event(s: str | None) -> str:
    """Map an AssociatedStorm value to an event key: 'helene', '1940-08', other dated year, or 'undated'."""
    s = s.strip() if isinstance(s, str) else ""
    if not s:
        return "undated"
    if "helene" in s.lower():
        return "helene"
    if s.startswith("1940/08") or s.startswith("1940-08"):
        return "1940-08"
    m = re.match(r"^(1[89]\d\d|20\d\d)", s)
    return m.group(1) if m else "other"


def conf_level(s: str | None) -> str | None:
    """'High: Mapper has ...' -> 'High'; None stays None."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    head = str(s).split(":")[0].strip()
    return head if head in CONF_LEVELS else None


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Add event, existence/location confidence levels, phase and natural flags."""
    out = df.copy()
    out["event"] = out["AssociatedStorm"].map(storm_event)
    out["exist_conf"] = out["ExistenceConfidence"].map(conf_level)
    out["loc_conf"] = out["LocationConfidence"].map(conf_level)
    ft = out["FeatureType"].fillna("")
    out["is_source"] = ft.str.startswith("Source Area")
    out["natural"] = out["SlopeModifier"].eq("None Apparent")
    # Road / trail / terrace runoff or agricultural activity concentrating water onto the slope: an
    # anthropogenic trigger even where the slope itself was not cut or filled (99 % of "Road Embankment"
    # source areas carry "Road Runoff"; METHOD decisions log 2026-10-09)
    runoff = out["RunoffModifier"] if "RunoffModifier" in out else pd.Series(None, index=out.index, dtype=object)
    out["natural_runoff"] = runoff.isna() | runoff.eq("None Apparent")
    return out


def positive_mask(df: pd.DataFrame, event: str = "helene", confs=("High", "Moderate"),
                  require_natural_runoff: bool = True) -> pd.Series:
    """Primary positive definition: source areas of the event with no apparent slope modifier and (by
    default) no runoff modifier, existence AND location confidence in `confs` (PLAN §6).
    `require_natural_runoff=False` gives the slope-modifier-only variant used in the feasibility check.
    Transport zones and deposits are never positives."""
    m = (
        df["event"].eq(event)
        & df["is_source"]
        & df["natural"]
        & df["exist_conf"].isin(confs)
        & df["loc_conf"].isin(confs)
    )
    return m & df["natural_runoff"] if require_natural_runoff else m
