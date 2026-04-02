import requests

def call(api_key, system_msg, user_msg, model_name="openai/gpt-oss-120b:fastest"):
    # Hugging Face Inference API provides an OpenAI-compatible endpoint at /v1/chat/completions
    url = "https://router.huggingface.co/v1/chat/completions"

    resp = requests.post(
        url,
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
            # # max_tokens: 2048 to allow for detailed CV generation
            # "max_tokens": 2048,
            # "temperature": 0.5,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()
