import requests

MODEL_NAME = "gpt-4o-mini"

def call(api_key, system_msg, user_msg):
    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": MODEL_NAME,
            "input": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
