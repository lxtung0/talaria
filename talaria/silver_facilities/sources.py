"""Group F, source quality (spec #13, #15): four flags read from `source_urls`.

Hosts are working values only; no host list is stored. All four flags are false
when the Facility has no usable source host.
"""

import re

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from talaria.silver_facilities import reference_hosts

FLAGS = [
    "flag_has_government_source",
    "flag_own_site_in_sources",
    "flag_only_directory_sources",
    "flag_single_source_domain",
]

# Scheme and a leading `www.` are dropped; the host ends at the first `/`, `?`, `#` or `:`.
_HOST = r"^(?:[a-z][a-z0-9+.-]*://)?(?:www\.)?([^/?#:\s]+)"
# A usable host: dot-separated labels, no spaces (`not a url` and `mailto` fail).
_HOST_SHAPE = r"^[a-z0-9-]+(\.[a-z0-9-]+)+$"


def _listed(hosts: list[str]) -> str:
    """A regex matching any listed host or a subdomain of one, as a whole host."""
    return r"(^|\.)(" + "|".join(re.escape(h) for h in hosts) + r")$"


_DIRECTORY_OR_SOCIAL = _listed(reference_hosts.DIRECTORY_HOSTS + reference_hosts.SOCIAL_HOSTS)
_GOVERNMENT = "(" + "|".join(re.escape(s) for s in reference_hosts.GOVERNMENT_SUFFIXES) + ")$"


def host(col: Column) -> Column:
    """The lower-case host of a URL, without scheme or `www.`; NULL when there is no usable host."""
    value = F.regexp_extract(F.lower(F.trim(col)), _HOST, 1)
    return F.when(value.rlike(_HOST_SHAPE), value)


def add_columns(df: DataFrame) -> DataFrame:
    hosts = F.array_distinct(F.filter(F.transform(F.col("source_urls"), host), lambda h: h.isNotNull()))
    df = df.withColumn("_f_hosts", F.coalesce(hosts, F.array().cast("array<string>")))
    any_host = F.size(F.col("_f_hosts")) > 0
    own_site = host(F.col("official_website"))

    return df.withColumns(
        {
            "flag_has_government_source": F.exists(F.col("_f_hosts"), lambda h: h.rlike(_GOVERNMENT)),
            "flag_own_site_in_sources": F.coalesce(F.array_contains(F.col("_f_hosts"), own_site), F.lit(False)),
            "flag_only_directory_sources": any_host
            & F.forall(F.col("_f_hosts"), lambda h: h.rlike(_DIRECTORY_OR_SOCIAL)),
            "flag_single_source_domain": F.size(F.col("_f_hosts")) == 1,
        }
    ).drop("_f_hosts")
