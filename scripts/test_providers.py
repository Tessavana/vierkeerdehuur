import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_config
from src.filters import evaluate_rental
from src.providers import RotsvastProvider, VbtProvider, VestedaProvider

config = load_config()
for cls, url in (
    (VbtProvider, "https://www.vbtverhuurmakelaars.nl/huurwoningen-eindhoven"),
    (RotsvastProvider, "https://www.rotsvast.nl/woningaanbod/huur/eindhoven/"),
    (VestedaProvider, "https://www.vesteda.com/nl/huurwoningen-eindhoven"),
):
    p = cls(url)
    listings = p.fetch()
    suitable = sum(1 for l in listings if evaluate_rental(l, config)[0])
    print(p.__class__.__name__, "parsed", len(listings), "suitable", suitable)
