"""Run all provider tests and print a summary."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests import test_bytez, test_groq, test_gemini, test_openai, test_openrouter, test_zai, test_hugging_face, test_cerebras

providers = [
    ("Bytez", test_bytez),
    ("Groq", test_groq),
    ("Gemini", test_gemini),
    ("OpenAI", test_openai),
    ("OpenRouter", test_openrouter),
    ("Z.ai", test_zai),
    ("Hugging Face", test_hugging_face),
    ("Cerebras", test_cerebras),
]

results = {}
for name, module in providers:
    print(f"\n{'='*50}")
    print(f"  Testing {name}")
    print(f"{'='*50}")
    r1 = module.test_cv_response()
    r2 = module.test_message_response()
    if r1 is None and r2 is None:
        results[name] = "⏭️  SKIPPED (no key)"
    elif r1 is True and r2 is True:
        results[name] = "✅ PASSED"
    elif r1 is False or r2 is False:
        results[name] = "❌ FAILED"
    else:
        results[name] = "⚠️  PARTIAL"

print(f"\n{'='*50}")
print(f"  SUMMARY")
print(f"{'='*50}")
for name, status in results.items():
    print(f"  {name:15s} {status}")
