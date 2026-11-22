"""Formatting of contact and location values (spec #1, "Formatting").

Each function takes and returns a Spark `Column` holding one whitespace-normalized
text value, so the same rule formats a plain column or, inside `F.transform`,
every item of a list column. A value that can't be formatted is returned exactly
as it was.
"""

from pyspark.sql import Column
from pyspark.sql import functions as F


def format_pin(col: Column) -> Column:
    """`201 301` -> `201301`: spaces and hyphens removed when 6 digits remain; otherwise unchanged."""
    stripped = F.regexp_replace(col, r"[ -]", "")
    return F.when(stripped.rlike(r"^[0-9]{6}$"), stripped).otherwise(col)


def format_phone(col: Column) -> Column:
    """`+91` followed by 10 digits; a toll-free number keeps its full digits after `+91`.

    Non-digits are removed, then: 12 digits starting `91` and toll-free numbers
    (`91` then 1800 or 1860) get a leading `+`; 10 digits, and a toll-free number
    written without `91` (1800 or 1860 then 7 digits), get `+91`, so both ways of
    writing a number end up equal. A value written with a leading `+` but no `91`
    names another country code (`+2382247959`, the US `+1 800 ...`) and, like
    anything else, keeps its original text.
    """
    digits = F.regexp_replace(col, r"[^0-9]", "")
    no_country_code = ~col.startswith("+")
    return (
        F.when(digits.rlike(r"^91(1800|1860)[0-9]+$"), F.concat(F.lit("+"), digits))
        .when(digits.rlike(r"^91[0-9]{10}$"), F.concat(F.lit("+"), digits))
        .when(digits.rlike(r"^[0-9]{10}$") & no_country_code, F.concat(F.lit("+91"), digits))
        .when(digits.rlike(r"^(1800|1860)[0-9]{7}$") & no_country_code, F.concat(F.lit("+91"), digits))
        .otherwise(col)
    )


# A basic `local@domain.tld` address.
_EMAIL = r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$"


def format_email(col: Column) -> Column:
    """Lower-cased, `[at]`/`(at)`/` at `/`[dot]`/`(dot)` decoded; kept only if it is then an address."""
    decoded = F.lower(col)
    decoded = F.regexp_replace(decoded, r" ?[\[(]at[\])] ?| at ", "@")
    decoded = F.regexp_replace(decoded, r" ?[\[(]dot[\])] ?", ".")
    return F.when(decoded.rlike(_EMAIL), decoded).otherwise(col)


# Optional `http(s)://` and `www.`, then the host, then the rest (path, query, fragment).
_URL = r"^(?i)(?:https?://)?(?:www\.)?([^/?#]*)(.*)$"
# A host name with at least one dot and an optional port.
_HOST = r"^[a-z0-9-]+(\.[a-z0-9-]+)+(:[0-9]+)?$"


def _host_and_port(col: Column) -> Column:
    return F.lower(F.regexp_extract(col, _URL, 1))


def url_host(col: Column) -> Column:
    """The lower-cased host, without scheme, leading `www.`, port or path.

    Not validated: text with no recognisable host gives whatever stands in the host's place.
    """
    return F.regexp_replace(_host_and_port(col), ":[0-9]+$", "")


def format_url(col: Column) -> Column:
    """Host lower-cased; scheme, leading `www.` and trailing `/` removed; path and its case kept.

    A value without a recognisable host (`Not Available Online`) is unchanged.
    """
    host = _host_and_port(col)
    rest = F.regexp_replace(F.regexp_extract(col, _URL, 2), r"/+$", "")
    return F.when(host.rlike(_HOST), F.concat(host, rest)).otherwise(col)
