from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from systems.axon.mesh.registry import DriverInterface

log = logging.getLogger("OpenMeteo")


# ---------------------------
# Utility validation schemas
# ---------------------------


class GeoResult(BaseModel):
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    timezone: str | None = None


class CommonArgs(BaseModel):
    # Accept either a human location string OR explicit lat/lon (lat/lon take precedence if given)
    location: str | None = Field(None, description="City/town name only, e.g. 'Sunshine Coast'")
    latitude: float | None = Field(None, description="WGS84 latitude")
    longitude: float | None = Field(None, description="WGS84 longitude")

    # Units + formatting (Open-Meteo native defaults preserved if None)
    temperature_unit: Literal["celsius", "fahrenheit"] | None = None
    wind_speed_unit: Literal["kmh", "ms", "mph", "kn"] | None = None
    precipitation_unit: Literal["mm", "inch"] | None = None
    timeformat: Literal["iso8601", "unixtime"] | None = None
    timezone: str | None = Field("auto", description="IANA TZ or 'auto'")

    include_current: bool = Field(True, description="Include current conditions block")


class ProbeArgs(CommonArgs):
    # /v1/forecast (global best-model blend)
    forecast_days: int = Field(3, ge=1, le=16)
    hourly: list[str] | None = None
    daily: list[str] | None = None


class HourlyArgs(CommonArgs):
    # Specialized “hourly only” fetch
    forecast_hours: int | None = Field(None, ge=1, le=16 * 24)  # up to 16 days worth
    hourly: list[str] = Field(
        default_factory=lambda: [
            "temperature_2m",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "cloud_cover",
        ]
    )


class DailyArgs(CommonArgs):
    # Specialized “daily only” fetch
    forecast_days: int = Field(7, ge=1, le=16)
    daily: list[str] = Field(
        default_factory=lambda: [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "uv_index_max",
            "weather_code",
            "sunrise",
            "sunset",
        ]
    )


class RadiationArgs(CommonArgs):
    # Radiation variables live under the same /v1/forecast; we expose a curated set
    forecast_days: int = Field(3, ge=1, le=16)
    hourly: list[str] = Field(
        default_factory=lambda: [
            "shortwave_radiation",
            "direct_radiation",
            "direct_normal_irradiance",
            "diffuse_radiation",
            "global_tilted_irradiance",
        ]
    )
    # Optional geometry for tilted-plane calc (Open-Meteo supports tilt/azimuth=nan for trackers)
    tilt: float | None = None
    azimuth: float | None = None


# ---------------------------
# Driver
# ---------------------------


class _Spec(BaseModel):
    driver_name: str
    version: str
    supported_actions: list[str] = ["probe"]
    summary: str = "Realtime weather and forecast from Open-Meteo."


