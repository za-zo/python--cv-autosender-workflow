import json
import re

def build_cv_prompt(profile, company, job):
    """Build CV generation prompt (port of n8n 'Code - Préparer Prompt CV')."""
    system_message = (
        "Tu es un expert en rédaction de CV professionnels.\n"
        "Réponds UNIQUEMENT en JSON valide sans aucun markdown, backticks ou texte supplémentaire.\n"
        "N'invente AUCUNE information — utilise uniquement les données fournies."
    )

    user_message = (
        "Génère le contenu d'un CV optimisé et compatible avec l'entreprise cible.\n"
        f"La langue du CV est : {job.get('cv_language') or 'français'}\n\n"
        "=== PROFIL DU CANDIDAT ===\n"
        f"Nom complet : {profile.get('firstName', '')} {profile.get('lastName', '')}\n"
        f"Email : {profile.get('email', '')}\n"
        f"Téléphone : {profile.get('phone', '')}\n"
        f"Localisation : {profile.get('city', '')}\n"
        f"GitHub : {profile.get('github', '')}\n"
        f"LinkedIn : {profile.get('linkedin', '')}\n"
        f"Portfolio : {profile.get('portfolio', '')}\n"
        f"Résumé actuel : {profile.get('summary', '')}\n"
        f"Compétences : {', '.join(profile.get('skills', []))}\n"
        f"Langues : {', '.join(profile.get('languages', []))}\n"
        f"Formation : {json.dumps(profile.get('education', []), default=str)}\n"
        f"Expériences : {json.dumps(profile.get('experiences', []), default=str)}\n"
        f"Projets : {json.dumps(profile.get('projects', []), default=str)}\n"
        f"Certifications : {json.dumps(profile.get('certifications', []), default=str)}\n\n"
        "=== ENTREPRISE CIBLE ===\n"
        f"Nom : {company.get('name', '')}\n"
        f"Email : {company.get('email', '')}\n"
        f"Site web : {company.get('website', '')}\n"
        f"Secteur : {company.get('sector', '')}\n"
        f"Taille : {company.get('size', '')}\n"
        f"Localisation : {company.get('location', '')}\n"
        f"Description : {company.get('description', '')}\n"
        f"Technologies : {', '.join(company.get('technologies', []))}\n"
        f"Projets entreprise : {json.dumps(company.get('projects', []), default=str)}\n\n"
        "=== POSTE VISÉ ===\n"
        f"Titre : {job.get('targetPosition', '')}\n"
        f"Description : {job.get('jobDescription', '')}\n"
        f"Niveau : {job.get('experienceLevel', '')}\n"
        f"Type de contrat : {job.get('contractType', '')}\n"
        f"Notes spéciales : {job.get('notes', '')}\n\n"
        "=== RÈGLES STRICTES ===\n"
        "1. Mets en avant les compétences et projets les plus pertinents pour cette entreprise\n"
        "2. Adapte le résumé à la culture de l'entreprise — détaillé et spécifique (3-5 phrases)\n"
        "3. N'invente AUCUNE information\n"
        "4. Si une section est vide, ne l'inclus pas\n"
        "5. Pour chaque projet : TOUTES les technologies + description complète\n"
        "6. Pour chaque expérience : description complète avec réalisations concrètes\n"
        "7. Inclus TOUTES les compétences pertinentes du profil\n"
        "8. Maximum 8 projets — les plus pertinents pour cette entreprise\n"
        "9. Réponds UNIQUEMENT en JSON valide\n\n"
        "FORMAT JSON ATTENDU :\n"
        '{\n'
        '  "summary": "...",\n'
        '  "skills": ["..."],\n'
        '  "experiences": [{"title": "", "company": "", "startDate": "", "endDate": "", "description": ""}],\n'
        '  "projects": [{"name": "", "description": "", "technologies": [], "link": ""}],\n'
        '  "education": [{"school": "", "degree": "", "field": "", "startYear": "", "endYear": ""}],\n'
        '  "languages": ["..."],\n'
        '  "certifications": [{"name": "", "organization": "", "date": ""}]\n'
        '}'
    )

    return system_message, user_message


