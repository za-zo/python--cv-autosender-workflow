import requests

MODEL_NAME = "llama3.1-8b"

def call(api_key, system_msg, user_msg):
    resp = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
