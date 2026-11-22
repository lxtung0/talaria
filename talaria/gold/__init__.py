"""Gold: the first layer that judges Facilities (spec #37).

One public entry point, `build_gold`: Silver facilities DataFrame in,
`(gold_facilities, gold_facility_items)` out. No reads, writes or Databricks-only calls.
"""

from talaria.gold.pipeline import build_gold

__all__ = ["build_gold"]