def build_message_prompt(profile, company, job):
    """Build message generation prompt (port of n8n 'Code - Préparer Prompt Message')."""
    raw = (job.get("cv_language") or "").lower().strip()
    if raw in ("anglais", "english", "en"):
        lang = "English"
    elif raw in ("arabe", "arabic", "ar"):
        lang = "Arabic"
    else:
        lang = "French"

    examples = {
        "French": (
            "EXAMPLE (French):\n"
            "Madame, Monsieur,\n"
            "Je souhaite postuler au poste de Développeur Full Stack chez TechCorp, reconnue pour son expertise en développement web. Votre utilisation de React.js et Node.js correspond parfaitement à mon profil.\n\n"
            "Fort de mes compétences en React, Next.js et MongoDB, je suis convaincu de pouvoir contribuer efficacement à vos projets. Mon portfolio : https://monsite.com — GitHub : https://github.com/monprofil.\n\n"
            "Dans l'attente de votre retour, je reste disponible pour tout entretien.\n"
            "Jean Dupont"
        ),
        "English": (
            "EXAMPLE (English):\n"
            "Dear Hiring Manager,\n"
            "I am excited to apply for the Full Stack Developer position at TechCorp. Your use of React.js and Node.js perfectly matches my skill set.\n\n"
            "With strong experience in React, Next.js and MongoDB, I am confident I can contribute effectively. Portfolio: https://mysite.com — GitHub: https://github.com/myprofile.\n\n"
            "I look forward to hearing from you.\n"
            "John Smith"
        ),
        "Arabic": (
            "EXAMPLE (Arabic):\n"
            "السلام عليكم،\n"
            "يسعدني التقدم لشغل منصب مطور Full Stack في شركة TechCorp. استخدامكم لـ React.js و Node.js يتوافق تماماً مع مهاراتي.\n\n"
            "بفضل خبرتي في React و Next.js و MongoDB، أنا واثق من قدرتي على المساهمة في مشاريعكم. موقعي: https://mysite.com — GitHub: https://github.com/myprofile.\n\n"
            "أتطلع إلى تلقي ردكم وأنا رهن الإشارة لأي مقابلة.\n"
            "محمد العربي"
        ),
    }

    system_message = (
        "You are an expert cover letter writer.\n"
        f"TARGET LANGUAGE: {lang}\n"
        "STRICT NEGATIVE CONSTRAINT: DO NOT use JSON. DO NOT use curly braces { } or brackets [ ]. DO NOT use key-value pairs.\n"
        'NEGATIVE EXAMPLE: Do NOT output text like {"cover_letter": "..."} or {"text": "..."}.\n'
        'STRICT RULE: If your output begins with a brace "{", it is a failure. Start directly with the text.\n'
        f"ABSOLUTE RULE 1: Write EVERY word in {lang}. Zero exceptions.\n"
        "ABSOLUTE RULE 2: Technology names (React, Node.js, Next.js, MongoDB, etc.) stay in English regardless of target language.\n"
        f"ABSOLUTE RULE 3: Salutation, body, closing and name are ALL in {lang}.\n"
        "ABSOLUTE RULE 4: Return ONLY the cover letter text. No JSON, no keys, no wrapper, no markdown. Just the raw letter.\n"
        "ABSOLUTE RULE 5: Do NOT wrap the letter in quotes. Output raw unquoted text only.\n"
        f"ABSOLUTE RULE 6: This letter will be sent DIRECTLY as an email body without any modification. Write it email-ready: proper greeting, clean paragraphs, and a professional closing. No placeholders, no notes, no comments, nothing extra — only the final letter text.\n"
        "ABSOLUTE RULE 7: NEVER use markdown formatting. No **bold**, no *italic*, no _underline_, no # headings, no bullet points with -, no backticks, no markdown syntax of any kind. Use only plain text. This will be displayed as raw text in an email — any markdown will look suspicious and unprofessional."
    )

    example = examples.get(lang, examples["French"])

    user_message = (
        f"{example}\n\n"
        f"--- NOW generate a message in {lang.upper()} ONLY using this data ---\n\n"
        "=== CANDIDATE ===\n"
        f"Full Name: {profile.get('firstName', '')} {profile.get('lastName', '')}\n"
        f"Email: {profile.get('email', '')}\n"
        f"Phone: {profile.get('phone', '')}\n"
        f"Location: {profile.get('city', '')}\n"
        f"GitHub: {profile.get('github', '')}\n"
        f"LinkedIn: {profile.get('linkedin', '')}\n"
        f"Portfolio: {profile.get('portfolio', '')}\n"
        f"Summary: {profile.get('summary', '')}\n"
        f"Skills: {', '.join(profile.get('skills', []))}\n"
        f"Languages: {', '.join(profile.get('languages', []))}\n"
        f"Education: {json.dumps(profile.get('education', []), default=str)}\n"
        f"Experiences: {json.dumps(profile.get('experiences', []), default=str)}\n"
        f"Projects: {json.dumps(profile.get('projects', []), default=str)}\n"
        f"Certifications: {json.dumps(profile.get('certifications', []), default=str)}\n\n"
        "=== COMPANY ===\n"
        f"Name: {company.get('name', '')}\n"
        f"Email: {company.get('email', '')}\n"
        f"Website: {company.get('website', '')}\n"
        f"Sector: {company.get('sector', '')}\n"
        f"Size: {company.get('size', '')}\n"
        f"Location: {company.get('location', '')}\n"
        f"Description: {company.get('description', '')}\n"
        f"Technologies: {', '.join(company.get('technologies', []))}\n"
        f"Company Projects: {json.dumps(company.get('projects', []), default=str)}\n\n"
        "=== JOB ===\n"
        f"Position: {job.get('targetPosition', '')}\n"
        f"Job Description: {job.get('jobDescription', '')}\n"
        f"Experience Level: {job.get('experienceLevel', '')}\n"
        f"Contract Type: {job.get('contractType', '')}\n"
        f"Special Notes: {job.get('notes', '')}\n\n"
        "=== RULES ===\n"
        f"1. Write entirely in {lang} — salutation, body, closing, name\n"
        "2. Technology names stay in English\n"
        "3. Mention specific company elements\n"
        "4. Include portfolio/GitHub links naturally in the body\n"
        "5. No placeholders, no subject line, no title\n"
        "6. Maximum 200 words\n"
        "7. End with a polite closing phrase then the full candidate name"
    )

    return system_message, user_message, lang


