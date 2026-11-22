"""The district alias table (#44): pincode-directory district -> NFHS-5 district.

NFHS-5 (2019-21) uses older district names than the India Post directory, and
lacks districts carved out since. `reference/district_aliases.csv` maps every
directory district whose name doesn't equal an NFHS district of its state. A
carved-out district maps to the district it came from and is `approximate`.
An empty `nfhs_district` means NFHS-5 has no row for it. Reviewed like code.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

ALIAS_CSV = Path(__file__).parent / "reference" / "district_aliases.csv"


@dataclass(frozen=True)
class DistrictAlias:
    state: str  # official state name (Silver base OFFICIAL_STATES)
    directory_district: str  # as the directory writes it
    nfhs_district: str | None  # as Silver NFHS-5 writes it; None: no NFHS-5 row
    approximate: bool
    note: str


def load_aliases(path: Path = ALIAS_CSV) -> list[DistrictAlias]:
    with open(path, newline="", encoding="utf-8") as file:
        return [
            DistrictAlias(
                row["state"].strip(),
                row["directory_district"].strip(),
                row["nfhs_district"].strip() or None,
                row["approximate"].strip().lower() == "true",
                row["note"].strip(),
            )
            for row in csv.DictReader(file)
        ]
