from fastapi import APIRouter, HTTPException

from app.services.location import reverse_geocode

router = APIRouter(prefix="/api/location", tags=["location"])


@router.get("/reverse")
def reverse(lat: float, lon: float) -> dict:
    place = reverse_geocode(lat, lon)
    if not place:
        raise HTTPException(404, "Couldn't find a city for those coordinates")
    return place
