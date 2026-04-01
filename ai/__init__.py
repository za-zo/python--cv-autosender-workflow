from ai import bytez, groq, gemini, openai, openrouter, zai

PROVIDERS = {
    "bytez": bytez,
    "groq": groq,
    "gemini": gemini,
    "openai": openai,
    "openrouter": openrouter,
    "z.ai": zai,
}

def get_provider_module(provider_name):
    """Get the provider module by matching name (case-insensitive)."""
    name_lower = provider_name.lower()
    for key, module in PROVIDERS.items():
        if key in name_lower:
            return module
    raise ValueError(f"Unknown AI provider: {provider_name}")
