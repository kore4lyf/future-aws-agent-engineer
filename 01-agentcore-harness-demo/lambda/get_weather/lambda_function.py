import json

def lambda_handler(event, context):
    city = event.get("city", "Unknown")
    date = event.get("date", "Unknown")

    weather_data = {
        "London": {
            "condition": "Light rain in the morning, clearing to partly cloudy by afternoon",
            "temperature_high": "18C",
            "temperature_low": "12C",
            "humidity": "75%",
            "wind": "15 km/h from the west"
        },
        "Paris": {
            "condition": "Sunny with clear skies throughout the day",
            "temperature_high": "24C",
            "temperature_low": "15C",
            "humidity": "45%",
            "wind": "8 km/h from the southeast"
        },
        "New York": {
            "condition": "Overcast with occasional thunderstorms in the afternoon",
            "temperature_high": "28C",
            "temperature_low": "20C",
            "humidity": "80%",
            "wind": "20 km/h from the southwest"
        }
    }

    result = weather_data.get(city, {
        "condition": "Weather data not available for this city",
        "temperature_high": "N/A",
        "temperature_low": "N/A",
        "humidity": "N/A",
        "wind": "N/A"
    })

    result["city"] = city
    result["date"] = date

    return result
