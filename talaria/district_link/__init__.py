"""District link: each facility's NFHS-5 district (#44).

One public entry point, `build_facility_districts`: facilities, the bronze pincode
directory and Silver NFHS-5 in, one row per facility out. No reads, writes or
Databricks-only calls; the alias table is a CSV next to this code.
"""

from talaria.district_link.pipeline import build_facility_districts

__all__ = ["build_facility_districts"]
