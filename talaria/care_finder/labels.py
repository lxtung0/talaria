"""The LLM check: which hits to send, the prompt, output validation and the similarity fallback (#28 step 4).

Pure functions; the call itself lives in `backend`.
"""

import json
import re

from talaria.care_finder.settings import DEFAULT, Settings

LABELS = ("direct", "related", "unrelated")


def normalize_service(service: str) -> str:
    """The cache key for a service query: lower-case, single-spaced."""
    return " ".join(service.lower().split())


def select_for_llm(hits: list[dict], settings: Settings = DEFAULT) -> list[dict]:
    """The top `llm_hits_per_facility` hits for each of the top `llm_facilities` Facilities, by similarity."""
    by_facility: dict[str, list[dict]] = {}
    for hit in sorted(hits, key=lambda h: -h["similarity"]):
        by_facility.setdefault(hit["unique_id"], []).append(hit)
    chosen = list(by_facility.values())[: settings.llm_facilities]
    return [hit for facility_hits in chosen for hit in facility_hits[: settings.llm_hits_per_facility]]


def build_prompt(service: str, hits: list[dict]) -> list[dict]:
    items = "\n".join(f'{h["item_id"]}\t{h["item_type"]}\t{h["item_text"]}' for h in hits)
    system = (
        "You check whether short claims copied from healthcare facility records are evidence that the "
        "facility offers a service. For each item answer with one label:\n"
        '- "direct": the text itself says the facility offers this service or has the equipment for it\n'
        '- "related": the text is about the same field but does not say the service is offered\n'
        '- "unrelated": the text is not evidence for this service\n'
        "Judge only the text given. Give a reason of at most 15 words. "
        'Reply with json only: {"labels": [{"item_id": "...", "label": "...", "reason": "..."}]}'
    )
    user = f"Service: {service}\n\nItems (item_id, type, text):\n{items}\n\nAnswer in json."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_llm_output(text: str) -> list:
    """The `labels` list from the model's reply, tolerating code fences or text around the JSON."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in the reply")
    data = json.loads(match.group(0))
    labels = data.get("labels") if isinstance(data, dict) else None
    if not isinstance(labels, list):
        raise ValueError("reply has no labels list")
    return labels


def validate_labels(raw: list, sent_ids: list[str]) -> dict[str, dict]:
    """`{item_id: {label, reason}}` for every sent id.

    Keeps only ids that were sent and only the three labels; a sent item the
    reply leaves out, or labels wrongly, is `unrelated`.
    """
    sent = set(sent_ids)
    labels = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        item_id, label = entry.get("item_id"), entry.get("label")
        if item_id in sent and item_id not in labels and label in LABELS:
            labels[item_id] = {"label": label, "reason": str(entry.get("reason") or "").strip()[:200]}
    for item_id in sent_ids:
        labels.setdefault(item_id, {"label": "unrelated", "reason": "Not labelled by the check"})
    return labels


def similarity_fallback(hits: list[dict], settings: Settings = DEFAULT) -> dict[str, dict]:
    """Labels from similarity alone, used when the LLM call fails."""
    labels = {}
    for hit in hits:
        if hit["similarity"] >= settings.fallback_direct_similarity:
            label = "direct"
        elif hit["similarity"] >= settings.min_similarity:
            label = "related"
        else:
            label = "unrelated"
        labels[hit["item_id"]] = {"label": label, "reason": f"Evidence not checked (similarity {hit['similarity']:.2f})"}
    return labels
