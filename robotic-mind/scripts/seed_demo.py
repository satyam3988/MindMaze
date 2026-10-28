import os

import httpx


def seed():
    url = os.environ.get("ROBOTIC_MIND_API", "http://localhost:8000")
    with httpx.Client(base_url=url) as client:
        response = client.get("/api/spaces")
        response.raise_for_status()
        existing = next((s for s in response.json() if s["name"] == "Warehouse Alpha"), None)
        if existing:
            return existing
        response = client.post(
            "/api/spaces", json={"name": "Warehouse Alpha", "display_name": "Satyam"}
        )
        response.raise_for_status()
        return response.json()["space"]


if __name__ == "__main__":
    space = seed()
    print(f"{space['name']} | Invite: {space['invite_code']} | Space: {space['id']}")
