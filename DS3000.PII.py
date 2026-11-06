
import requests
import pandas as pd
from pathlib import Path

# --------------------------------------------------
# PART 1: PROJECT SETUP
# --------------------------------------------------

API_URL = (
    "https://api.waterdata.usgs.gov/ogcapi/v1/"
    "collections/daily/items"
)

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

SITE = "USGS-01435000"

# Urban/rural classification still needs verification
AREA_TYPE = "Unknown"

# Verified USGS time series from the metadata results
TIME_SERIES = {
    "streamflow": "ea0befb1e5684ae1a1efa98337f514ca",
    "water_temperature": "f80fcea1c1f14bd095aca16f1c6f0d47"
}

PARAMETERS = {
    "streamflow": "00060",
    "water_temperature": "00010"
}

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

print("Project: Streamflow and Water Quality")
print("Monitoring station:", SITE)


# --------------------------------------------------
# PART 2: COLLECT DATA FROM USGS
# --------------------------------------------------

def fetch_usgs_data(site, parameter, start_date, end_date):
    """Retrieve daily mean observations from the USGS API."""

    params = {
        "monitoring_location_id": site,
        "parameter_code": parameter,
        "statistic_id": "00003",
        "datetime": f"{start_date}/{end_date}",
        "limit": 500,
        "f": "json"
    }

    records = []
    url = API_URL

    with requests.Session() as session:
        while url:
            response = session.get(
                url,
                params=params,
                timeout=40
            )

            response.raise_for_status()
            result = response.json()

            for feature in result.get("features", []):
                records.append(feature["properties"])

            next_url = None

            for link in result.get("links", []):
                if link.get("rel") == "next":
                    next_url = link["href"]
                    break

            url = next_url
            params = None

    return pd.DataFrame(records)


# Retrieve both variables
all_data = []

for variable, parameter in PARAMETERS.items():

    data = fetch_usgs_data(
        SITE,
        parameter,
        START_DATE,
        END_DATE
    )

    print(f"\n{variable}: {len(data)} records retrieved")

    if data.empty:
        raise ValueError(f"No data found for {variable}")

    # Use only the verified time series
    selected_id = TIME_SERIES[variable]

    data = data[
        data["time_series_id"] == selected_id
    ].copy()

    print(f"{variable}: {len(data)} records after filtering")

    if data.empty:
        raise ValueError(
            f"No records matched selected series for {variable}"
        )

    data["variable"] = variable
    data["site"] = SITE
    data["area_type"] = AREA_TYPE

    all_data.append(data)

raw_data = pd.concat(all_data, ignore_index=True)

print("\nTotal selected observations:", len(raw_data))


# --------------------------------------------------
# PART 3: CLEAN THE DATA
# --------------------------------------------------

clean_data = raw_data.copy()

# Convert dates to datetime
clean_data["date"] = pd.to_datetime(
    clean_data["time"],
    errors="coerce"
).dt.normalize()

# Convert measurements to numbers
clean_data["value"] = pd.to_numeric(
    clean_data["value"],
    errors="coerce"
)

# Remove missing values
clean_data = clean_data.dropna(
    subset=["date", "value"]
)

# Check measurement units
print("\nMeasurement units:")
print(
    clean_data.groupby("variable")[
        "unit_of_measure"
    ].unique()
)

# Check for duplicate observations
duplicate_count = clean_data.duplicated(
    subset=["site", "date", "variable"]
).sum()

print("\nDuplicate observations:", duplicate_count)

# Prevent conflicting measurements from being merged
if duplicate_count > 0:
    raise ValueError(
        "Duplicate dates remain within a selected time series."
    )

print("Clean observations:", len(clean_data))


# --------------------------------------------------
# PART 4: MERGE STREAMFLOW AND TEMPERATURE
# --------------------------------------------------

# Convert long-format observations to wide format
merged_data = clean_data.pivot(
    index=["site", "area_type", "date"],
    columns="variable",
    values="value"
).reset_index()

merged_data.columns.name = None

# Keep days with both measurements
paired_data = merged_data.dropna(
    subset=["streamflow", "water_temperature"]
).copy()

# Sort chronologically
paired_data = paired_data.sort_values("date")

print("\n--- MERGED DATA RESULTS ---")

print("Total station-days:", len(merged_data))
print("Days with both measurements:", len(paired_data))

print("\nFirst five paired observations:")
print(paired_data.head())


# --------------------------------------------------
# PART 5: CHECK DATA QUALITY
# --------------------------------------------------

print("\n--- DATA QUALITY CHECK ---")

print("\nMissing values:")
print(merged_data.isna().sum())

print("\nSummary statistics:")
print(
    paired_data[
        ["streamflow", "water_temperature"]
    ].describe()
)

# Confirm there is enough data for exploratory analysis
if len(paired_data) >= 30:
    print("\nSUCCESS: Sufficient paired observations for initial analysis.")
else:
    print("\nWARNING: Fewer than 30 paired observations.")

if AREA_TYPE == "Unknown":
    print(
        "NOTE: Site classification still needs verification. "
        "Urban/rural comparison is not ready."
    )


# --------------------------------------------------
# PART 6: SAVE CLEANED DATA
# --------------------------------------------------

merged_data.to_csv(
    DATA_DIR / "all_station_days.csv",
    index=False
)

paired_data.to_csv(
    DATA_DIR / "paired_streamflow_water_quality.csv",
    index=False
)

print("\nSaved cleaned datasets to:", DATA_DIR.resolve())

print("\nData collection and cleaning completed.")
