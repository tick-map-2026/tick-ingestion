"""NEON splits this product across two tables:
  tck_fielddata          one row per plot visit
  tck_taxonomyProcessed  one row per taxon x life stage found in a sample
"""

from pathlib import Path
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")

FIELD_COLS = [
    "sampleID",
    "siteID",
    "plotID",
    "domainID",
    "nlcdClass",
    "decimalLatitude",
    "decimalLongitude",
    "elevation",
    "collectDate",
    "totalSampledArea",
    "targetTaxaPresent",
]
TAXON_COLS = [
    "sampleID",
    "scientificName",
    "acceptedTaxonID",
    "taxonRank",
    "sexOrAge",
    "individualCount",
]


def main():
    field = pd.read_csv(RAW / "tck_fielddata.csv")
    taxon = pd.read_csv(RAW / "tck_taxonomyProcessed.csv")

    # Drop visits where sampling never happened
    sampled = field[field["totalSampledArea"].notna()][FIELD_COLS]

    df = sampled.merge(
        taxon[TAXON_COLS], on="sampleID", how="left", indicator=True
    )

    # Visits that sampled but caught nothing
    caught_nothing = df["_merge"] == "left_only"
    df.loc[caught_nothing, "individualCount"] = 0
    df.loc[caught_nothing, "scientificName"] = "none detected"
    df = df.drop(columns="_merge")

    df["collectDate"] = pd.to_datetime(df["collectDate"], format="ISO8601")
    df["year"] = df["collectDate"].dt.year
    df["dayOfYear"] = df["collectDate"].dt.dayofyear

    # NEOM's effort-corrected metric
    df["densityPer100m2"] = (
        df["individualCount"] / df["totalSampledArea"] * 100
    ).round(3)

    # Larvae are only identified to family and arrive in huge clumps, so they
    # swamp counts. Flagging them as in case we want to filter
    df["lifeStage"] = df["sexOrAge"].replace(
        {"Female": "Adult", "Male": "Adult"}
    )
    df["isLarva"] = df["lifeStage"] == "Larva"

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "tick_observations.csv", index=False)
    return df


if __name__ == "__main__":
    main()
