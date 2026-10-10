"""Inventory normalisation and the positive rule on a fixture covering every spelling and phase."""

import pandas as pd

from landslide.inventory import conf_level, normalise, positive_mask, storm_event

H = "High: Mapper has high confidence the feature is a LS."
M = "Moderate: Moderate confidence the feature is a LS."
L = "Low: Low confidence the feature is a LS."


def test_storm_event_spellings():
    assert storm_event("2024/09/27 Helene") == "helene"
    assert storm_event("2024-09-27 Helene") == "helene"
    assert storm_event("Helene 09/27/2024") == "helene"
    assert storm_event("1940/08/13-14") == "1940-08"
    assert storm_event("1940/08/28-31") == "1940-08"
    assert storm_event("2004/09/06-17") == "2004"
    assert storm_event(" ") == "undated"
    assert storm_event(None) == "undated"
    assert storm_event("Active") == "other"


def test_conf_level():
    assert conf_level(H) == "High" and conf_level(M) == "Moderate" and conf_level(L) == "Low"
    assert conf_level(None) is None and conf_level("High") == "High" and conf_level("x") is None


def test_positive_mask():
    NA = "None Apparent"
    rows = [  # storm, type, slope modifier, existence, location, runoff modifier, primary, slope-only variant
        ("2024/09/27 Helene", "Source Area", NA, H, H, NA, True, True),
        ("Helene 09/27/2024", "Source Area (Reactivated)", NA, M, M, None, True, True),  # runoff not assessed
        ("2024/09/27 Helene", "Source Area", NA, H, H, "Road Runoff", False, True),     # road drainage trigger
        ("2024/09/27 Helene", "Source Area", "Road Cut", H, H, NA, False, False),       # road cut
        ("2024/09/27 Helene", "Source Area", None, H, H, NA, False, False),             # modifier not assessed
        ("2024/09/27 Helene", "Deposit", NA, H, H, NA, False, False),                   # never a positive
        ("2024/09/27 Helene", "Transport Zone", NA, H, H, NA, False, False),
        ("2024/09/27 Helene", "Source Area", NA, L, H, NA, False, False),               # low existence conf.
        ("2024/09/27 Helene", "Source Area", NA, H, L, NA, False, False),               # low location conf.
        ("1940/08/13-14", "Source Area", NA, H, H, NA, False, False),                   # other event
        (None, "Source Area", NA, H, H, NA, False, False),                              # undated
    ]
    df = pd.DataFrame(rows, columns=["AssociatedStorm", "FeatureType", "SlopeModifier", "ExistenceConfidence",
                                     "LocationConfidence", "RunoffModifier", "primary", "variant"])
    n = normalise(df)
    assert positive_mask(n).tolist() == df["primary"].tolist()
    assert positive_mask(n, require_natural_runoff=False).tolist() == df["variant"].tolist()
