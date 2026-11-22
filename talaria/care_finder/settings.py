"""Every tunable number in the care finder query flow (spec #26: placeholders, kept in one module)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Expanding search loop (H3 resolution 5).
    h3_resolution: int = 5
    min_direct_facilities: int = 3  # stop once this many Facilities have a `direct` hit
    max_k: int = 15  # about 250 km
    small_k_limit: int = 4  # grow k by 1 up to here,
    large_k_step: int = 2  # then by this much

    # Vector Search and the LLM check.
    results_per_round: int = 75
    # Similarity is cosine on databricks-gte-large-en embeddings. Measured on the data:
    # "kidney machine" → "State-of-the-art dialysis machines" is 0.76, so the spec's
    # placeholder 0.80 would drop the very match the app is meant to find.
    min_similarity: float = 0.70  # hits below this are dropped
    fallback_direct_similarity: float = 0.90  # similarity fallback: >= this is direct, else related
    llm_hits_per_facility: int = 5
    llm_facilities: int = 15

    # Scoring.
    label_values: dict = field(default_factory=lambda: {"direct": 1.0, "related": 0.4})
    type_weights: dict = field(
        default_factory=lambda: {
            "equipment": 0.7,
            "procedure": 0.7,
            "capability": 0.6,
            "description_sentence": 0.5,
            "specialty": 0.25,
        }
    )
    hits_per_type: int = 2  # only the best this many hits of each type count
    distance_decay_km: dict = field(default_factory=lambda: {"emergency": 25.0, "planned": 100.0})
    # Affordability: free or low-cost Facilities rank a little higher where fewer households
    # are insured (NFHS-5, the entered location's H3 cell). rank × (1 + boost × tier × uninsured share).
    affordability_values: dict = field(default_factory=lambda: {"government": 1.0, "charitable": 0.67, "public": 0.33})
    affordability_max_boost: float = 0.15  # government, where no household is insured: rank × 1.15
    uninsured_share_default: float = 0.59  # no area figure: NFHS-5 India, 41% of households insured

    # Bands.
    evidence_bands: tuple = (("strong", 0.75), ("some", 0.5))  # above 0 otherwise: "mention only"
    confidence_bands: tuple = (("high", 0.7), ("medium", 0.5))  # high is strictly above 0.7

    # Results.
    top_n: int = 3
    others_n: int = 3

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


DEFAULT = Settings()
