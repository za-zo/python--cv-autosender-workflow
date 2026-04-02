import requests

def call(api_key, system_msg, user_msg):
    resp = requests.post(
        "https://api.cerebras.ai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": "llama3.1-8b",
            # "model": "gpt-oss-120b",
            # "model": "qwen-3-235b-a22b-instruct-2507",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