def _extract_content(provider_name, response_json):
    """Extract the text content from any provider's response JSON."""
    name = provider_name.lower()
    if "bytez" in name:
        return response_json["output"]["content"]
    elif "groq" in name:
        return response_json["choices"][0]["message"]["content"]
    elif "gemini" in name:
        return response_json["candidates"][0]["content"]["parts"][0]["text"]
    elif "openai" in name:
        return response_json["output"][0]["content"][0]["text"]
    elif "openrouter" in name:
        return response_json["choices"][0]["message"]["content"]
    elif "z.ai" in name:
        return response_json["choices"][0]["message"]["content"]
    elif "hugging face" in name:
        return response_json["choices"][0]["message"]["content"]
    elif "cerebras" in name:
        return response_json["choices"][0]["message"]["content"]
    elif "cloudflare" in name:
        return response_json["result"]["response"]
    elif "cohere" in name:
        return response_json["message"]["content"][0]["text"]
    raise ValueError(f"Unknown provider: {provider_name}")


def parse_cv_response(provider_name, response_json):
    """Parse CV response from any provider (port of n8n 'Code - Parser Réponse')."""
    content = _extract_content(provider_name, response_json)
    if isinstance(content, dict):
        return content
    clean = re.sub(r"```json|```", "", content).strip()
    return json.loads(clean)


def parse_message_response(provider_name, response_json):
    """Parse message response from any provider (port of n8n 'Code - Parser Message')."""
    message = _extract_content(provider_name, response_json)
    if isinstance(message, dict):
        message = json.dumps(message)
    # Clean: remove surrounding quotes, fix escaped newlines/tabs
    message = re.sub(r'^[\'"]+|[\'"]+$', "", message)
    message = message.replace("\\n", "\n").replace("\\t", "\t").strip()
    # Strip markdown formatting
    message = re.sub(r"\*\*(.+?)\*\*", r"\1", message)  # **bold** -> bold
    message = re.sub(r"\*(.+?)\*", r"\1", message)        # *italic* -> italic
    message = re.sub(r"_(.+?)_", r"\1", message)           # _underline_ -> underline
    message = re.sub(r"`(.+?)`", r"\1", message)           # `code` -> code
    return message
