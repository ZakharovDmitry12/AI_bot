"""Локальные инструменты, которыми может пользоваться LLM.

Важно: модель сама не выполняет Python-код. Она только просит вызвать инструмент
через tool_calls, а наш код уже вызывает нужную функцию и возвращает результат
модели отдельным сообщением role="tool".
"""

import aiohttp


WEATHER_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Получить текущую погоду в городе. Используй этот инструмент, "
            "когда пользователь спрашивает о погоде, температуре, ветре или осадках."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Название города на любом языке, например: Москва, Berlin, Tokyo.",
                }
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    },
}

AVAILABLE_TOOLS = [WEATHER_TOOL_SCHEMA]


WEATHER_CODE_DESCRIPTIONS = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь и туман",
    51: "слабая морось",
    53: "умеренная морось",
    55: "сильная морось",
    61: "слабый дождь",
    63: "умеренный дождь",
    65: "сильный дождь",
    71: "слабый снег",
    73: "умеренный снег",
    75: "сильный снег",
    80: "слабый ливень",
    81: "умеренный ливень",
    82: "сильный ливень",
    95: "гроза",
    96: "гроза с небольшим градом",
    99: "гроза с сильным градом",
}


async def get_weather(city: str) -> str:
    """Возвращает текущую погоду по названию города.

    Используется Open-Meteo: сначала превращаем название города в координаты,
    затем запрашиваем текущие погодные параметры по этим координатам.
    """
    normalized_city = city.strip()

    if len(normalized_city) < 2:
        return "Не удалось получить погоду: название города слишком короткое."

    timeout = aiohttp.ClientTimeout(total=12)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        location = await _find_city(session, normalized_city)

        if not location:
            return f"Не удалось найти город: {normalized_city}."

        weather = await _fetch_current_weather(session, location["latitude"], location["longitude"])

    current = weather.get("current", {})
    units = weather.get("current_units", {})
    weather_code = current.get("weather_code")
    description = WEATHER_CODE_DESCRIPTIONS.get(weather_code, f"код погоды {weather_code}")
    place_name = _format_place_name(location)

    return (
        f"Погода для {place_name}: {description}. "
        f"Температура {current.get('temperature_2m')} {units.get('temperature_2m', '°C')}, "
        f"ощущается как {current.get('apparent_temperature')} {units.get('apparent_temperature', '°C')}. "
        f"Влажность {current.get('relative_humidity_2m')} {units.get('relative_humidity_2m', '%')}. "
        f"Ветер {current.get('wind_speed_10m')} {units.get('wind_speed_10m', 'км/ч')}, "
        f"направление {current.get('wind_direction_10m')} {units.get('wind_direction_10m', '°')}. "
        f"Осадки {current.get('precipitation')} {units.get('precipitation', 'мм')}. "
        f"Время измерения: {current.get('time')}."
    )


async def execute_tool(tool_name: str, arguments: dict) -> str:
    """Вызывает локальный инструмент по имени.

    Такая маленькая диспетчеризация удобна: когда появятся новые инструменты,
    их можно будет добавить сюда, не переписывая LLM-цикл.
    """
    if tool_name == "get_weather":
        city = arguments.get("city")

        if not isinstance(city, str):
            return "Ошибка инструмента get_weather: аргумент city должен быть строкой."

        return await get_weather(city)

    return f"Неизвестный инструмент: {tool_name}."


async def _find_city(session: aiohttp.ClientSession, city: str) -> dict | None:
    """Ищет город через Open-Meteo Geocoding API."""
    async with session.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city,
            "count": 1,
            "language": "ru",
            "format": "json",
        },
    ) as response:
        response.raise_for_status()
        data = await response.json()

    results = data.get("results") or []

    if not results:
        return None

    return results[0]


async def _fetch_current_weather(
    session: aiohttp.ClientSession,
    latitude: float,
    longitude: float,
) -> dict:
    """Запрашивает текущую погоду по координатам через Open-Meteo Forecast API."""
    async with session.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "cloud_cover",
                    "wind_speed_10m",
                    "wind_direction_10m",
                ]
            ),
            "timezone": "auto",
            "wind_speed_unit": "kmh",
        },
    ) as response:
        response.raise_for_status()
        return await response.json()


def _format_place_name(location: dict) -> str:
    """Собирает человекочитаемое название найденной локации."""
    parts = [
        location.get("name"),
        location.get("admin1"),
        location.get("country"),
    ]
    return ", ".join(part for part in parts if part)
