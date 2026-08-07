"""Join NEON's tck_fielddata (one row per plot visit) to tck_taxonomyProcessed
(one row per taxon x stage per sample).

Output is one row per visit x sexOrAge x species. Sometimes, these people went to
visit things that resulted in no detections. Those visits have an explicit 0 and null
scientific name.
"""

from pathlib import Path
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")

STAGES = ["Female", "Male", "Nymph", "Larva"]
COUNTED = ["identified", "noneDetected"]

VISIT_COLS = {
    "uid": "visitID",  # sampleID is null on zero-catch visits, so key on uid
    "sampleID": "sampleID",
    "siteID": "siteID",
    "plotID": "plotID",
    "domainID": "domainID",
    "nlcdClass": "nlcdClass",
    "decimalLatitude": "decimalLatitude",
    "decimalLongitude": "decimalLongitude",
    "elevation": "elevation",
    "collectDate": "collectDate",
    "totalSampledArea": "totalSampledArea",
    "targetTaxaPresent": "targetTaxaPresent",
    # In-field crew tallies. NEON STOPPED POPULATING THESE ON 2019-04-24.
    "adultCount": "fieldAdultCount",
    "nymphCount": "fieldNymphCount",
    "larvaCount": "fieldLarvaCount",
}


def tidy_ticks():
    field = pd.read_csv(RAW / "tck_fielddata.csv", low_memory=False)
    taxon = pd.read_csv(RAW / "tck_taxonomyProcessed.csv", low_memory=False)

    # Drop visits where sampling never happened
    field = field.drop_duplicates(subset=["plotID", "collectDate", "sampleID"])
    happened = field["totalSampledArea"].notna() | field["sampleID"].notna()
    visits = field[happened][list(VISIT_COLS)].rename(columns=VISIT_COLS)

    # Taxonomy rows with no scientificName are lab rejections because they are NOT A TICK!
    processed = set(taxon["sampleID"].dropna())
    had_ticks = set(taxon.loc[taxon["scientificName"].notna(), "sampleID"])
    got = visits["sampleID"].notna()
    visits["sampleStatus"] = "noneDetected"
    visits.loc[got & visits.sampleID.isin(had_ticks), "sampleStatus"] = "identified"
    # Collected but not yet reported by the lab
    visits.loc[got & ~visits.sampleID.isin(processed), "sampleStatus"] = "pendingIdentification"

    # NEON can log one species and stage under several
    # subsampleIDs, and those need summing
    counts = (
        taxon.dropna(subset=["sexOrAge", "scientificName"])
        .groupby(["sampleID", "sexOrAge", "scientificName"], as_index=False)
        .agg(
            individualCount=("individualCount", "sum"),
            acceptedTaxonID=("acceptedTaxonID", "first"),
            taxonRank=("taxonRank", "first"),
        )
    )

    grid = visits.merge(pd.DataFrame({"sexOrAge": STAGES}), how="cross")

    # A stage that caught two species becomes two rows.
    df = grid.merge(counts, on=["sampleID", "sexOrAge"], how="left")
    known = df["sampleStatus"].isin(COUNTED)
    df["individualCount"] = pd.to_numeric(df["individualCount"].fillna(0).where(known))

    df["collectDate"] = pd.to_datetime(df["collectDate"], format="ISO8601")
    df["year"] = df["collectDate"].dt.year
    df["lifeStage"] = df["sexOrAge"].replace({"Female": "Adult", "Male": "Adult"})
    df["isLarva"] = df["lifeStage"] == "Larva"

    df = df.sort_values(["siteID", "plotID", "collectDate", "sexOrAge"])
    df = df.reset_index(drop=True)

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "tick_observations.csv", index=False)
    return df


if __name__ == "__main__":
    tidy_ticks()