from dataclasses import dataclass


@dataclass(frozen=True)
class Chokepoint:
    name: str
    kind: str
    latitude: float
    longitude: float
    aliases: tuple[str, ...]
    strategic_note: str
    baseline_political_risk: int
    baseline_risk_note: str


CHOKEPOINTS: tuple[Chokepoint, ...] = (
    Chokepoint(
        name="Suez Canal",
        kind="Canal",
        latitude=30.5852,
        longitude=32.2654,
        aliases=("Suez", "Suez Canal"),
        strategic_note="Europe-Asia shortcut for containerized cargo, energy, bulk and industrial inputs.",
        baseline_political_risk=24,
        baseline_risk_note="Strategic route with episodic disruption risk, usually driven by Red Sea spillover, grounding, strikes or regional security.",
    ),
    Chokepoint(
        name="Panama Canal",
        kind="Canal",
        latitude=9.0800,
        longitude=-79.6800,
        aliases=("Panama", "Panama Canal"),
        strategic_note="Atlantic-Pacific shortcut exposed to drought, draft restrictions and queue pressure.",
        baseline_political_risk=18,
        baseline_risk_note="Main baseline risk is operational and climate-related rather than geopolitical.",
    ),
    Chokepoint(
        name="Strait of Hormuz",
        kind="Strait",
        latitude=26.5667,
        longitude=56.2500,
        aliases=("Hormuz", "Strait of Hormuz"),
        strategic_note="Critical Gulf exit for seaborne trade, energy flows, metals, fertilizers and regional risk.",
        baseline_political_risk=75,
        baseline_risk_note="Persistent high geopolitical and military escalation risk around Gulf maritime flows.",
    ),
    Chokepoint(
        name="Bab el-Mandeb",
        kind="Strait",
        latitude=12.5833,
        longitude=43.3333,
        aliases=("Bab el-Mandeb", "Bab al-Mandab", "Bab el Mandeb", "Red Sea"),
        strategic_note="Red Sea access point linking Suez flows to the Indian Ocean.",
        baseline_political_risk=70,
        baseline_risk_note="Elevated Red Sea security risk with direct rerouting relevance for shipping and freight.",
    ),
    Chokepoint(
        name="Strait of Malacca",
        kind="Strait",
        latitude=2.5000,
        longitude=101.0000,
        aliases=("Malacca", "Strait of Malacca", "Malacca Strait"),
        strategic_note="Main Asia trade artery for raw materials, manufactured goods and energy flows.",
        baseline_political_risk=22,
        baseline_risk_note="High strategic importance, but baseline tension is usually operational rather than acute.",
    ),
    Chokepoint(
        name="Strait of Gibraltar",
        kind="Strait",
        latitude=35.9600,
        longitude=-5.6000,
        aliases=("Gibraltar", "Strait of Gibraltar"),
        strategic_note="Mediterranean-Atlantic gateway for broad maritime trade and rerouting signals.",
        baseline_political_risk=16,
        baseline_risk_note="Strategically important but usually low baseline political disruption risk.",
    ),
    Chokepoint(
        name="Cape of Good Hope",
        kind="Cape route",
        latitude=-34.3568,
        longitude=18.4740,
        aliases=("Cape of Good Hope", "Cape route", "Cape Town", "southern Africa route"),
        strategic_note="Major rerouting corridor when Suez or Red Sea risk pushes vessels around Africa.",
        baseline_political_risk=28,
        baseline_risk_note="Risk rises mainly when Red Sea/Suez rerouting increases exposure, freight time and weather sensitivity.",
    ),
)


GENERAL_TRADE_TERMS = (
    "commodity", "commodities", "raw materials", "supply chain", "shipping", "maritime",
    "freight", "vessel", "cargo", "port", "canal", "strait", "chokepoint",
    "bulk carrier", "dry bulk", "tanker", "container", "rerouting", "congestion",
    "blockage", "disruption", "delay", "strike", "sanctions", "attack", "security",
    "piracy", "war risk", "drought", "draft restriction", "storm", "collision",
    "grounding", "accident", "iron ore", "steel", "scrap", "coal", "oil", "lng",
    "gas", "copper", "aluminium", "aluminum", "nickel", "bauxite", "grain", "wheat",
    "corn", "soybean", "fertilizer", "phosphate", "potash", "sugar", "palm oil",
)

HIGH_RISK_TERMS = (
    "blocked", "blockage", "closed", "closure", "attack", "missile", "drone",
    "piracy", "hijack", "explosion", "war risk", "rerouting", "reroute",
    "collision", "grounding", "drought", "restriction", "congestion", "strike",
    "sanction", "storm",
)

# Extra context terms used only for RSS article matching (broader than aliases)
CHOKEPOINT_CONTEXT_TERMS: dict[str, tuple[str, ...]] = {
    "Bab el-Mandeb": ("houthi", "houthis", "yemen", "gulf of aden", "red sea attack", "red sea shipping"),
    "Strait of Hormuz": ("persian gulf", "iran sanctions", "gulf tensions", "iran oil", "iran nuclear"),
    "Suez Canal": ("red sea rerouting", "red sea disruption", "port said", "suez blockage"),
    "Strait of Gibraltar": ("western mediterranean", "algeciras", "ceuta", "strait traffic"),
    "Panama Canal": ("gatun lake", "canal drought", "canal restrictions", "canal water level"),
    "Strait of Malacca": ("south china sea", "singapore strait", "piracy asia"),
    "Cape of Good Hope": ("cape route", "africa rerouting", "suez alternative", "cape storms"),
}


CURATED_RSS_FEEDS = (
    # ── Maritime / Shipping ──────────────────────────────────────────────
    "https://gcaptain.com/feed/",
    "https://safety4sea.com/feed/",
    "https://www.hellenicshippingnews.com/feed/",
    "https://www.freightwaves.com/feed/",
    "https://maritime-executive.com/rss",
    "https://splash247.com/feed/",
    "https://www.seatrade-maritime.com/rss.xml",
    "https://www.marinelink.com/rss/",
    "https://www.offshore-energy.biz/feed/",
    # ── Energy / Commodities ─────────────────────────────────────────────
    "https://oilprice.com/rss/main",
    "https://www.mining.com/feed/",
    # ── World News / Geopolitics ─────────────────────────────────────────
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.reuters.com/reuters/worldNews",
    "https://feeds.reuters.com/reuters/businessNews",
)
