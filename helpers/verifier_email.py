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
    4. Provider check (Gmail, Google Workspace, Zoho, Microsoft 365...)
    5. API Disify (gratuite, base dynamique de domaines jetables)
=============================================================================
"""

import requests
import dns.resolver
from email_validator import validate_email, EmailNotValidError


# =============================================================================
# LOGGING
# =============================================================================

COLORS = {
    "green"  : "\033[92m",
    "red"    : "\033[91m",
    "yellow" : "\033[93m",
    "cyan"   : "\033[96m",
    "white"  : "\033[97m",
    "gray"   : "\033[90m",
    "bold"   : "\033[1m",
    "reset"  : "\033[0m",
}

def c(text: str, color: str) -> str:
    """Applique une couleur ANSI au texte."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"

def log_step(numero: int, nom: str, succes: bool, message: str):
    """Affiche une ligne de log pour une etape."""
    icone  = c("✓", "green") if succes else c("✗", "red")
    etape  = c(f"[Step {numero}]", "cyan")
    label  = c(f"{nom:<22}", "white")
    detail = c(message, "green") if succes else c(message, "red")
    print(f"   {etape} {icone}  {label} {detail}")

def log_skip_step(numero: int, nom: str, message: str):
    """Affiche une etape ignoree (non executee car inutile)."""
    etape = c(f"[Step {numero}]", "cyan")
    label = c(f"{nom:<22}", "gray")
    msg   = c(f"— {message}", "gray")
    print(f"   {etape} -  {label} {msg}")

def log_header(email: str):
    """Affiche l'en-tete pour un email."""
    print(f"\n{'─' * 65}")
    print(f"  {c('▶', 'cyan')} {c(email, 'bold')}")
    print(f"{'─' * 65}")

def log_footer(valide: bool, raison: str):
    """Affiche le resultat final d'un email."""
    if valide:
        resultat = c("✅  VALID   → Generate AI message + Send Gmail", "green")
    else:
        resultat = c("❌  SKIPPED → 0 token consumed, 0 Gmail quota used", "red")
    print(f"\n   {c('Result:', 'bold')} {resultat}")
    print(f"   {c('Reason:', 'bold')} {c(raison, 'gray')}")


# =============================================================================
# CONFIGURATION
# =============================================================================

DNS_TIMEOUT  = 5   # secondes avant abandon resolution DNS

# Liste de secours si GitHub est inaccessible au demarrage
FALLBACK_JETABLE = {
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "yopmail.com",
    "trashmail.com", "fakeinbox.com", "10minutemail.com", "maildrop.cc",
    "throwaway.email", "discard.email", "spamgourmet.com", "tempr.email",
    "mohmal.com", "tempinbox.com", "dispostable.com", "sharklasers.com",
    "dependity.com", "emailondeck.com", "drrieca.com", "hostelness.com",
}

# Grands providers par domaine : SMTP non fiable (ils acceptent tout sans confirmer)
GRANDS_PROVIDERS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.fr", "yahoo.co.uk",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me",
}

