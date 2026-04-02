import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai import hugging_face
from ai.base import parse_cv_response, parse_message_response
from tests.conftest import get_test_api_key

SYSTEM_MSG = "You are a helpful assistant. Reply with a short JSON object containing a 'summary' key with a one-sentence summary of yourself."
USER_MSG = "Who are you? Reply in JSON format: {\"summary\": \"...\"}"

SYSTEM_MSG_MSG = "You are a cover letter writer. Reply with only raw text, no JSON, no quotes."
USER_MSG_MSG = "Write a 2-sentence cover letter for a developer position at TechCorp."


def test_cv_response():
    provider, api_key = get_test_api_key("hugging face")
    if not api_key:
        print(f"[SKIP] No active hugging face API key found in DB")
        return None

    print(f"[TEST] hugging face CV response — using key: {api_key['name']}")
    try:
        resp = hugging_face.call(api_key["apiKey"], SYSTEM_MSG, USER_MSG, model_name=provider.get("model_name"))
        print(f"[OK] API call succeeded")

        content = parse_cv_response(provider["name"], resp)
        print(f"[OK] Parsed CV response: summary={content.get('summary', 'N/A')[:80]}")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def test_message_response():
    provider, api_key = get_test_api_key("hugging face")
    if not api_key:
        print(f"[SKIP] No active hugging face API key found in DB")
        return None

    print(f"[TEST] hugging face Message response — using key: {api_key['name']}")
    try:
        resp = hugging_face.call(api_key["apiKey"], SYSTEM_MSG_MSG, USER_MSG_MSG, model_name=provider.get("model_name"))
        print(f"[OK] API call succeeded")

        message = parse_message_response(provider["name"], resp)
        print(f"[OK] Parsed message: {message[:100]}...")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  Testing hugging face")
    print(f"{'='*50}")
    r1 = test_cv_response()
    r2 = test_message_response()
    if r1 is None and r2 is None:
        print(f"\n⏭️  hugging face — SKIPPED (no API key)")
    elif r1 is True and r2 is True:
        print(f"\n✅ hugging face — PASSED")
    elif r1 is False or r2 is False:
        print(f"\n❌ hugging face — FAILED")
    else:
        print(f"\n⚠️  hugging face — PARTIAL")
