import requests

def call(api_key, system_msg, user_msg, model_name="Meta-Llama-3.3-70B-Instruct"):
    resp = requests.post(
        "https://api.sambanova.ai/v1/chat/completions",
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
            # "temperature": 0.5,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
