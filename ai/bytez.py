import requests

MODEL_NAME = "openai/o4-mini"

def call(api_key, system_msg, user_msg):
    resp = requests.post(
        f"https://api.bytez.com/models/v2/{MODEL_NAME}",
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
