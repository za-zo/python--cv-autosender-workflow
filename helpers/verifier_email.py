"""
=============================================================================
VÉRIFICATEUR D'EMAIL - Version finale
=============================================================================
Installation :
    pip install email-validator dnspython requests
=============================================================================
"""

import socket
import smtplib
import requests
import dns.resolver
from email_validator import validate_email, EmailNotValidError


# =============================================================================
# CONFIGURATION
# =============================================================================

SMTP_TIMEOUT     = 8    # secondes avant abandon de la connexion SMTP
DNS_TIMEOUT      = 5    # secondes avant abandon de la résolution DNS
FALLBACK_JETABLE = {    # liste de secours si GitHub est inaccessible
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "yopmail.com",
    "trashmail.com", "fakeinbox.com", "10minutemail.com", "maildrop.cc",
    "throwaway.email", "discard.email", "spamgourmet.com", "tempr.email",
    "mohmal.com", "tempinbox.com", "dispostable.com", "sharklasers.com",
}

# Grands providers : leur SMTP accepte tout sans confirmer → on skip l'étape SMTP
GRANDS_PROVIDERS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.fr", "yahoo.co.uk",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me",
}


# =============================================================================
# CHARGEMENT DE LA LISTE DES DOMAINES JETABLES
# =============================================================================

