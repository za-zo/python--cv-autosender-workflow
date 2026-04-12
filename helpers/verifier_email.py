"""
=============================================================================
VÉRIFICATEUR D'EMAIL - Version finale avec Disify (gratuit, sans clé API)
=============================================================================
Installation :
    pip install email-validator dnspython requests

Ordre de vérification :
    1. Syntaxe
    2. Liste statique GitHub (+100k domaines jetables)
    3. DNS / MX records
    4. Grands providers (Gmail, Outlook, Yahoo...)
    5. API Disify (gratuite, base dynamique de domaines jetables)
    6. Vérification SMTP directe (RCPT TO)
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

SMTP_TIMEOUT = 8   # secondes avant abandon connexion SMTP
DNS_TIMEOUT  = 5   # secondes avant abandon resolution DNS

# Liste de secours si GitHub est inaccessible au demarrage
FALLBACK_JETABLE = {
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "yopmail.com",
    "trashmail.com", "fakeinbox.com", "10minutemail.com", "maildrop.cc",
    "throwaway.email", "discard.email", "spamgourmet.com", "tempr.email",
    "mohmal.com", "tempinbox.com", "dispostable.com", "sharklasers.com",
    "dependity.com", "emailondeck.com", "drrieca.com", "hostelness.com",
}

# Grands providers : SMTP non fiable (ils acceptent tout sans confirmer)
GRANDS_PROVIDERS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.fr", "yahoo.co.uk",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me",
}


# =============================================================================
# ETAPE 0 : CHARGEMENT DE LA LISTE STATIQUE (GitHub, +100k domaines)
# =============================================================================

def charger_domaines_jetables() -> set:
    """
    Telecharge +100 000 domaines jetables depuis GitHub.
    Appelee UNE SEULE FOIS au demarrage du script.
    Utilise la liste de secours en cas d'echec reseau.
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
        print(f"[INIT] {len(domaines)} domaines jetables charges depuis GitHub")
        return domaines
    except Exception as e:
        print(f"[INIT] GitHub inaccessible ({e}) -> liste de secours utilisee")
        return FALLBACK_JETABLE


# Chargement unique au demarrage du script
DOMAINES_JETABLES = charger_domaines_jetables()


# =============================================================================
# ETAPE 5 : API DISIFY (gratuite, dynamique, sans cle API)
# =============================================================================

