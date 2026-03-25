from __future__ import annotations

import os
from html import escape
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.schemas.travel import PlanRequest, PlanResponse


class PlannerService:
    def __init__(self) -> None:
        self.rapidapi_key = os.getenv("RAPIDAPI_KEY", "")
        self.foursquare_key = os.getenv("FOURSQUARE_API_KEY", "")

    async def generate(self, req: PlanRequest) -> PlanResponse:
        weather = await self._weather_brief(req.city, req.check_in)
        hotels_data = await self._fetch_hotels(req.city, req.check_in, req.check_out, req.adults)
        restaurants_data = await self._fetch_restaurants(req.city)
        attractions_data = await self._fetch_attractions(req.city)
        currency_data = await self._currency_brief(req.budget_currency, "USD", req.budget_amount)

        hotels = self._hotel_brief(req.city, hotels_data)
        restaurants = self._restaurant_brief(req.city, restaurants_data)
        attractions = self._attraction_brief(req.city, attractions_data)
        budget_optimizer = self._budget_optimizer(req, hotels_data, restaurants_data, attractions_data)
        itinerary = self._itinerary(req, weather, hotels, restaurants, attractions, budget_optimizer)

        final_response = self._compose_final(
            city=req.city,
            weather=weather,
            hotels=hotels,
            restaurants=restaurants,
            attractions=attractions,
            currency=currency_data,
            itinerary=itinerary,
            budget_optimizer=budget_optimizer,
        )

        return PlanResponse(
            destination=req.city,
            weather=weather,
            hotels=hotels,
            restaurants=restaurants,
            attractions=attractions,
            currency=currency_data,
            itinerary=itinerary,
            budget_optimizer=budget_optimizer,
            final_response=final_response,
            generated_at=datetime.utcnow().isoformat(),
        )

    async def _weather_brief(self, city: str, target_date: date) -> str:
        coords = await self._geocode(city)
        if not coords:
            return "Could not resolve city coordinates for weather forecast."

        lat, lon, resolved_name = coords
        current = await self._current_weather(lat, lon)
        expected = await self._historical_expectation(lat, lon, target_date)

        if not expected:
            if current:
                return (
                    f"For {resolved_name} around {target_date.isoformat()}, seasonal archive data was unavailable, "
                    "so this outlook is based on current conditions only.\n"
                    f"Right now it feels {current['comfort_phrase']}, around {self._format_temp(current['temp_c'])}, "
                    f"with humidity near {current['humidity_pct']:.0f}%."
                )
            return "Weather forecast data is currently unavailable for this destination."

        day_band = self._temperature_band(expected["avg_max_c"])
        rain_phrase = self._rain_phrase(expected["avg_rain_mm"])
        packing_tip = self._packing_tip(expected["avg_min_c"], expected["avg_max_c"], expected["avg_rain_mm"])

        lines = [
            (
                f"If you visit {resolved_name} around {target_date.isoformat()}, expect mostly {day_band} weather. "
                f"Typical daytime feels around {self._format_temp(expected['avg_max_c'])}, "
                f"and early mornings or evenings can drop to about {self._format_temp(expected['avg_min_c'])}."
            ),
            f"Rain outlook: {rain_phrase} (about {expected['avg_rain_mm']:.1f} mm/day in seasonal averages).",
            f"How to dress: {packing_tip}",
        ]

        if current:
            lines.append(
                (
                    f"Current snapshot: {self._format_temp(current['temp_c'])} with humidity near "
                    f"{current['humidity_pct']:.0f}% ({current['comfort_phrase']})."
                )
            )

        return "\n".join(lines)

    async def _geocode(self, city: str) -> tuple[float, float, str] | None:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": city, "count": 1, "language": "en", "format": "json"}

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.get(url, params=params)
                data = res.json()
            results = data.get("results", [])
            if not results:
                return None
            top = results[0]
            return float(top["latitude"]), float(top["longitude"]), top.get("name", city)
        except Exception:
            return None

    async def _current_weather(self, lat: float, lon: float) -> dict[str, float | str] | None:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "timezone": "auto",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.get(url, params=params)
                data = res.json()
            current = data.get("current", {})
            t = current.get("temperature_2m")
            h = current.get("relative_humidity_2m")
            if t is None or h is None:
                return None

            temp_c = float(t)
            humidity_pct = float(h)
            return {
                "temp_c": temp_c,
                "humidity_pct": humidity_pct,
                "comfort_phrase": self._comfort_phrase(temp_c, humidity_pct),
            }
        except Exception:
            return None

    async def _historical_expectation(self, lat: float, lon: float, target_date: date) -> dict[str, float] | None:
        ref = target_date.replace(year=max(target_date.year - 1, 2000))
        start = ref - timedelta(days=1)
        end = ref + timedelta(days=1)

        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.get(url, params=params)
                data = res.json()

            daily = data.get("daily", {})
            tmax = daily.get("temperature_2m_max", [])
            tmin = daily.get("temperature_2m_min", [])
            rain = daily.get("precipitation_sum", [])

            if not tmax or not tmin:
                return None

            avg_max = sum(tmax) / len(tmax)
            avg_min = sum(tmin) / len(tmin)
            avg_rain = (sum(rain) / len(rain)) if rain else 0.0

            return {
                "avg_max_c": float(avg_max),
                "avg_min_c": float(avg_min),
                "avg_rain_mm": float(avg_rain),
            }
        except Exception:
            return None

    def _format_temp(self, celsius: float) -> str:
        fahrenheit = (celsius * 9 / 5) + 32
        return f"{celsius:.1f} C ({fahrenheit:.1f} F)"

    def _temperature_band(self, celsius: float) -> str:
        if celsius < 10:
            return "chilly"
        if celsius < 17:
            return "cool"
        if celsius < 24:
            return "mild"
        if celsius < 30:
            return "warm"
        return "hot"

    def _rain_phrase(self, rain_mm: float) -> str:
        if rain_mm < 0.5:
            return "usually dry conditions"
        if rain_mm < 2.0:
            return "light showers are possible"
        if rain_mm < 5.0:
            return "intermittent rain is fairly likely"
        return "wet weather is likely, with frequent showers"

    def _packing_tip(self, min_c: float, max_c: float, rain_mm: float) -> str:
        layers = "pack light layers with a breathable top and a medium jacket"
        if max_c >= 24:
            layers = "pack breathable clothes for daytime heat and one light evening layer"
        elif max_c < 14:
            layers = "pack warm layers and a proper jacket, especially for mornings"

        rain = "an umbrella is optional"
        if rain_mm >= 0.5:
            rain = "carry a compact umbrella or a light rain shell"

        return f"{layers}; {rain}."

    def _comfort_phrase(self, temp_c: float, humidity_pct: float) -> str:
        band = self._temperature_band(temp_c)
        if humidity_pct >= 80 and temp_c >= 24:
            return f"{band} and humid"
        if humidity_pct <= 35:
            return f"{band} and fairly dry"
        return f"{band} and comfortable"

    async def _fetch_hotels(self, city: str, check_in: date, check_out: date, adults: int) -> list[dict[str, Any]]:
        if not self.rapidapi_key:
            return []

        headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": "tripadvisor16.p.rapidapi.com",
        }

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                loc_resp = await client.get(
                    "https://tripadvisor16.p.rapidapi.com/api/v1/hotels/searchLocation",
                    headers=headers,
                    params={"query": city},
                )
                loc_data = loc_resp.json().get("data", [])
                if not loc_data:
                    return []

                geo_id = str(loc_data[0].get("geoId"))
                hotel_resp = await client.get(
                    "https://tripadvisor16.p.rapidapi.com/api/v1/hotels/searchHotels",
                    headers=headers,
                    params={
                        "geoId": geo_id,
                        "checkIn": check_in.isoformat(),
                        "checkOut": check_out.isoformat(),
                        "adults": adults,
                        "pageNumber": 1,
                        "currencyCode": "USD",
                    },
                )
                return hotel_resp.json().get("data", {}).get("data", [])[:8]
        except Exception:
            return []

    async def _fetch_restaurants(self, city: str) -> list[dict[str, Any]]:
        if not self.rapidapi_key:
            return []

        headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": "tripadvisor16.p.rapidapi.com",
        }

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                loc_resp = await client.get(
                    "https://tripadvisor16.p.rapidapi.com/api/v1/restaurant/searchLocation",
                    headers=headers,
                    params={"query": city},
                )
                locations = loc_resp.json().get("data", [])
                city_locations = [x for x in locations if x.get("placeType") == "CITY"]
                if not city_locations:
                    return []

                location_id = str(city_locations[0].get("locationId"))
                rest_resp = await client.get(
                    "https://tripadvisor16.p.rapidapi.com/api/v1/restaurant/searchRestaurants",
                    headers=headers,
                    params={"locationId": location_id},
                )
                return rest_resp.json().get("data", {}).get("data", [])[:8]
        except Exception:
            return []

    async def _fetch_attractions(self, city: str) -> list[dict[str, Any]]:
        if not self.foursquare_key:
            return []

        headers = {
            "Authorization": f"Bearer {self.foursquare_key}",
            "Accept": "application/json",
            "X-Places-Api-Version": "2025-06-17",
        }
        queries = [
            "historic monument landmark",
            "museum art gallery",
            "cathedral basilica",
            "palace castle tower",
        ]
        seen: set[str] = set()
        places: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=25) as client:
                for query in queries:
                    resp = await client.get(
                        "https://places-api.foursquare.com/places/search",
                        headers=headers,
                        params={
                            "query": query,
                            "near": city,
                            "limit": 6,
                            "sort": "POPULARITY",
                            "fields": "fsq_place_id,name,categories,location",
                        },
                    )
                    for place in resp.json().get("results", []):
                        pid = place.get("fsq_place_id")
                        if pid and pid not in seen:
                            seen.add(pid)
                            places.append(place)
                    if len(places) >= 10:
                        break
            return places[:10]
        except Exception:
            return []

    async def _currency_brief(self, base: str, target: str, amount: float) -> str:
        base = base.upper()
        target = target.upper()
        url = f"https://api.exchangerate-api.com/v4/latest/{base}"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.get(url)
                data = res.json()
            rate = data.get("rates", {}).get(target)
            if not rate:
                return f"Currency conversion unavailable for {base}->{target}."
            converted = amount * float(rate)
            return f"{amount:.0f} {base} is approximately {converted:.2f} {target} at rate 1 {base} = {rate:.4f} {target}."
        except Exception:
            return f"Currency conversion unavailable for {base}->{target}."

    def _hotel_brief(self, city: str, hotels: list[dict[str, Any]]) -> str:
        if not hotels:
            return f"Hotel APIs returned no direct inventory for {city} in the selected range."

        lines = [f"Hotel intelligence from live search in {city}:"]
        for idx, hotel in enumerate(hotels[:5], start=1):
            name = hotel.get("title", "Unknown")
            price = hotel.get("priceForDisplay", "N/A")
            rating = hotel.get("bubbleRating", {}).get("rating", "N/A")
            reviews = hotel.get("bubbleRating", {}).get("count", "N/A")
            primary_info = hotel.get("primaryInfo") or ""
            price_details = hotel.get("priceDetails") or ""
            lines.append(
                f"{idx}. {name} | Rating {rating}/5 ({reviews} reviews) | Price {price}"
                + (f" | {primary_info}" if primary_info else "")
                + (f" | {price_details}" if price_details else "")
            )

        lines.append("Neighborhood strategy: prioritize central districts with short commute to core attractions.")
        return "\n".join(lines)

    def _restaurant_brief(self, city: str, restaurants: list[dict[str, Any]]) -> str:
        if not restaurants:
            return f"Restaurant APIs returned no live rows for {city}."

        lines = [f"Restaurant intelligence from live search in {city}:"]
        for idx, item in enumerate(restaurants[:6], start=1):
            name = item.get("name", "Unknown")
            rating = item.get("averageRating", "N/A")
            cuisine = ", ".join(item.get("establishmentTypeAndCuisineTags", [])[:3]) or "N/A"
            price = item.get("priceTag", "N/A")
            lines.append(f"{idx}. {name} | Rating {rating}/5 | Cuisine {cuisine} | Price {price}")
        return "\n".join(lines)

    def _attraction_brief(self, city: str, attractions: list[dict[str, Any]]) -> str:
        if not attractions:
            return f"Attraction APIs returned no live rows for {city}."

        lines = [f"Attraction intelligence from live search in {city}:"]
        for idx, place in enumerate(attractions[:8], start=1):
            name = place.get("name", "Unknown")
            category = (place.get("categories", [{}])[0].get("name", "Attraction") if place.get("categories") else "Attraction")
            addr = place.get("location", {}).get("formatted_address", "")
            lines.append(f"{idx}. {name} | {category}" + (f" | {addr}" if addr else ""))
        return "\n".join(lines)

    def _itinerary(
        self,
        req: PlanRequest,
        weather: str,
        hotels: str,
        restaurants: str,
        attractions: str,
        budget_optimizer: str,
    ) -> str:
        return (
            f"4-day itinerary for {req.city} ({req.check_in} to {req.check_out}), style={req.style}, adults={req.adults}.\n"
            "Day 1 Morning: city-core orientation and first landmark cluster.\n"
            "Day 1 Afternoon: museum/culture block and cafe recovery stop.\n"
            "Day 1 Evening: signature dining based on top-rated live restaurant rows.\n"
            "Day 2 Morning: high-demand attractions first (prebooked entries).\n"
            "Day 2 Afternoon: neighborhood exploration with transit-aware pacing.\n"
            "Day 2 Evening: scenic promenade plus local culinary focus.\n"
            "Day 3 Morning: secondary landmark cluster and photo windows.\n"
            "Day 3 Afternoon: shopping/local experiences depending on style preference.\n"
            "Day 3 Evening: cultural show/night district option.\n"
            "Day 4: flexible reserve day for weather shifts, spillover tickets, and premium upgrades.\n\n"
            f"Weather input used:\n{weather}\n\n"
            f"Hotel input used:\n{hotels}\n\n"
            f"Restaurant input used:\n{restaurants}\n\n"
            f"Attraction input used:\n{attractions}\n\n"
            f"Budget tier input used:\n{budget_optimizer}"
        )

    def _budget_optimizer(
        self,
        req: PlanRequest,
        hotels: list[dict[str, Any]],
        restaurants: list[dict[str, Any]],
        attractions: list[dict[str, Any]],
    ) -> str:
        low = req.budget_amount * 0.35
        medium = req.budget_amount * 0.6
        luxury = req.budget_amount * 1.0

        return (
            "Budget optimizer with all tiers (auto-generated, no follow-up needed):\n\n"
            f"LOW PLAN (~{low:.0f} {req.budget_currency}):\n"
            "- Stay: value hotels with strong location-to-price ratio from live search.\n"
            "- Food: 1 signature meal + 2 casual local meals per day.\n"
            "- Mobility: public transit pass and clustered attraction routing.\n"
            "- Experiences: prioritize top 2-3 paid attractions, fill rest with low-cost city walks.\n\n"
            f"MEDIUM PLAN (~{medium:.0f} {req.budget_currency}):\n"
            "- Stay: boutique/upscale mid-tier properties from live inventory.\n"
            "- Food: 1 premium dinner daily + curated cafe/lunch circuit.\n"
            "- Mobility: mixed transit + selective ride-hailing for time-critical slots.\n"
            "- Experiences: add skip-the-line entries and one premium guided activity.\n\n"
            f"LUXURY PLAN (~{luxury:.0f} {req.budget_currency}):\n"
            "- Stay: flagship luxury properties with concierge-grade amenities.\n"
            "- Food: top-tier tasting-led dining and reservation-priority spots.\n"
            "- Mobility: private transfers for airport and evening returns.\n"
            "- Experiences: private/limited-access experiences and premium time optimization.\n\n"
            f"Live inputs counted: hotels={len(hotels)}, restaurants={len(restaurants)}, attractions={len(attractions)}"
        )

    def _compose_final(
        self,
        city: str,
        weather: str,
        hotels: str,
        restaurants: str,
        attractions: str,
        currency: str,
        itinerary: str,
        budget_optimizer: str,
    ) -> str:
        city_safe = escape(city)
        return f"""
<article class=\"result-shell\">
    <header class=\"result-hero\">
        <p class=\"result-kicker\">Concierge Plan</p>
        <h2>{city_safe}</h2>
        <div class=\"chip-row\">
            <span class=\"chip\">Live APIs</span>
            <span class=\"chip\">Weather + Seasonal Estimate</span>
            <span class=\"chip\">Low / Medium / Luxury</span>
        </div>
    </header>

    <section class=\"result-card\">
        <h3>Weather Intelligence</h3>
        {self._to_html_paragraphs(weather)}
    </section>

    <section class=\"result-card\">
        <h3>Hotel Intelligence</h3>
        {self._to_html_list(hotels)}
    </section>

    <section class=\"result-card two-col\">
        <div>
            <h3>Restaurant Intelligence</h3>
            {self._to_html_list(restaurants)}
        </div>
        <div>
            <h3>Attraction Intelligence</h3>
            {self._to_html_list(attractions)}
        </div>
    </section>

    <section class=\"result-card\">
        <h3>Currency Intelligence</h3>
        {self._to_html_paragraphs(currency)}
    </section>

    <section class=\"result-card\">
        <h3>Budget Optimizer</h3>
        {self._to_html_list(budget_optimizer)}
    </section>

    <section class=\"result-card\">
        <h3>Signature Itinerary</h3>
        {self._to_html_list(itinerary)}
    </section>
</article>
""".strip()

    def _to_html_paragraphs(self, text: str) -> str:
        lines = [escape(line.strip()) for line in text.splitlines() if line.strip()]
        if not lines:
            return "<p>No data available.</p>"
        return "".join(f"<p>{line}</p>" for line in lines)

    def _to_html_list(self, text: str) -> str:
        lines = [escape(line.strip()) for line in text.splitlines() if line.strip()]
        if not lines:
            return "<p>No data available.</p>"
        items = "".join(f"<li>{line}</li>" for line in lines)
        return f"<ul class=\"result-list\">{items}</ul>"
