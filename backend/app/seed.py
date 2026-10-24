"""Demo closet and mock calendar.

The closet deliberately has NO waterproof outerwear, so the rain gap triggers in
the Seattle and NYC demos. A few items were worn recently so freshness matters.
Calendar dates are computed relative to today so the demo always works.
"""

from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, delete, select

from app.models import AgentRunRecord, WardrobeItem

# (art, name, category, subcategory, color, style, formality, season, material, brand,
#  days_since_worn | None, times_worn, favorite)
_CLOSET: list[tuple] = [
    # Tops
    ("shirt", "White Oxford Shirt", "tops", "button-down", "white", "smart casual", "business", "all season", "cotton", "Everlane", 1, 14, True),
    ("cami", "Black Silk Camisole", "tops", "camisole", "black", "formal", "formal", "spring, summer, fall", "silk", "Vince", None, 2, False),
    ("sweater", "Grey Merino Crewneck", "tops", "sweater", "heather grey", "smart casual", "smart casual", "fall, winter", "merino wool", "Uniqlo", 20, 9, False),
    ("tee_stripe", "Breton Striped Tee", "tops", "t-shirt", "navy stripe", "casual", "casual", "spring, fall", "cotton", "Saint James", 40, 6, False),
    ("mockneck", "Black Mock-Neck Knit", "tops", "sweater", "black", "smart casual", "business", "fall, winter", "fine-gauge wool", "COS", 2, 18, True),
    ("tee", "White Crew Tee", "tops", "t-shirt", "white", "casual", "casual", "all season", "organic cotton", "Pact", 5, 30, False),
    ("shirt", "Sage Linen Shirt", "tops", "button-down", "sage", "casual", "smart casual", "spring, summer", "linen", "Quince", 60, 3, False),
    # Bottoms
    ("trousers", "Black Tailored Trousers", "bottoms", "trousers", "black", "formal", "business", "all season", "wool blend", "Theory", 9, 12, True),
    ("jeans", "Dark Wash Straight Jeans", "bottoms", "jeans", "dark denim", "casual", "casual", "all season", "denim", "Levi's", 3, 40, False),
    ("trousers_wide", "Camel Wide-Leg Trousers", "bottoms", "trousers", "camel", "smart casual", "business", "fall, spring", "wool", "Aritzia", 25, 5, False),
    ("skirt", "Black Leather Midi Skirt", "bottoms", "skirt", "black", "streetwear", "smart casual", "fall, winter", "vegan leather", "& Other Stories", None, 1, False),
    # Dresses
    ("slipdress", "Black Satin Slip Dress", "dresses", "slip dress", "black", "formal", "formal", "spring, summer, fall", "satin", "Reformation", 70, 3, True),
    ("wrapdress", "Emerald Wrap Dress", "dresses", "wrap dress", "emerald", "smart casual", "smart casual", "spring, fall", "crepe", "Diane von Furstenberg", None, 0, False),
    # Outerwear (none waterproof on purpose)
    ("moto", "Black Leather Moto Jacket", "outerwear", "jacket", "black", "streetwear", "smart casual", "fall, spring", "leather", "AllSaints", 14, 22, True),
    ("coat", "Camel Wool Coat", "outerwear", "coat", "camel", "formal", "business", "fall, winter", "wool", "Max Mara", 120, 8, False),
    ("blazer", "Charcoal Blazer", "outerwear", "blazer", "charcoal", "formal", "business", "all season", "wool", "J.Crew", 10, 15, False),
    ("denimjacket", "Vintage Denim Jacket", "outerwear", "jacket", "light denim", "vintage", "casual", "spring, fall", "denim", "Levi's", 30, 11, False),
    # Shoes
    ("sneakers", "White Leather Sneakers", "shoes", "sneakers", "white", "casual", "casual", "all season", "leather", "Veja", 1, 60, True),
    ("boots", "Black Chelsea Boots", "shoes", "boots", "black", "smart casual", "smart casual", "fall, winter", "suede", "Blundstone", 6, 25, False),
    ("heels", "Black Pointed Pumps", "shoes", "heels", "black", "formal", "formal", "all season", "patent leather", "Sam Edelman", 90, 4, False),
    ("loafers", "Tan Leather Loafers", "shoes", "loafers", "tan", "smart casual", "business", "spring, fall", "leather", "G.H. Bass", 12, 10, False),
    ("runners", "Grey Running Shoes", "shoes", "running shoes", "grey", "sporty", "casual", "all season", "mesh", "Allbirds", 4, 35, False),
    # Activewear
    ("tank", "Black Running Tank", "activewear", "tank top", "black", "sporty", "casual", "spring, summer, fall", "recycled polyester", "Girlfriend Collective", 4, 20, False),
    ("leggings", "Black Running Leggings", "activewear", "leggings", "black", "sporty", "casual", "all season", "recycled nylon", "Girlfriend Collective", 4, 28, False),
    # Accessories and bags
    ("earrings", "Gold Hoop Earrings", "accessories", "jewelry", "gold", "smart casual", "smart casual", "all season", "gold vermeil", "Mejuri", 3, 40, True),
    ("necklace", "Silver Chain Necklace", "accessories", "jewelry", "silver", "streetwear", "smart casual", "all season", "sterling silver", "Mejuri", 15, 12, False),
    ("scarf", "Grey Cashmere Scarf", "accessories", "scarf", "grey", "smart casual", "smart casual", "fall, winter", "cashmere", "Naadam", 100, 6, False),
    ("tote", "Black Leather Tote", "bags", "tote", "black", "smart casual", "business", "all season", "leather", "Cuyana", 1, 50, True),
]


