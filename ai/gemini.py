import requests

MODEL_NAME = "gemini-2.5-flash"

def call(api_key, system_msg, user_msg):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={api_key}"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "systemInstruction": {"parts": [{"text": system_msg}]},
            "generationConfig": {"responseMimeType": "application/json"},
            "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
