"""Gold district cells: each H3 res-5 cell's NFHS-5 district, for the app to look up at runtime.

One public entry point, `build_district_cells`: post offices with their NFHS-5
district and `h3_r5` (from `district_link.office_districts`; the notebook adds the
cell, since H3 functions only exist on Databricks) and Silver NFHS-5 in, one row
per cell out. No reads or writes.
"""

from talaria.gold_districts.pipeline import build_district_cells

__all__ = ["build_district_cells"]
