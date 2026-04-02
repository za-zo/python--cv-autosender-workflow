import requests

def call(api_key, system_msg, user_msg, model_name="llama3.1-8b"):
    resp = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
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
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
