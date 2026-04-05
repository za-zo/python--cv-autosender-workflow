"""HTML fragments for workflow notification emails (progressive context)."""


def html_escape(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def mask_api_key_value(api_key_str):
    """Show only last 4 characters of a secret API key in notifications."""
    s = str(api_key_str) if api_key_str else ""
    if len(s) <= 4:
        return "****"
    return f"…{s[-4:]}"


def _fmt_val(v):
    if v is None:
        return "—"
    return html_escape(str(v))


def _dl_row(label, value):
    return f"<tr><td style=\"padding:4px 12px 4px 0;vertical-align:top;color:#555;\"><strong>{html_escape(label)}</strong></td><td style=\"padding:4px 0;\">{_fmt_val(value)}</td></tr>"


def _section(title, rows_html):
    return (
        f"<h3 style=\"margin:16px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px;\">{html_escape(title)}</h3>"
        f"<table style=\"border-collapse:collapse;font-size:13px;\">{rows_html}</table>"
    )


def _job_section(job):
    rows = "".join(
        [
            _dl_row("_id", job.get("_id")),
            _dl_row("companyId", job.get("companyId")),
            _dl_row("targetPosition", job.get("targetPosition")),
            _dl_row("jobDescription", job.get("jobDescription")),
            _dl_row("cv_language", job.get("cv_language")),
            _dl_row("experienceLevel", job.get("experienceLevel")),
            _dl_row("contractType", job.get("contractType")),
            _dl_row("notes", job.get("notes")),
            _dl_row("createdAt", job.get("createdAt")),
        ]
    )
    return _section("Job", rows)


def _company_section(company):
    rows = "".join(
        [
            _dl_row("_id", company.get("_id")),
            _dl_row("name", company.get("name")),
            _dl_row("website", company.get("website")),
            _dl_row("email", company.get("email")),
            _dl_row("sector", company.get("sector")),
            _dl_row("location", company.get("location")),
            _dl_row("createdAt", company.get("createdAt")),
        ]
    )
    return _section("Company", rows)


def _provider_section(title, provider):
    rows = "".join(
        [
            _dl_row("_id", provider.get("_id")),
            _dl_row("name", provider.get("name")),
            _dl_row("model_name", provider.get("model_name")),
            _dl_row("createdAt", provider.get("createdAt")),
        ]
    )
    return _section(title, rows)


def _api_key_section(title, doc):
    api_key_display = mask_api_key_value(doc.get("apiKey")) if doc else "—"
    rows = "".join(
        [
            _dl_row("_id", doc.get("_id")),
            _dl_row("name", doc.get("name")),
            _dl_row("apiKey", api_key_display),
            _dl_row("usageCount", doc.get("usageCount")),
            _dl_row("successUsageCount", doc.get("successUsageCount")),
            _dl_row("failedUsageCount", doc.get("failedUsageCount")),
            _dl_row("createdAt", doc.get("createdAt")),
        ]
    )
    return _section(title, rows)


def _email_section(email_config):
    rows = "".join(
        [
            _dl_row("_id", email_config.get("_id")),
            _dl_row("smtp_email", email_config.get("smtp_email")),
            _dl_row("usage_count", email_config.get("usage_count")),
            _dl_row("successUsageCount", email_config.get("successUsageCount")),
            _dl_row("failedUsageCount", email_config.get("failedUsageCount")),
            _dl_row("createdAt", email_config.get("createdAt")),
        ]
    )
    return _section("Email (SMTP account)", rows)


def build_context_html(
    job,
    company=None,
    cv_provider=None,
    msg_provider=None,
    cv_api_key=None,
    msg_api_key=None,
    email_config=None,
):
    """Build progressive HTML: only include sections for non-None entities."""
    parts = [_job_section(job)]
    if company is not None:
        parts.append(_company_section(company))
    if email_config is not None:
        parts.append(_email_section(email_config))
    if cv_provider is not None:
        parts.append(_provider_section("CV provider", cv_provider))
    if msg_provider is not None:
        parts.append(_provider_section("Message provider", msg_provider))
    if cv_api_key is not None:
        parts.append(_api_key_section("AI API key (CV generation)", cv_api_key))
    if msg_api_key is not None:
        parts.append(_api_key_section("AI API key (message generation)", msg_api_key))
    return "\n".join(parts)


def format_updates_html(updates_made):
    if not updates_made:
        return ""
    items = "".join(f"<li>{html_escape(u)}</li>" for u in updates_made)
    return (
        "<h3 style=\"margin:16px 0 8px;\">Updates applied</h3>"
        f"<ul style=\"margin:0;padding-left:20px;\">{items}</ul>"
    )


def format_smtp_line(smtp_email):
    if not smtp_email:
        return ""
    return f"<p><strong>SMTP sender used:</strong> {_fmt_val(smtp_email)}</p>"
