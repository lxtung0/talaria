"""Silver Stage 3: capacity, large-hospital and consistency flags for facilities (#35).

One public entry point, `build_silver_stage3`: the Silver facilities DataFrame (Stage 2)
plus the reference tables in, the Stage 3 DataFrame out. No reads, writes or
Databricks-only calls; `load_references` reads the reference CSVs kept next to this code.
"""

from talaria.silver_stage3.pipeline import build_silver_stage3
from talaria.silver_stage3.references import load_references

__all__ = ["build_silver_stage3", "load_references"]