class OpenMeteo(DriverInterface):
    """
    Endpoints exposed:
      - open_meteo.probe               -> /v1/forecast  (global, blended 'best models')
      - open_meteo.hourly_forecast     -> /v1/forecast  (hourly-focused)
      - open_meteo.daily_forecast      -> /v1/forecast  (daily-focused)
      - open_meteo.radiation_forecast  -> /v1/forecast  (solar radiation suite)
    """

    NAME: str = "open_meteo"
    VERSION: str = "2.0.0"

    # Canonical action names (must match your tool catalog endpoint names)
    ACTION_PROBE: Literal["probe"] = "probe"
    ACTION_HOURLY: Literal["hourly_forecast"] = "hourly_forecast"
    ACTION_DAILY: Literal["daily_forecast"] = "daily_forecast"
    ACTION_RAD: Literal["radiation_forecast"] = "radiation_forecast"

    def __init__(self) -> None:
        self.geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.api_url = "https://api.open-meteo.com/v1/forecast"
        self._timeout = aiohttp.ClientTimeout(total=20)

    # ---- Driver metadata
    def describe(self) -> _Spec:
        return _Spec(
            driver_name=self.NAME,
            version=self.VERSION,
            supported_actions=[
                self.ACTION_PROBE,
                self.ACTION_HOURLY,
                self.ACTION_DAILY,
                self.ACTION_RAD,
            ],
            summary="Realtime weather and forecast from Open-Meteo.",
        )

    # ---- Shared helpers
    async def _geocode(self, s: aiohttp.ClientSession, name: str) -> GeoResult:
        resp = await s.get(self.geo_url, params={"name": name, "count": 1, "language": "en"})
        resp.raise_for_status()
        data = await resp.json()
        if not data.get("results"):
            raise ValueError(f"Could not geocode location: {name}")
        first = data["results"][0]
        return GeoResult(
            name=first.get("name"),
            latitude=first["latitude"],
            longitude=first["longitude"],
            country=first.get("country"),
            timezone=first.get("timezone"),
        )

    async def _resolve_coords(
        self, s: aiohttp.ClientSession, args: CommonArgs
    ) -> tuple[GeoResult, float, float]:
        if args.latitude is not None and args.longitude is not None:
            # "Synthetic" GeoResult when lat/lon is provided
            pseudo = GeoResult(
                name=args.location or "coordinates",
                latitude=args.latitude,
                longitude=args.longitude,
                country=None,
                timezone=args.timezone if (args.timezone and args.timezone != "auto") else None,
            )
            return pseudo, args.latitude, args.longitude
        if not args.location:
            raise ValueError("Provide either 'location' or both 'latitude' and 'longitude'.")
        geo = await self._geocode(s, args.location)
        return geo, geo.latitude, geo.longitude

    def _apply_common_query_params(self, q: dict[str, Any], args: CommonArgs) -> None:
        # Timezone defaults to 'auto' (Open-Meteo will localize to coords)
        q["timezone"] = args.timezone or "auto"
        if args.temperature_unit:
            q["temperature_unit"] = args.temperature_unit
        if args.wind_speed_unit:
            q["wind_speed_unit"] = args.wind_speed_unit
        if args.precipitation_unit:
            q["precipitation_unit"] = args.precipitation_unit
        if args.timeformat:
            q["timeformat"] = args.timeformat
        if args.include_current:
            # "current" can be a CSV list; per docs any hourly variable works here.
            q["current"] = "temperature_2m,weather_code,wind_speed_10m"

    async def _fetch(
        self, s: aiohttp.ClientSession, url: str, query: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await s.get(url, params=query)
        resp.raise_for_status()
        return await resp.json()

    def _shape_response(self, geo: GeoResult, data: dict[str, Any]) -> dict[str, Any]:
        if not (data.get("hourly") or data.get("daily") or data.get("current")):
            return {"status": "error", "message": "Empty payload from Open-Meteo."}
        return {
            "status": "ok",
            "location": {
                "name": geo.name,
                "country": geo.country,
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "timezone": data.get("timezone"),
                "timezone_abbreviation": data.get("timezone_abbreviation"),
                "elevation": data.get("elevation"),
            },
            "current": data.get("current"),
            "hourly": data.get("hourly"),
            "hourly_units": data.get("hourly_units"),
            "daily": data.get("daily"),
            "daily_units": data.get("daily_units"),
            "generationtime_ms": data.get("generationtime_ms"),
            "utc_offset_seconds": data.get("utc_offset_seconds"),
        }

    # ---------------------------
    # Endpoints
    # ---------------------------

    async def probe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Global blended forecast snapshot (/v1/forecast)."""
        try:
            args = ProbeArgs(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        headers = {"User-Agent": f"Axon/{self.VERSION} (+open-meteo-client)"}
        async with aiohttp.ClientSession(timeout=self._timeout, headers=headers) as s:
            try:
                geo, lat, lon = await self._resolve_coords(s, args)
                q: dict[str, Any] = {
                    "latitude": lat,
                    "longitude": lon,
                    "forecast_days": args.forecast_days,
                }
                # Defaults if none provided
                hourly = args.hourly or [
                    "temperature_2m",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                    "cloud_cover",
                ]
                daily = args.daily or [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "uv_index_max",
                    "weather_code",
                    "sunrise",
                    "sunset",
                ]
                q["hourly"] = ",".join(hourly)
                q["daily"] = ",".join(daily)

                self._apply_common_query_params(q, args)
                data = await self._fetch(s, self.api_url, q)
                return self._shape_response(geo, data)
            except Exception as e:
                log.exception("[OpenMeteo.probe] failure")
                return {"status": "error", "message": str(e)}

    async def hourly_forecast(self, params: dict[str, Any]) -> dict[str, Any]:
        """Hourly-focused forecast from /v1/forecast."""
        try:
            args = HourlyArgs(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        headers = {"User-Agent": f"Axon/{self.VERSION} (+open-meteo-client)"}
        async with aiohttp.ClientSession(timeout=self._timeout, headers=headers) as s:
            try:
                geo, lat, lon = await self._resolve_coords(s, args)
                q: dict[str, Any] = {
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": ",".join(args.hourly),
                }
                if args.forecast_hours:
                    # Use forecast_hours to bound hours instead of forecast_days
                    q["forecast_hours"] = args.forecast_hours

                self._apply_common_query_params(q, args)
                data = await self._fetch(s, self.api_url, q)
                # Strip daily if present to keep payload lean
                data["daily"] = None
                data["daily_units"] = None
                return self._shape_response(geo, data)
            except Exception as e:
                log.exception("[OpenMeteo.hourly_forecast] failure")
                return {"status": "error", "message": str(e)}

    async def daily_forecast(self, params: dict[str, Any]) -> dict[str, Any]:
        """Daily-focused forecast from /v1/forecast."""
        try:
            args = DailyArgs(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        headers = {"User-Agent": f"Axon/{self.VERSION} (+open-meteo-client)"}
        async with aiohttp.ClientSession(timeout=self._timeout, headers=headers) as s:
            try:
                geo, lat, lon = await self._resolve_coords(s, args)
                q: dict[str, Any] = {
                    "latitude": lat,
                    "longitude": lon,
                    "daily": ",".join(args.daily),
                    "forecast_days": args.forecast_days,
                }
                self._apply_common_query_params(q, args)
                data = await self._fetch(s, self.api_url, q)
                # Strip hourly if present to keep payload lean
                data["hourly"] = None
                data["hourly_units"] = None
                return self._shape_response(geo, data)
            except Exception as e:
                log.exception("[OpenMeteo.daily_forecast] failure")
                return {"status": "error", "message": str(e)}

    async def radiation_forecast(self, params: dict[str, Any]) -> dict[str, Any]:
        """Solar radiation suite (shortwave, direct, DNi, diffuse, GTI) from /v1/forecast."""
        try:
            args = RadiationArgs(**params)
        except ValidationError as e:
            return {"status": "error", "message": f"Invalid parameters: {e}"}

        headers = {"User-Agent": f"Axon/{self.VERSION} (+open-meteo-client)"}
        async with aiohttp.ClientSession(timeout=self._timeout, headers=headers) as s:
            try:
                geo, lat, lon = await self._resolve_coords(s, args)
                q: dict[str, Any] = {
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": ",".join(args.hourly),
                    "forecast_days": args.forecast_days,
                }
                # Optional geometry for GTI calc
                if args.tilt is not None:
                    q["tilt"] = args.tilt
                if args.azimuth is not None:
                    q["azimuth"] = args.azimuth

                self._apply_common_query_params(q, args)
                data = await self._fetch(s, self.api_url, q)
                # We return hourly only by design here
                data["daily"] = None
                data["daily_units"] = None
                return self._shape_response(geo, data)
            except Exception as e:
                log.exception("[OpenMeteo.radiation_forecast] failure")
                return {"status": "error", "message": str(e)}

    # ---- Driver diagnostics
    def repro_bundle(self) -> dict[str, Any]:
        return {
            "driver_name": self.NAME,
            "version": self.VERSION,
            "geo_url": self.geo_url,
            "api_url": self.api_url,
        }

    async def self_test(self) -> dict[str, Any]:
        try:
            glob = await self.probe({"location": "Sunshine Coast", "forecast_days": 3})
            if glob.get("status") != "ok":
                raise RuntimeError(f"Global check failed: {glob}")

            return {"status": "ok", "message": "Open-Meteo endpoints healthy."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
