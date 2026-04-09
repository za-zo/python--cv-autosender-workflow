import json
import re

def build_cv_prompt(profile, company, job):
    """Build CV generation prompt - version améliorée."""

    cv_language = job.get("cv_language") or "français"

    # ─── System message ───────────────────────────────────────────────────────
    system_message = (
        "Tu es un expert en rédaction de CV ATS-optimisés et adaptés aux entreprises cibles.\n"
        "Réponds UNIQUEMENT en JSON valide sans aucun markdown, backticks ou texte supplémentaire.\n"
        "N'invente AUCUNE information — utilise uniquement les données fournies.\n\n"
        "RAISONNEMENT OBLIGATOIRE : Avant de générer, analyse mentalement :\n"
        "  1. Quels mots-clés du poste correspondent aux compétences du candidat ?\n"
        "  2. Quels projets et expériences sont les plus alignés avec l'entreprise cible ?\n"
        "  3. Quel ton adopter selon la culture de l'entreprise (startup agile vs grande entreprise) ?\n"
        "Utilise cette analyse pour produire un CV ciblé et pertinent, pas générique.\n"
    )

    # ─── User message ─────────────────────────────────────────────────────────
    user_message = (
        "Génère le contenu d'un CV optimisé et compatible avec l'entreprise cible.\n\n"

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
        "   → Compare les mots-clés du job description avec les compétences et projets du candidat\n"
        "2. Le résumé doit : mentionner le poste visé, citer 2-3 compétences clés qui correspondent\n"
        "   au job description, et montrer une connaissance du secteur de l'entreprise. 3-5 phrases.\n"
        "3. N'invente AUCUNE information — utilise uniquement ce qui est fourni\n"
        "4. Si une section est vide, ne l'inclus pas dans le JSON\n"
        "5. Pour chaque projet : TOUTES les technologies + description complète\n"
        "6. Pour chaque expérience : description complète avec réalisations concrètes\n"
        "7. Inclus TOUTES les compétences pertinentes du profil\n"
        "8. Maximum 8 projets — sélectionne les plus pertinents pour cette entreprise et ce poste\n"
        f"9. LANGUE STRICTE : Tout le contenu textuel (summary, descriptions) doit être rédigé\n"
        f"   en {cv_language}. Les noms de technologies restent en anglais.\n"
        "10. Réponds UNIQUEMENT en JSON valide — aucun texte avant ou après\n\n"

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
    """Build message generation prompt - version améliorée."""

    # ─── Détection de la langue ───────────────────────────────────────────────
    raw = (job.get("cv_language") or "").lower().strip()
    if raw in ("anglais", "english", "en"):
        lang = "English"
    elif raw in ("arabe", "arabic", "ar"):
        lang = "Arabic"
    else:
        lang = "French"

    # ─── Anti-exemples par langue ─────────────────────────────────────────────
    anti_examples = {
        "French": (
            "=== ANTI-EXEMPLES : Ces phrases sont INTERDITES ===\n"
            "❌ 'Je suis convaincu de pouvoir contribuer efficacement à votre équipe'\n"
            "❌ 'Votre utilisation de X correspond parfaitement à mon profil'\n"
            "❌ 'Je suis passionné par le développement web'\n"
            "❌ 'Dans l'attente de votre retour favorable'\n"
            "❌ 'Je me permets de vous contacter pour...'\n"
            "Ces formules sont génériques, évitées par tout bon recruteur. Ne les utilise jamais.\n"
        ),
        "English": (
            "=== ANTI-EXAMPLES: These phrases are FORBIDDEN ===\n"
            "❌ 'I am confident I can contribute effectively to your team'\n"
            "❌ 'Your use of X perfectly matches my skill set'\n"
            "❌ 'I am passionate about web development'\n"
            "❌ 'I look forward to hearing from you'\n"
            "❌ 'I am excited to apply for this position'\n"
            "These are generic filler phrases that recruiters ignore. Never use them.\n"
        ),
        "Arabic": (
            "=== أمثلة مضادة: هذه العبارات محظورة ===\n"
            "❌ 'أنا واثق من قدرتي على المساهمة في فريقكم'\n"
            "❌ 'مهاراتي تتوافق تماماً مع متطلبات الوظيفة'\n"
            "❌ 'أنا شغوف بتطوير الويب'\n"
            "❌ 'أتطلع إلى تلقي ردكم'\n"
            "هذه عبارات عامة يتجاهلها المسؤولون عن التوظيف. لا تستخدمها أبداً.\n"
        ),
    }

    # ─── System message ───────────────────────────────────────────────────────
    system_message = (
        "You are an elite cover letter writer who specializes in crafting messages that get interviews.\n"
        f"TARGET LANGUAGE: {lang}\n\n"

        "=== YOUR WRITING PHILOSOPHY ===\n"
        "- Write like a sharp human professional, never like a template or a robot\n"
        "- Open with a hook that immediately shows you understand the company's specific world\n"
        "- Mention at least ONE concrete project or achievement from the candidate's experience\n"
        "- Position the candidate as a solution to the company's needs, not just a job seeker\n"
        "- Every sentence must earn its place — cut anything vague or generic\n"
        "- The tone should feel confident, specific, and human\n\n"

        "=== STRICT FORMAT RULES ===\n"
        f"ABSOLUTE RULE 1: Write EVERY word in {lang}. Zero exceptions.\n"
        "ABSOLUTE RULE 2: Technology names (React, Node.js, Next.js, MongoDB, etc.) stay in English.\n"
        "ABSOLUTE RULE 3: Return ONLY the cover letter text. No JSON, no keys, no markdown, no wrapper.\n"
        "ABSOLUTE RULE 4: Do NOT wrap the letter in quotes. Output raw unquoted plain text only.\n"
        "ABSOLUTE RULE 5: NEVER use markdown. No **bold**, no *italic*, no bullet points, no headings.\n"
        "ABSOLUTE RULE 6: This letter is sent directly as email body. Write it email-ready.\n"
        "ABSOLUTE RULE 7: No placeholders, no subject line, no title, no comments.\n"
        f"ABSOLUTE RULE 8: If output begins with '{{', it is a failure. Start directly with the salutation.\n"
    )

    # ─── User message ─────────────────────────────────────────────────────────
    user_message = (
        f"{anti_examples.get(lang, anti_examples['French'])}\n"

        f"--- GENERATE a cover letter in {lang.upper()} ONLY using the data below ---\n\n"

        "=== CANDIDATE ===\n"
        f"Full Name: {profile.get('firstName', '')} {profile.get('lastName', '')}\n"
        f"Email: {profile.get('email', '')}\n"
        f"Phone: {profile.get('phone', '')}\n"
        f"Location: {profile.get('city', '')}\n"
        f"GitHub: {profile.get('github', '')}\n"
        f"Portfolio: {profile.get('portfolio', '')}\n"
        f"LinkedIn: {profile.get('linkedin', '')}\n"
        f"Summary: {profile.get('summary', '')}\n"
        f"Skills: {', '.join(profile.get('skills', []))}\n"
        f"Languages: {', '.join(profile.get('languages', []))}\n"
        f"Education: {json.dumps(profile.get('education', []), default=str)}\n"
        f"Experiences (pick the most relevant to the job): {json.dumps(profile.get('experiences', []), default=str)}\n"
        f"Projects (mention at least one concrete project): {json.dumps(profile.get('projects', []), default=str)}\n"
        f"Certifications: {json.dumps(profile.get('certifications', []), default=str)}\n\n"

        "=== COMPANY ===\n"
        f"Name: {company.get('name', '')}\n"
        f"Email: {company.get('email', '')}\n"
        f"Website: {company.get('website', '')}\n"
        f"Sector: {company.get('sector', '')}\n"
        f"Size: {company.get('size', '')}\n"
        f"Location: {company.get('location', '')}\n"
        f"Description: {company.get('description', '')}\n"
        f"Technologies they use: {', '.join(company.get('technologies', []))}\n"
        f"Company Projects: {json.dumps(company.get('projects', []), default=str)}\n\n"

        "=== JOB ===\n"
        f"Position: {job.get('targetPosition', '')}\n"
        f"Job Description (extract keywords and match with candidate): {job.get('jobDescription', '')}\n"
        f"Experience Level: {job.get('experienceLevel', '')}\n"
        f"Contract Type: {job.get('contractType', '')}\n"
        f"Special Notes: {job.get('notes', '')}\n\n"

        "=== WRITING RULES ===\n"
        f"1. Write entirely in {lang} — salutation, body, closing, name\n"
        "2. Technology names stay in English\n"
        "3. HOOK: Open with something specific about the company or the role — not about yourself\n"
        "4. ACHIEVEMENT: Reference at least one real project or experience from the candidate's data\n"
        "5. VALUE: Explain what the candidate brings to THIS company, not just what they want\n"
        "6. LINKS: If GitHub or Portfolio are provided, include them — this is REQUIRED\n"
        "7. LENGTH: 220 to 270 words — enough to be specific, short enough to be read fully\n"
        "8. CLOSING: End with a confident, non-generic closing phrase then the full candidate name\n"
        "9. NO placeholders, NO subject line, NO title, NO notes outside the letter\n"
    )

    return system_message, user_message, lang


def build_contact_message_prompt(profile, contact, contact_message):
    """Build an outreach message prompt for a personal contact (HR, director, etc.)."""

    raw = (contact_message.get("language") or "").lower().strip()
    if raw in ("anglais", "english", "en"):
        lang = "English"
    elif raw in ("arabe", "arabic", "ar"):
        lang = "Arabic"
    else:
        lang = "French"

    msg_type = (contact_message.get("type") or "introduction").strip()
    notes = (contact_message.get("notes") or "").strip()
    contact_name = (contact.get("complete_name") or "").strip()

    system_message = (
        "You are an expert networking outreach writer.\n"
        f"TARGET LANGUAGE: {lang}\n\n"
        "=== STRICT RULES ===\n"
        f"1. Write EVERY word in {lang}. Technology names stay in English.\n"
        "2. Return ONLY the email body text (no subject line, no markdown, no JSON).\n"
        "3. Be concise, specific, and human. Avoid generic filler.\n"
        "4. Mention the attached CV naturally (no file name).\n"
    )

    user_message = (
        f"Write a networking email ({msg_type}) to the contact below.\n\n"
        "=== CANDIDATE ===\n"
        f"Full Name: {profile.get('firstName', '')} {profile.get('lastName', '')}\n"
        f"Email: {profile.get('email', '')}\n"
        f"Phone: {profile.get('phone', '')}\n"
        f"Location: {profile.get('city', '')}\n"
        f"GitHub: {profile.get('github', '')}\n"
        f"Portfolio: {profile.get('portfolio', '')}\n"
        f"LinkedIn: {profile.get('linkedin', '')}\n"
        f"Summary: {profile.get('summary', '')}\n"
        f"Skills: {', '.join(profile.get('skills', []))}\n"
        f"Projects (mention at least one concrete project if relevant): {json.dumps(profile.get('projects', []), default=str)}\n\n"
        "=== CONTACT ===\n"
        f"Name: {contact_name}\n"
        f"Email: {contact.get('email', '')}\n"
        f"Description/context: {contact.get('description', '')}\n\n"
        "=== EXTRA NOTES (optional) ===\n"
        f"{notes}\n\n"
        "=== WRITING GUIDELINES ===\n"
        "- If contact name exists, greet them by name.\n"
        "- Clearly state who you are and what you’re looking for (job/internship/alternance/entrepreneurship) without sounding desperate.\n"
        "- Ask for a short call or for the right person to speak to.\n"
        "- Keep it short: 140–190 words.\n"
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
    elif "sambanova" in name:
        return response_json["choices"][0]["message"]["content"]
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
    message = message.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'").strip()
    # Strip markdown formatting
    message = re.sub(r"\*\*(.+?)\*\*", r"\1", message)     # **bold** -> bold
    message = re.sub(r"\*(.+?)\*", r"\1", message)         # *italic* -> italic
    message = re.sub(r"_(.+?)_", r"\1", message)           # _underline_ -> underline
    message = re.sub(r"`(.+?)`", r"\1", message)           # `code` -> code
    return message
