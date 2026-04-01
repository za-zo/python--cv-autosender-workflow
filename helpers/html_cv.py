import html as _html


def _esc(s):
    """Escape HTML entities."""
    return _html.escape(s or "")


def _section(title, content):
    """Render a section if content exists."""
    if not content:
        return ""
    return f'<div class="section"><div class="section-title">{title}</div>{content}</div>'


def generate_html_cv(cv, profile, job):
    """Generate a styled HTML CV from parsed CV JSON data."""
    language = (job.get("cv_language") or "").lower()
    is_arabic = language in ("arabe", "arabic", "ar")
    direction = "rtl" if is_arabic else "ltr"
    lang = "ar" if is_arabic else "fr"

    font_family = (
        "'Noto Sans Arabic',Arial,sans-serif"
        if is_arabic
        else "'Segoe UI',Arial,sans-serif"
    )

    # Skills HTML
    skills_html = ""
    if cv.get("skills"):
        spans = "".join(f'<span class="skill">{_esc(s)}</span>' for s in cv["skills"])
        skills_html = f'<div class="skills">{spans}</div>'

    # Languages HTML
    langs_html = ""
    if cv.get("languages"):
        spans = "".join(
            f'<span class="skill lang">{_esc(l)}</span>' for l in cv["languages"]
        )
        langs_html = f'<div class="skills">{spans}</div>'

    # Experiences HTML
    exp_html = ""
    if cv.get("experiences"):
        items = []
        for e in cv["experiences"]:
            date_str = f'{_esc(e.get("startDate", ""))} — {_esc(e.get("endDate") or "Présent")}'
            desc = (
                f'<div class="item-desc">{_esc(e.get("description"))}</div>'
                if e.get("description")
                else ""
            )
            items.append(
                f'<div class="item"><div class="item-header">'
                f"<div><div class=\"item-title\">{_esc(e.get('title'))}</div>"
                f"<div class=\"item-sub\">{_esc(e.get('company'))}</div></div>"
                f'<div class="item-date">{date_str}</div></div>{desc}</div>'
            )
        exp_html = "".join(items)

    # Projects HTML
    proj_html = ""
    if cv.get("projects"):
        items = []
        for p in cv["projects"]:
            link_html = (
                f' <a href="{_esc(p.get("link"))}" class="link">{_esc(p.get("link"))}</a>'
                if p.get("link")
                else ""
            )
            tech_html = ""
            if p.get("technologies"):
                tech_spans = " ".join(
                    f'<span class="tech">{_esc(t)}</span>'
                    for t in p["technologies"]
                )
                tech_html = f'<div class="item-sub">{tech_spans}</div>'
            desc = (
                f'<div class="item-desc">{_esc(p.get("description"))}</div>'
                if p.get("description")
                else ""
            )
            items.append(
                f'<div class="item"><div class="item-header">'
                f"<div><div class=\"item-title\">{_esc(p.get('name'))}{link_html}</div>"
                f"{tech_html}</div></div>{desc}</div>"
            )
        proj_html = "".join(items)

    # Education HTML
    edu_html = ""
    if cv.get("education"):
        items = []
        for e in cv["education"]:
            field = f' — {_esc(e.get("field"))}' if e.get("field") else ""
            items.append(
                f'<div class="item"><div class="item-header">'
                f"<div><div class=\"item-title\">{_esc(e.get('degree'))}{field}</div>"
                f"<div class=\"item-sub\">{_esc(e.get('school'))}</div></div>"
                f'<div class="item-date">{_esc(e.get("startYear"))} — {_esc(e.get("endYear"))}</div></div></div>'
            )
        edu_html = "".join(items)

    # Certifications HTML
    cert_html = ""
    if cv.get("certifications"):
        items = []
        for c in cv["certifications"]:
            items.append(
                f'<div class="item"><div class="item-header">'
                f"<div><div class=\"item-title\">{_esc(c.get('name'))}</div>"
                f"<div class=\"item-sub\">{_esc(c.get('organization'))}</div></div>"
                f'<div class="item-date">{_esc(c.get("date"))}</div></div></div>'
            )
        cert_html = "".join(items)

    # Contact links
    contact_parts = []
    if profile.get("email"):
        contact_parts.append(f'<span>{_esc(profile["email"])}</span>')
    if profile.get("phone"):
        contact_parts.append(f'<span>{_esc(profile["phone"])}</span>')
    if profile.get("city"):
        contact_parts.append(f'<span>{_esc(profile["city"])}</span>')
    if profile.get("linkedin"):
        contact_parts.append(f'<span>{_esc(profile["linkedin"])}</span>')
    if profile.get("github"):
        contact_parts.append(f'<span>{_esc(profile["github"])}</span>')
    if profile.get("portfolio"):
        contact_parts.append(f'<span>{_esc(profile["portfolio"])}</span>')
    links = '<span class="sep"> &bull; </span>'.join(contact_parts)

    # Summary
    summary_html = ""
    if cv.get("summary"):
        summary_html = f'<div class="summary">{_esc(cv["summary"])}</div>'

    # Two-column skills/languages
    two_col_parts = []
    if skills_html:
        two_col_parts.append(_section("C O M P É T E N C E S", skills_html))
    if langs_html:
        two_col_parts.append(_section("L A N G U E S", langs_html))
    two_col = (
        f'<div class="two-col">{"".join(two_col_parts)}</div>' if two_col_parts else ""
    )

    html = f"""<!DOCTYPE html><html lang="{lang}" dir="{direction}"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:{font_family};font-size:13px;color:#1a1a2e;background:#fff;direction:{direction}}}.page{{max-width:794px;margin:0 auto;padding:40px 48px}}.header{{border-bottom:3px solid #00b894;padding-bottom:20px;margin-bottom:24px;text-align:center}}.name{{font-size:30px;font-weight:800;color:#0a3d62;letter-spacing:-0.5px;margin-bottom:6px}}.position{{font-size:14px;color:#00b894;font-weight:600;margin-bottom:12px}}.contacts{{display:flex;flex-wrap:wrap;justify-content:center;gap:6px 4px;font-size:11.5px;color:#555;align-items:center}}.sep{{color:#ccc;padding:0 4px}}.summary{{background:#f0faf7;border-left:4px solid #00b894;padding:12px 16px;border-radius:0 8px 8px 0;font-size:13px;line-height:1.8;color:#2d3436;margin-bottom:20px}}.section{{margin-bottom:22px}}.section-title{{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:{'0' if is_arabic else '2px'};color:#00b894;border-bottom:1px solid #e0f5ef;padding-bottom:5px;margin-bottom:12px}}.skills{{display:flex;flex-wrap:wrap;gap:6px}}.skill{{background:#e8f8f3;color:#00876a;font-size:11.5px;padding:3px 10px;border-radius:20px;font-weight:500}}.lang{{background:#eaf2ff;color:#2d6cdf}}.item{{margin-bottom:14px}}.item-header{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:4px}}.item-title{{font-weight:700;font-size:13.5px;color:#0a3d62}}.item-sub{{font-size:12px;color:#636e72;margin-top:2px}}.item-date{{font-size:11px;color:#b2bec3;white-space:nowrap;padding-top:2px}}.item-desc{{font-size:12.5px;color:#4a4a4a;line-height:1.8;margin-top:4px}}.tech{{background:#f1f2f6;color:#636e72;font-size:11px;padding:1px 7px;border-radius:4px;margin-right:3px}}.link{{font-size:11px;color:#00b894;text-decoration:none;margin-left:6px;direction:ltr}}.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}</style></head><body><div class="page"><div class="header"><div class="name">{_esc(profile.get('firstName'))} {_esc(profile.get('lastName'))}</div><div class="position">{_esc(job.get('targetPosition'))}</div><div class="contacts">{links}</div></div>{summary_html} {_section('F O R M A T I O N', edu_html)}{_section('P R O J E T S', proj_html)}{exp_html if not exp_html else _section('E X P É R I E N C E S', exp_html)}{two_col}{cert_html if not cert_html else _section('C E R T I F I C A T I O N S', cert_html)}</div></body></html>"""

    return html
