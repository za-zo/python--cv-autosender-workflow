import requests

def call(api_key, system_msg, user_msg, model_name="openai/o4-mini"):
    resp = requests.post(
        f"https://api.bytez.com/models/v2/{model_name}",
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
