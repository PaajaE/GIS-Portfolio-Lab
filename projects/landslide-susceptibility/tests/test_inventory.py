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
    rows = [  # (storm, type, modifier, exist, loc, expected)
        ("2024/09/27 Helene", "Source Area", "None Apparent", H, H, True),
        ("Helene 09/27/2024", "Source Area (Reactivated)", "None Apparent", M, M, True),
        ("2024/09/27 Helene", "Source Area", "Road Cut", H, H, False),        # road-related
        ("2024/09/27 Helene", "Source Area", None, H, H, False),             # modifier not assessed
        ("2024/09/27 Helene", "Deposit", "None Apparent", H, H, False),       # never a positive
        ("2024/09/27 Helene", "Transport Zone", "None Apparent", H, H, False),
        ("2024/09/27 Helene", "Source Area", "None Apparent", L, H, False),   # low existence confidence
        ("2024/09/27 Helene", "Source Area", "None Apparent", H, L, False),   # low location confidence
        ("1940/08/13-14", "Source Area", "None Apparent", H, H, False),       # other event
        (None, "Source Area", "None Apparent", H, H, False),                  # undated
    ]
    df = pd.DataFrame(rows, columns=["AssociatedStorm", "FeatureType", "SlopeModifier", "ExistenceConfidence",
                                     "LocationConfidence", "expected"])
    got = positive_mask(normalise(df))
    assert got.tolist() == df["expected"].tolist()