def closet_items(today: date | None = None) -> list[WardrobeItem]:
    today = today or date.today()
    items = []
    for n, row in enumerate(_CLOSET, start=1):
        art, name, cat, sub, color, style, formality, season, material, brand, days, worn, fav = row
        items.append(
            WardrobeItem(
                id=f"itm_seed{n:02d}",
                name=name,
                category=cat,
                subcategory=sub,
                color=color,
                style=style,
                formality=formality,
                season=season,
                material=material,
                brand=brand,
                waterproof=False,
                image_url=f"/media/seed/{n:02d}-{art}.svg",
                last_worn=None if days is None else today - timedelta(days=days),
                number_of_times_worn=worn,
                is_favorite=fav,
                source="seed",
            )
        )
    return items


def art_manifest() -> list[tuple[str, str, str]]:
    """(filename, art kind, color) for the seed image renderer."""
    return [(f"{n:02d}-{row[0]}.svg", row[0], row[4]) for n, row in enumerate(_CLOSET, start=1)]


# ---------------------------------------------------------------------------
# Mock calendar
# ---------------------------------------------------------------------------
def _next_weekday(today: date, weekday: int, *, include_today: bool = False) -> date:
    """Next date with the given weekday (Mon=0). Strictly after today unless include_today."""
    delta = (weekday - today.weekday()) % 7
    if delta == 0 and not include_today:
        delta = 7
    return today + timedelta(days=delta)


def calendar_events(today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    tue = _next_weekday(today, 1)
    wed, thu = tue + timedelta(days=1), tue + timedelta(days=2)
    sat = _next_weekday(today, 5, include_today=True)
    sun = sat + timedelta(days=1)
    mon = _next_weekday(today, 0)

    raw = [
        # Seattle tech conference trip
        (tue, "08:30", "Tech Conference Day 1", "Seattle Convention Center, Seattle", "business casual"),
        (tue, "19:30", "Team Dinner at Canlis", "Canlis, Seattle", "dressy, upscale restaurant"),
        (wed, "06:45", "Morning run", "Waterfront trail, Seattle", "athletic"),
        (wed, "09:00", "Tech Conference Day 2", "Seattle Convention Center, Seattle", "business casual"),
        (thu, "09:00", "Tech Conference Day 3 + flight home", "Seattle Convention Center, Seattle", "business casual, travel-friendly"),
        # NYC weekend
        (sat, "11:00", "Networking Brunch", "Balthazar, New York", "smart casual"),
        (sat, "19:00", "Broadway Show", "Majestic Theatre, New York", "evening, dressy-casual"),
        (sun, "10:00", "Gallery walk in Chelsea", "Chelsea, New York", "casual, lots of walking"),
        # New job
        (mon, "09:00", "First day at Northwind", "Northwind HQ (home city)", "business casual"),
    ]
    events = []
    for n, (day, time, name, location, dress) in enumerate(sorted(raw, key=lambda r: (r[0], r[1])), 1):
        events.append(
            {
                "id": f"evt_{n:02d}",
                "date": day.isoformat(),
                "start_time": time,
                "name": name,
                "location": location,
                "dress_code_hint": dress,
            }
        )
    return events


def events_between(start: date, end: date, today: date | None = None) -> list[dict[str, Any]]:
    return [e for e in calendar_events(today) if start.isoformat() <= e["date"] <= end.isoformat()]


# ---------------------------------------------------------------------------
# DB seeding
# ---------------------------------------------------------------------------
def seed_if_empty(session: Session) -> None:
    if session.exec(select(WardrobeItem).limit(1)).first() is None:
        session.add_all(closet_items())
        session.commit()


def reset(session: Session) -> int:
    """Restore the seed closet and clear runs. Returns the item count."""
    session.exec(delete(WardrobeItem))
    session.exec(delete(AgentRunRecord))
    items = closet_items()
    session.add_all(items)
    session.commit()
    return len(items)
