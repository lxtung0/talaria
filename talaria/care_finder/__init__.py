"""Care finder (spec #26): a service and a location in, the best Facilities out, with evidence.

- `items`: unpacks the source Facilities table into the app tables (Spark, notebook only).
- the query flow modules (`recommend` and friends) are plain Python, so the app
  can import them without Spark.
"""
