"""Silver NFHS-5: the NFHS-5 district health indicators, cleaned and typed (#41).

One public entry point, `build_silver_nfhs5`: the bronze NFHS-5 DataFrame in, one
typed row per district out. No reads, writes or Databricks-only calls.
"""

from talaria.silver_nfhs5.pipeline import build_silver_nfhs5

__all__ = ["build_silver_nfhs5"]
