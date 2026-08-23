import json

def lambda_handler(event, context):
    city = event.get("city", "Unknown")

    attractions_data = {
        "London": {
            "city": "London",
            "attractions": [
                {"name": "British Museum", "type": "Indoor", "family_friendly": True, "description": "World-renowned museum with ancient Egyptian mummies, Greek sculptures, and the Rosetta Stone"},
                {"name": "Tower of London", "type": "Outdoor", "family_friendly": True, "description": "Historic castle housing the Crown Jewels and Beefeater tours"},
                {"name": "Natural History Museum", "type": "Indoor", "family_friendly": True, "description": "Dinosaur skeletons, gemstones, and interactive Earth galleries"},
                {"name": "London Eye", "type": "Outdoor", "family_friendly": True, "description": "Giant observation wheel with panoramic views of the city skyline"},
                {"name": "Science Museum", "type": "Indoor", "family_friendly": True, "description": "Interactive exhibitions on space, technology, and medicine"}
            ]
        },
        "Paris": {
            "city": "Paris",
            "attractions": [
                {"name": "Louvre Museum", "type": "Indoor", "family_friendly": True, "description": "Home to the Mona Lisa and thousands of works of art"},
                {"name": "Eiffel Tower", "type": "Outdoor", "family_friendly": True, "description": "Iconic iron lattice tower with observation decks"},
                {"name": "Musée d'Orsay", "type": "Indoor", "family_friendly": False, "description": "Impressionist and Post-Impressionist masterpieces in a former railway station"},
                {"name": "Jardin des Tuileries", "type": "Outdoor", "family_friendly": True, "description": "Historic garden between the Louvre and Place de la Concorde"},
                {"name": "Cité des Sciences et de l'Industrie", "type": "Indoor", "family_friendly": True, "description": "Europe's largest science museum with interactive exhibits"}
            ]
        },
        "New York": {
            "city": "New York",
            "attractions": [
                {"name": "American Museum of Natural History", "type": "Indoor", "family_friendly": True, "description": "Dinosaur halls, planetarium, and the famous blue whale model"},
                {"name": "Central Park", "type": "Outdoor", "family_friendly": True, "description": "843-acre urban park with playgrounds, lakes, and walking trails"},
                {"name": "Statue of Liberty", "type": "Outdoor", "family_friendly": True, "description": "Iconic copper statue on Liberty Island with crown access tours"},
                {"name": "Metropolitan Museum of Art", "type": "Indoor", "family_friendly": True, "description": "Encyclopedic art collection spanning 5,000 years"},
                {"name": "Intrepid Sea, Air & Space Museum", "type": "Indoor", "family_friendly": True, "description": "Aircraft carrier museum with submarine, Concorde, and space shuttle"}
            ]
        }
    }

    result = attractions_data.get(city, {
        "city": city,
        "attractions": []
    })

    return result
