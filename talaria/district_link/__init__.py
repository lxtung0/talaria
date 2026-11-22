"""District link: each facility's NFHS-5 district (#44).

`build_facility_districts`: facilities, the bronze pincode directory and Silver
NFHS-5 in, one row per facility out. `office_districts`: the same link for each
post office, which Gold's district cells build on. No reads, writes or
Databricks-only calls; the alias table is a CSV next to this code.
"""

from talaria.district_link.pipeline import build_facility_districts, office_districts

__all__ = ["build_facility_districts", "office_districts"]
