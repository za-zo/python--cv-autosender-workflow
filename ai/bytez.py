import requests

def call(api_key, system_msg, user_msg):
    resp = requests.post(
        "https://api.bytez.com/models/v2/openai/o4-mini",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json={
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "params": {},
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