def verifier_disify(email: str) -> dict:
    """
    Verifie l'email via l'API Disify :
        - Base de donnees dynamique de domaines jetables/invalides
        - 100% gratuite, sans inscription, sans cle API
        - Couvre les domaines absents des listes statiques (ex: dependity.com)

    Retourne :
        {
            "est_jetable"    : bool  -> domaine jetable selon Disify
            "domaine_valide" : bool  -> domaine avec MX valide selon Disify
            "erreur"         : str   -> None si OK, message si API inaccessible
        }
    """
    try:
        url      = f"https://www.disify.com/api/email/{email}"
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        data = response.json()

        return {
            "est_jetable"   : data.get("disposable", False),
            "domaine_valide": data.get("dns", False),
            "erreur"        : None
        }

    except requests.exceptions.Timeout:
        return {"est_jetable": False, "domaine_valide": True, "erreur": "disify_timeout"}
    except Exception as e:
        return {"est_jetable": False, "domaine_valide": True, "erreur": f"disify_erreur: {e}"}


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def verifier_email(email: str) -> dict:
    """
    Verifie si une adresse email est valide et livrable.

    Retourne :
        {
            "valide" : bool  -> True = utiliser (generer IA + envoyer Gmail)
            "existe" : bool  -> True = adresse probablement existante
            "raison" : str   -> explication detaillee du resultat
        }
    """

    email = email.strip().lower()

    # -- ETAPE 1 : Syntaxe --------------------------------------------------
    try:
        valide = validate_email(email, check_deliverability=False)
        email  = valide.normalized
    except EmailNotValidError as e:
        return {"valide": False, "existe": False, "raison": f"syntaxe_invalide: {e}"}

    domaine = email.split("@")[1]

    # -- ETAPE 2 : Liste statique GitHub ------------------------------------
    if domaine in DOMAINES_JETABLES:
        return {"valide": False, "existe": False, "raison": "jetable_liste_statique"}

    # -- ETAPE 3 : DNS / MX records -----------------------------------------
    try:
        mx_records = dns.resolver.resolve(domaine, "MX", lifetime=DNS_TIMEOUT)
        serveurs   = sorted(
            [(r.preference, str(r.exchange).rstrip(".")) for r in mx_records]
        )
        serveur_mx = serveurs[0][1]
    except dns.resolver.NXDOMAIN:
        return {"valide": False, "existe": False, "raison": "domaine_inexistant"}
    except dns.resolver.NoAnswer:
        return {"valide": False, "existe": False, "raison": "pas_de_mx"}
    except dns.resolver.Timeout:
        return {"valide": False, "existe": False, "raison": "timeout_dns"}
    except Exception as e:
        return {"valide": False, "existe": False, "raison": f"erreur_dns: {e}"}

    # -- ETAPE 4 : Grands providers -----------------------------------------
    # Gmail/Outlook/Yahoo bloquent volontairement la verif SMTP.
    # On verifie quand meme Disify, puis on fait confiance au MX.
    if domaine in GRANDS_PROVIDERS:
        disify = verifier_disify(email)
        if disify["est_jetable"]:
            return {"valide": False, "existe": False, "raison": "jetable_disify_grand_provider"}
        return {"valide": True, "existe": True, "raison": "grand_provider_mx_ok"}

    # -- ETAPE 5 : API Disify (domaines jetables dynamiques) ----------------
    # Capture les domaines absents de la liste statique (ex: dependity.com)
    disify = verifier_disify(email)

    if disify["erreur"] is None:
        if disify["est_jetable"]:
            return {"valide": False, "existe": False, "raison": "jetable_disify"}
        if not disify["domaine_valide"]:
            return {"valide": False, "existe": False, "raison": "domaine_invalide_disify"}
    # Si Disify timeout/erreur -> on continue vers SMTP sans bloquer

    # -- ETAPE 6 : Verification SMTP (RCPT TO) ------------------------------
    # Contacte le serveur mail directement SANS envoyer d'email.
    # En cas de timeout/erreur -> on rejette (conservateur) plutot qu'accepter.
    try:
        with smtplib.SMTP(timeout=SMTP_TIMEOUT) as smtp:
            smtp.connect(serveur_mx, 25)
            smtp.ehlo_or_helo_if_needed()
            smtp.mail("check@verification.local")
            code, _ = smtp.rcpt(email)

            if code == 250:
                return {"valide": True,  "existe": True,  "raison": "smtp_confirme"}
            elif code in (550, 551, 552, 553, 554):
                return {"valide": False, "existe": False, "raison": f"smtp_adresse_inexistante_{code}"}
            else:
                # Code ambigu (greylisting 451, etc.) -> on accepte prudemment
                return {"valide": True,  "existe": True,  "raison": f"smtp_ambigu_{code}"}

    except (smtplib.SMTPConnectError, ConnectionRefusedError):
        # Port 25 bloque (frequent chez les hebergeurs) ->
        # Disify a deja valide le domaine, on fait confiance
        return {"valide": True,  "existe": True,  "raison": "smtp_port_bloque_disify_ok"}

    except socket.timeout:
        # Timeout SMTP = comportement suspect -> on rejette
        # (fix du bug dependity.com de la version precedente)
        return {"valide": False, "existe": False, "raison": "smtp_timeout_suspect"}

    except Exception as e:
        # Toute autre erreur SMTP inattendue -> on rejette par securite
        return {"valide": False, "existe": False, "raison": f"smtp_erreur_suspect: {e}"}


# =============================================================================
# INTEGRATION DANS TON WORKFLOW
# =============================================================================

def traiter_email(email: str) -> bool:
    """
    A appeler dans ton code AVANT de generer le message IA
    et AVANT d'envoyer via Gmail.

    Retourne True  -> continuer (generer IA + envoyer Gmail)
    Retourne False -> skip    (economie tokens + quota Gmail)
    """
    resultat = verifier_email(email)

    if resultat["valide"]:
        print(f"  OK    {email:45s} -> {resultat['raison']}")
        return True
    else:
        print(f"  SKIP  {email:45s} -> {resultat['raison']}")
        return False


# =============================================================================
# DEMONSTRATION
# =============================================================================

if __name__ == "__main__":

    emails_test = [
        # Valides - grands providers
        "utilisateur@gmail.com",
        "quelquun@outlook.com",

        # Valide - domaine professionnel
        "contact@python.org",

        # Invalides - syntaxe
        "pasdarobase.com",
        "double@@domaine.com",

        # Invalide - domaine inexistant
        "test@domainequiexistepas123456.xyz",

        # Invalides - liste statique GitHub
        "temp@mailinator.com",
        "jetable@yopmail.com",

        # Invalide - capture par Disify (absent de la liste statique)
        "lanetta54@dependity.com",
    ]

    print("\n" + "=" * 65)
    print("  VERIFICATION DES EMAILS")
    print("=" * 65 + "\n")

    valides = 0
    skips   = 0

    for email in emails_test:
        if traiter_email(email):
            valides += 1
            # <- ICI ton code existant :
            # message = generer_message_ia(email)
            # envoyer_gmail(email, message)
        else:
            skips += 1
            # <- Rien -> 0 token IA consomme, 0 usage Gmail

    total = len(emails_test)
    print("\n" + "=" * 65)
    print(f"  Total     : {total} emails")
    print(f"  Valides   : {valides}  -> generer IA + envoyer")
    print(f"  Skippes   : {skips}  -> tokens et quota Gmail economises")
    print(f"  Economie  : {round(skips / total * 100)}%")
    print("=" * 65 + "\n")