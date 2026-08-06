"""NEON splits this product across two tables:
  tck_fielddata          one row per plot visit
  tck_taxonomyProcessed  one row per taxon x life stage found in a sample

sampleID is the join key. It is NEON's sample barcode, formatted as
plotID.YYYYMMDD (e.g. ABBY_001.20160831), so it identifies one plot visit.
NEON only issues one when ticks were actually collected, so a blank sampleID
on a visit that happened means "we dragged and found nothing" -- it is a real
zero, not a missing value.
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
    # Field-crew counts. Not a substitute for the taxonomy table (no species),
    # but they are the only record of what was caught in samples the lab has
    # not processed yet. Like totalSampledArea these repeat across every taxon
    # row of a sample -- do not sum them without collapsing to sampleID first.
    "adultCount",
    "nymphCount",
    "larvaCount",
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
    field = pd.read_csv(RAW / "tck_fielddata.csv", low_memory=False)
    taxon = pd.read_csv(RAW / "tck_taxonomyProcessed.csv", low_memory=False)

    # One visit (UKFS_018 2015-10-20) is recorded twice under different uids,
    # identical in every other respect. Keeping both would double-count it.
    field = field.drop_duplicates(subset=["plotID", "collectDate", "sampleID"])

    # Drop visits where sampling never happened -- these are all samplingImpractical
    # (flooded, snow covered, logistical) and are absences of effort, not zeros.
    # Keep a visit that produced a sample even if the area is missing, otherwise
    # confirmed detections get silently dropped (SERC_002.20220810). Those rows
    # carry a real count with no effort denominator, so density comes out NaN.
    happened = field["totalSampledArea"].notna() | field["sampleID"].notna()
    sampled = field[happened][FIELD_COLS]

    # Merge only the rows that have a key. pandas treats NaN as a matchable
    # merge key, so joining the blanks straight through risks a cartesian
    # product against any null sampleID that shows up on the taxonomy side.
    has_sample = sampled[sampled["sampleID"].notna()]
    no_sample = sampled[sampled["sampleID"].isna()].copy()

    matched = has_sample.merge(
        taxon[TAXON_COLS], on="sampleID", how="left", indicator=True
    )

    # Three distinct outcomes, previously collapsed into one:
    #
    #   identified            joined to a taxonomy record
    #   noneDetected          visit happened, no ticks collected -> a true 0
    #   pendingIdentification sample was collected but the lab has not published
    #                         taxonomy for it -> unknown, NOT a 0
    #
    # Calling that third group 0 understates density. It is ~427 visits, split
    # between recent lab lag and older samples that were never processed.
    pending = matched["_merge"] == "left_only"
    matched["sampleStatus"] = "identified"
    matched.loc[pending, "sampleStatus"] = "pendingIdentification"
    matched.loc[pending, "individualCount"] = pd.NA
    matched = matched.drop(columns="_merge")

    # No barcode. Almost always a genuine zero-catch visit, but a handful of
    # rows claim targetTaxaPresent == "Y" with no sample to back it up
    # (DELA_001 2015-06-02); those are unresolved rather than zero.
    no_sample["sampleStatus"] = "noneDetected"
    no_sample["individualCount"] = 0.0
    no_sample["scientificName"] = "none detected"
    contradictory = no_sample["targetTaxaPresent"] == "Y"
    no_sample.loc[contradictory, "sampleStatus"] = "unresolved"
    no_sample.loc[contradictory, "individualCount"] = pd.NA
    no_sample.loc[contradictory, "scientificName"] = pd.NA

    df = pd.concat([matched, no_sample], ignore_index=True)
    df["individualCount"] = pd.to_numeric(df["individualCount"])

    df["collectDate"] = pd.to_datetime(df["collectDate"], format="ISO8601")
    df["year"] = df["collectDate"].dt.year
    df["dayOfYear"] = df["collectDate"].dt.dayofyear

    # NEON's effort-corrected metric. NaN wherever the count is unknown or the
    # sampled area is missing, so it never fabricates a zero.
    df["densityPer100m2"] = (
        df["individualCount"] / df["totalSampledArea"] * 100
    ).round(3)

    # Larvae are only identified to family and arrive in huge clumps, so they
    # swamp counts. Flagging them as in case we want to filter
    df["lifeStage"] = df["sexOrAge"].replace(
        {"Female": "Adult", "Male": "Adult"}
    )
    df["isLarva"] = df["lifeStage"] == "Larva"

    df = df.sort_values(["siteID", "plotID", "collectDate"]).reset_index(drop=True)

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "tick_observations.csv", index=False)
    report(df, taxon)
    return df


def report(df, taxon):
    """Reconciliation, so a bad join is visible instead of silent."""
    print(f"{len(df):,} rows")
    print(df["sampleStatus"].value_counts().to_string())

    visits = df["sampleID"].nunique(dropna=True) + df["sampleID"].isna().sum()
    print(f"{visits:,} plot visits")

    joined = df.loc[df["sampleStatus"] == "identified", "individualCount"].sum()
    print(f"individuals: {joined:,.0f} joined of {taxon['individualCount'].sum():,.0f} in taxonomy")

    stranded = df["individualCount"].notna() & df["totalSampledArea"].isna()
    if stranded.any():
        print(f"{stranded.sum()} counted rows have no sampled area (density NaN)")

    unknown = df["sampleStatus"].isin(["pendingIdentification", "unresolved"])
    caught = df.loc[unknown, ["adultCount", "nymphCount", "larvaCount"]].fillna(0)
    print(
        f"{unknown.sum()} visits with unknown taxonomy hold at least "
        f"{caught.to_numpy().sum():,.0f} field-counted ticks (excluded from density)"
    )


if __name__ == "__main__":
    main()
