import requests


def call(api_key, system_msg, user_msg, model_name="command-a-03-2025"):
    resp = requests.post(
        "https://api.cohere.com/v2/chat",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 4096,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
