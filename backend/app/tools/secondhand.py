"""suggest_secondhand_item: search links only. No scraping, nothing that can fail live."""

from typing import Optional
from urllib.parse import quote_plus

from app.tools.context import RunContext, ToolOutput


def links_for(query: str) -> list[dict[str, str]]:
    q = quote_plus(query)
    return [
        {"site": "Depop", "url": f"https://www.depop.com/search/?q={q}"},
        {"site": "ThredUp", "url": f"https://www.thredup.com/products?query={q}"},
        {"site": "Poshmark", "url": f"https://poshmark.com/search?query={q}"},
        {"site": "eBay (pre-owned)", "url": f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_ItemCondition=3000"},
    ]


def suggest_secondhand_item(ctx: RunContext, description: str, why: Optional[str] = None, size: Optional[str] = None) -> ToolOutput:
    query = f"{description} {size}".strip() if size else description
    ref = f"S{len(ctx.suggestions) + 1}"
    suggestion = {
        "suggestion_ref": ref,
        "description": description,
        "why": why or "Fills a gap your closet can't cover for this trip.",
        "links": links_for(query),
    }
    ctx.suggestions[ref] = suggestion
    return ToolOutput(
        result=suggestion,
        title=f"Suggested secondhand: {description}",
        detail="Search links on Depop, ThredUp, Poshmark and eBay",
    )
