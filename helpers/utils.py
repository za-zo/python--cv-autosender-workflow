import config
import time
import html

def mask(val, kind="str"):
    """Mask sensitive values when config.MASK_LOGS is enabled."""
    if not config.MASK_LOGS:
        return val
    s = str(val) if val else ""
    if not s:
        return ""
    if kind == "email":
        return "***@***.***"
    if kind == "secret":
        return "********"
    if kind == "json":
        return "[MASKED]"
    return "***"

def html_escape(s):
    """Escape HTML characters."""
    return html.escape(str(s))

def call_ai_with_retries(provider_module, api_key, system_msg, user_msg, model_name=None):
    """Call AI provider with retry logic."""
    last_error = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return provider_module.call(api_key, system_msg, user_msg, model_name=model_name)
        except Exception as e:
            last_error = e
            if attempt < config.MAX_RETRIES:
                print(f"  -> Retry {attempt}/{config.MAX_RETRIES} failed, waiting {config.RETRY_WAIT_SECONDS}s...")
                time.sleep(config.RETRY_WAIT_SECONDS)
    raise last_error

def smtp_pair(smtp_email, smtp_password):
    """Return a pair of SMTP credentials or fallback to global ones."""
    if smtp_email and smtp_password:
        return smtp_email, smtp_password
    ne, np = config.NOTIFICATION_SMTP_EMAIL, config.NOTIFICATION_SMTP_PASSWORD
    if ne and np:
        return ne, np
    return None, None