# Serveurs MX hebergeant des domaines tiers (Google Workspace, Microsoft 365...)
# Ex: heuristik.tech utilise aspmx.l.google.com -> traiter comme Gmail
MX_PROVIDERS_FIABLES = {
    "google.com",              # Google Workspace  -> aspmx.l.google.com
    "googlemail.com",          # Google Workspace  -> alt*.aspmx.l.google.com
    "outlook.com",             # Microsoft 365     -> *.mail.protection.outlook.com
    "protection.outlook.com",  # Microsoft 365
    "yahoodns.net",            # Yahoo Business
    "zoho.com",                # Zoho Mail         -> mx.zoho.com
    "zoho.in",                 # Zoho Mail India   -> mx.zoho.in
    "zoho.eu",                 # Zoho Mail Europe  -> mx.zoho.eu
    "mimecast.com",            # Mimecast (filtre email entreprise)
    "pphosted.com",            # Proofpoint (filtre email entreprise)
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
# ETAPE 5 : APIs JETABLES (Disify + Kickbox, gratuits, sans cle API)
# =============================================================================

def verifier_disify(email: str) -> dict:
    """
    API Disify — base dynamique de domaines jetables.
    Gratuite, sans inscription, sans cle API.
    """
    try:
        response = requests.get(
            f"https://www.disify.com/api/email/{email}",
            timeout=6
        )
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


def verifier_kickbox(domaine: str) -> dict:
    """
    API Kickbox — second avis sur les domaines jetables.
    Gratuite, sans inscription, sans cle API.
    Utile quand Disify rate un domaine (ex: dependity.com).
    """
    try:
        response = requests.get(
            f"https://open.kickbox.com/v1/disposable/{domaine}",
            timeout=6
        )
        response.raise_for_status()
        data = response.json()
        return {
            "est_jetable": data.get("disposable", False),
            "erreur"     : None
        }
    except requests.exceptions.Timeout:
        return {"est_jetable": False, "erreur": "kickbox_timeout"}
    except Exception as e:
        return {"est_jetable": False, "erreur": f"kickbox_erreur: {e}"}


def verifier_jetable(email: str, domaine: str) -> dict:
    """
    Verifie si un domaine est jetable via Disify + Kickbox.
    Les deux APIs sont interrogees : si l'une dit jetable, c'est jetable.

    Retourne :
        {
            "est_jetable"    : bool
            "domaine_valide" : bool
            "source"         : str   -> quelle API a detecte / confirme
            "erreur"         : str   -> None si au moins une API a repondu
        }
    """
    disify  = verifier_disify(email)
    kickbox = verifier_kickbox(domaine)

    # Si l'une des deux dit jetable -> jetable
    if disify["est_jetable"]:
        return {"est_jetable": True,  "domaine_valide": False, "source": "disify",  "erreur": None}
    if kickbox["est_jetable"]:
        return {"est_jetable": True,  "domaine_valide": False, "source": "kickbox", "erreur": None}

    # Aucune n'a dit jetable
    # domaine_valide = True si au moins Disify a repondu correctement
    domaine_valide = disify["domaine_valide"] if disify["erreur"] is None else True
    les_deux_erreur = disify["erreur"] is not None and kickbox["erreur"] is not None
    erreur = f"{disify['erreur']} / {kickbox['erreur']}" if les_deux_erreur else None
    source = "disify+kickbox" if not les_deux_erreur else "unavailable"

    return {
        "est_jetable"   : False,
        "domaine_valide": domaine_valide,
        "source"        : source,
        "erreur"        : erreur
    }


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def verifier_email(email: str) -> dict:
    """
    Verifie si une adresse email est valide et livrable.
    Affiche le detail de chaque etape dans les logs.

    Retourne :
        {
            "valide" : bool  -> True = utiliser (generer IA + envoyer Gmail)
            "existe" : bool  -> True = adresse probablement existante
            "raison" : str   -> explication detaillee du resultat
        }
    """

    email = email.strip().lower()
    log_header(email)

    def rejeter(raison: str) -> dict:
        log_footer(False, raison)
        return {"valide": False, "existe": False, "raison": raison}

    def accepter(raison: str) -> dict:
        log_footer(True, raison)
        return {"valide": True, "existe": True, "raison": raison}

    # -- ETAPE 1 : Syntaxe --------------------------------------------------
    try:
        valide = validate_email(email, check_deliverability=False)
        email  = valide.normalized
        log_step(1, "Syntax", True, f"Valid format -> {email}")
    except EmailNotValidError as e:
        log_step(1, "Syntax", False, str(e))
        log_skip_step(2, "Disposable list", "skipped")
        log_skip_step(3, "DNS / MX records", "skipped")
        log_skip_step(4, "Provider check", "skipped")
        log_skip_step(5, "Disify API", "skipped")
        return rejeter(f"syntaxe_invalide: {e}")

    domaine = email.split("@")[1]

    # -- ETAPE 2 : Liste statique GitHub ------------------------------------
    if domaine in DOMAINES_JETABLES:
        log_step(2, "Disposable list", False, f"{domaine} found in static blocklist (+100k domains)")
        log_skip_step(3, "DNS / MX records", "skipped — disposable detected early")
        log_skip_step(4, "Provider check", "skipped")
        log_skip_step(5, "Disify API", "skipped")
        return rejeter("jetable_liste_statique")

    log_step(2, "Disposable list", True, f"{domaine} not in static blocklist")

    # -- ETAPE 3 : DNS / MX records -----------------------------------------
    try:
        mx_records = dns.resolver.resolve(domaine, "MX", lifetime=DNS_TIMEOUT)
        serveurs   = sorted(
            [(r.preference, str(r.exchange).rstrip(".")) for r in mx_records]
        )
        serveur_mx = serveurs[0][1]
        log_step(3, "DNS / MX records", True, f"MX found -> {serveur_mx}")
    except dns.resolver.NXDOMAIN:
        log_step(3, "DNS / MX records", False, f"Domain {domaine} does not exist")
        log_skip_step(4, "Provider check", "skipped")
        log_skip_step(5, "Disify API", "skipped")
        return rejeter("domaine_inexistant")
    except dns.resolver.NoAnswer:
        log_step(3, "DNS / MX records", False, f"No MX records found for {domaine}")
        log_skip_step(4, "Provider check", "skipped")
        log_skip_step(5, "Disify API", "skipped")
        return rejeter("pas_de_mx")
    except dns.resolver.Timeout:
        log_step(3, "DNS / MX records", False, "DNS resolution timed out")
        log_skip_step(4, "Provider check", "skipped")
        log_skip_step(5, "Disify API", "skipped")
        return rejeter("timeout_dns")
    except Exception as e:
        log_step(3, "DNS / MX records", False, str(e))
        log_skip_step(4, "Provider check", "skipped")
        log_skip_step(5, "Disify API", "skipped")
        return rejeter(f"erreur_dns: {e}")

    # -- ETAPE 4 : Provider check -------------------------------------------
    # Detecte les grands providers de 2 facons :
    #   A) Par le domaine de l'email  : gmail.com, outlook.com...
    #   B) Par le serveur MX          : aspmx.l.google.com -> Google Workspace
    #                                   mail.protection.outlook.com -> Microsoft 365
    #                                   mx.zoho.com -> Zoho Mail
    mx_parts     = serveur_mx.split(".")
    mx_domaine   = ".".join(mx_parts[-2:]) if len(mx_parts) >= 2 else serveur_mx
    mx_domaine_3 = ".".join(mx_parts[-3:]) if len(mx_parts) >= 3 else mx_domaine

    est_grand_provider = (
        domaine    in GRANDS_PROVIDERS or
        mx_domaine in MX_PROVIDERS_FIABLES or
        mx_domaine_3 in MX_PROVIDERS_FIABLES
    )

    if est_grand_provider:
        if domaine in GRANDS_PROVIDERS:
            provider_label = f"{domaine} is a major provider"
        else:
            provider_label = f"hosted on {serveur_mx} (Google Workspace / Zoho / Microsoft 365)"
        log_step(4, "Provider check", True, f"{provider_label} — trusted infrastructure")

        jetable = verifier_jetable(email, domaine)
        if jetable["erreur"] is None:
            log_step(5, "Disposable APIs", not jetable["est_jetable"],
                     f"Disposable detected ({jetable['source']})" if jetable["est_jetable"]
                     else f"Not disposable ({jetable['source']})")
        else:
            log_skip_step(5, "Disposable APIs", f"unavailable ({jetable['erreur']})")

        if jetable["est_jetable"]:
            return rejeter("jetable_grand_provider")
        return accepter("grand_provider_mx_ok")

    log_skip_step(4, "Provider check", f"{domaine} is not a major provider (MX: {serveur_mx})")

    # -- ETAPE 5 : APIs jetables (Disify + Kickbox) -------------------------
    jetable = verifier_jetable(email, domaine)

    if jetable["erreur"] is None:
        if jetable["est_jetable"]:
            log_step(5, "Disposable APIs", False,
                     f"{domaine} flagged as disposable ({jetable['source']})")
            return rejeter("jetable_detecte")
        if not jetable["domaine_valide"]:
            log_step(5, "Disposable APIs", False,
                     f"{domaine} has no valid DNS according to APIs")
            return rejeter("domaine_invalide")
        log_step(5, "Disposable APIs", True,
                 f"Not disposable, DNS valid ({jetable['source']})")
        return accepter("apis_confirmed_valid")
    else:
        log_skip_step(5, "Disposable APIs", f"unavailable — trusting MX")
        return accepter("mx_ok_apis_unavailable")




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
    return resultat["valide"]


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

        # Invalide - pas de MX
        "hello@takpay.com",
    ]

    print(c("\n" + "═" * 65, "cyan"))
    print(c("  EMAIL VERIFICATION REPORT", "bold"))
    print(c("═" * 65, "cyan"))

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
    print(f"\n{c('═' * 65, 'cyan')}")
    print(c("  SUMMARY", "bold"))
    print(c("─" * 65, "cyan"))
    print(f"  {'Total checked':<25} {c(str(total), 'white')}")
    print(f"  {'Valid (processed)':<25} {c(str(valides), 'green')}")
    print(f"  {'Skipped (blocked)':<25} {c(str(skips), 'red')}")
    print(f"  {'Savings':<25} {c(str(round(skips / total * 100)) + '%', 'yellow')}  <- tokens + Gmail quota saved")
    print(c("═" * 65, "cyan") + "\n")