def charger_domaines_jetables() -> set:
    """
    Télécharge +100 000 domaines jetables depuis GitHub (communauté open-source).
    À appeler UNE SEULE FOIS au démarrage du script.
    En cas d'échec, utilise la liste de secours intégrée.
    """
    url = (
        "https://raw.githubusercontent.com/"
        "disposable-email-domains/disposable-email-domains/"
        "master/disposable_email_blocklist.conf"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        domaines = set(response.text.strip().splitlines())
        print(f"[OK] {len(domaines)} domaines jetables chargés depuis GitHub")
        return domaines
    except Exception as e:
        print(f"[ATTENTION] Impossible de charger la liste GitHub : {e}")
        print(f"[FALLBACK] Utilisation de la liste de secours ({len(FALLBACK_JETABLE)} domaines)")
        return FALLBACK_JETABLE


# Chargement unique au démarrage
DOMAINES_JETABLES = charger_domaines_jetables()


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def verifier_email(email: str) -> dict:
    """
    Vérifie si une adresse email est valide et livrable.

    Étapes (du plus rapide au plus précis) :
        1. Syntaxe
        2. Domaine jetable
        3. DNS / MX records
        4. Grands providers (Gmail, Outlook, Yahoo...)
        5. Vérification SMTP directe (RCPT TO)

    Retourne :
        {
            "valide" : bool  → True = utiliser cet email (générer IA + envoyer)
            "existe" : bool  → True = adresse probablement existante
            "raison" : str   → explication du résultat
        }
    """

    email = email.strip().lower()

    # ── ÉTAPE 1 : Syntaxe ─────────────────────────────────────────────────
    try:
        valide = validate_email(email, check_deliverability=False)
        email  = valide.normalized
    except EmailNotValidError as e:
        return {
            "valide": False,
            "existe": False,
            "raison": f"syntaxe_invalide → {e}"
        }

    domaine = email.split("@")[1]

    # ── ÉTAPE 2 : Domaine jetable ──────────────────────────────────────────
    if domaine in DOMAINES_JETABLES:
        return {
            "valide": False,
            "existe": False,
            "raison": "email_jetable"
        }

    # ── ÉTAPE 3 : DNS / MX records ────────────────────────────────────────
    try:
        mx_records = dns.resolver.resolve(domaine, "MX", lifetime=DNS_TIMEOUT)
        serveurs   = sorted(
            [(r.preference, str(r.exchange).rstrip(".")) for r in mx_records]
        )
        serveur_mx = serveurs[0][1]
    except dns.resolver.NXDOMAIN:
        return {
            "valide": False,
            "existe": False,
            "raison": "domaine_inexistant"
        }
    except dns.resolver.NoAnswer:
        return {
            "valide": False,
            "existe": False,
            "raison": "pas_de_mx_sur_ce_domaine"
        }
    except dns.resolver.Timeout:
        return {
            "valide": False,
            "existe": False,
            "raison": "timeout_dns"
        }
    except Exception as e:
        return {
            "valide": False,
            "existe": False,
            "raison": f"erreur_dns → {e}"
        }

    # ── ÉTAPE 4 : Grands providers ────────────────────────────────────────
    # Gmail/Outlook/Yahoo bloquent la vérif SMTP volontairement.
    # Si le MX existe, on fait confiance → valide: True
    if domaine in GRANDS_PROVIDERS:
        return {
            "valide": True,
            "existe": True,
            "raison": "grand_provider_mx_ok"
        }

    # ── ÉTAPE 5 : Vérification SMTP (RCPT TO) ─────────────────────────────
    # On contacte le serveur mail pour vérifier l'adresse SANS envoyer d'email
    try:
        with smtplib.SMTP(timeout=SMTP_TIMEOUT) as smtp:
            smtp.connect(serveur_mx, 25)
            smtp.ehlo_or_helo_if_needed()
            smtp.mail("check@verification.local")
            code, _ = smtp.rcpt(email)

            if code == 250:
                return {
                    "valide": True,
                    "existe": True,
                    "raison": "smtp_confirme"
                }
            elif code in (550, 551, 552, 553, 554):
                return {
                    "valide": False,
                    "existe": False,
                    "raison": f"adresse_inexistante_code_{code}"
                }
            else:
                # Code ambigu (greylisting, etc.) → on accepte par précaution
                return {
                    "valide": True,
                    "existe": True,
                    "raison": f"smtp_ambigu_code_{code}"
                }

    except (smtplib.SMTPConnectError, ConnectionRefusedError):
        # Serveur injoignable → on fait confiance au MX
        return {
            "valide": True,
            "existe": True,
            "raison": "smtp_inaccessible_mx_ok"
        }
    except socket.timeout:
        return {
            "valide": True,
            "existe": True,
            "raison": "smtp_timeout_mx_ok"
        }
    except Exception as e:
        return {
            "valide": True,
            "existe": True,
            "raison": f"smtp_erreur_mx_ok → {e}"
        }


# =============================================================================
# INTÉGRATION DANS TON WORKFLOW
# =============================================================================

def traiter_email(email: str) -> bool:
    """
    Fonction à appeler dans ton code AVANT de générer le message IA
    et AVANT d'envoyer via Gmail.

    Retourne True  → continuer (générer IA + envoyer Gmail)
    Retourne False → skip (économie tokens + quota Gmail)
    """
    resultat = verifier_email(email)

    if resultat["valide"]:
        print(f"  ✅  {email:45s} → {resultat['raison']}")
        return True
    else:
        print(f"  ❌  {email:45s} → SKIP ({resultat['raison']})")
        return False


# =============================================================================
# DÉMONSTRATION
# =============================================================================

if __name__ == "__main__":

    emails_test = [
        # # Cas valides
        # "utilisateur@gmail.com",
        # "contact@python.org",
        # "quelquun@outlook.com",

        # # Cas invalides — syntaxe
        # "pasdarobase.com",
        # "double@@domaine.com",
        # "@domaine.com",

        # # Cas invalides — domaine inexistant
        # "test@domainequiexistepas123456.xyz",
        # "hello@faux-domaine-zzz.net",

        # # Cas invalides — emails jetables
        # "temp@mailinator.com",
        # "jetable@yopmail.com",
        # "trash@guerrillamail.com",

        "lanetta54@dependity.com"
    ]

    print("\n" + "=" * 65)
    print("  VÉRIFICATION DES EMAILS")
    print("=" * 65 + "\n")

    valides = 0
    skips   = 0

    for email in emails_test:
        if traiter_email(email):
            valides += 1
            # ← ICI ton code : génère message IA + envoie Gmail
            # message = generer_message_ia(email)
            # envoyer_gmail(email, message)
        else:
            skips += 1
            # ← Rien → 0 token IA consommé, 0 usage Gmail

    print("\n" + "=" * 65)
    print(f"  Total     : {len(emails_test)} emails")
    print(f"  Valides   : {valides}  → générer IA + envoyer")
    print(f"  Skippés   : {skips}  → tokens et quota Gmail économisés")
    print(f"  Économie  : {round(skips / len(emails_test) * 100)}%")
    print("=" * 65 + "\n")