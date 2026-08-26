from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
paths = [
    ROOT/'data/processed/rainfall/chirps_v3_dekad_district_2015-01-01_2025-12-31.csv',
    ROOT/'data/processed/rainfall/chirps_v3_daily_district_2015-01-01_2025-12-31.csv',
    ROOT/'data/processed/vegetation/mod13q1_v061_district_2015-01-01_2025-12-31.csv',
    ROOT/'data/processed/climate/nasa_power_district_daily_20000101_20251231.csv.gz',
    ROOT/'data/processed/climate/nasa_power_district_dekadal_20000101_20251231.csv.gz',
    ROOT/'data/processed/river_levels/river_levels_canonical.csv',
    ROOT/'data/processed/river_station_metadata.csv',
    ROOT/'data/processed/food_security/ipc_outcomes_canonical.csv',
    ROOT/'data/processed/food_security/ipc_geographic_mapping.csv',
    ROOT/'data/processed/market_prices/wfp_food_prices_canonical.csv',
    ROOT/'data/processed/population/district_population_2025.csv',
]
for p in paths:
    print('\n###', p.relative_to(ROOT), p.exists(), p.stat().st_size if p.exists() else None)
    if not p.exists():
        continue
    d = pd.read_csv(p, nrows=8)
    print('columns=', list(d.columns))
    print(d.head(3).to_dict('records'))
