"""Silver base: the first Silver stage for facilities (spec #1).

One public entry point, `build_silver_base`: bronze facilities DataFrame in,
Silver base DataFrame out. No reads, writes or Databricks-only calls.
"""

from talaria.silver_base.pipeline import build_silver_base

__all__ = ["build_silver_base"]
