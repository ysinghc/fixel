"""What a model call costs, from the usage the API reports (prices: dev.meta.ai pricing page, Standard mode)."""

# per 1M tokens: (input, cached input, output)
TOKEN_PRICES = {
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.2-contributor": (0.10, 0.002, 0.20),
}
SAM_PER_IMAGE = 2.50 / 1000
IMAGE_EACH = 0.01


def model_of(kind: str, model: str | None) -> str | None:
    if model:
        return model
    if kind.startswith("sam"):
        return "sam-3.1"
    return None


def usd(kind: str, model: str | None, usage: dict | None, source: str = "live") -> float:
    """Dollars for one model.call event. Cached answers cost nothing."""
    if source != "live" or not usage:
        return 0.0
    m = model_of(kind, model)
    if m == "sam-3.1":
        return (usage.get("images") or 1) * SAM_PER_IMAGE
    if m == "muse-image-1.0":
        return IMAGE_EACH
    price = TOKEN_PRICES.get(m or "")
    if not price:
        return 0.0
    inp = usage.get("input_tokens") or 0
    cached = ((usage.get("input_tokens_details") or {}).get("cached_tokens")) or 0
    out = usage.get("output_tokens") or 0
    return ((inp - cached) * price[0] + cached * price[1] + out * price[2]) / 1_000_000
