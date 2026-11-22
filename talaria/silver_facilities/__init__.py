"""Silver facilities: the second and final Silver stage for facilities (spec #13).

One public entry point, `build_silver_facilities`: Silver base, bronze facilities and
bronze pincode directory DataFrames plus a run date in, Silver facilities DataFrame
out. No reads, writes or Databricks-only calls.
"""

from talaria.silver_facilities.pipeline import build_silver_facilities

__all__ = ["build_silver_facilities"]
