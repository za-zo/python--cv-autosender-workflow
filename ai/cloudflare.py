import requests


def call(api_key, system_msg, user_msg, model_name="@cf/meta/llama-3.3-70b-instruct-fp8-fast"):
    account_id, api_token = api_key.split("|", 1)
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}"

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_token}"},
        json={
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
