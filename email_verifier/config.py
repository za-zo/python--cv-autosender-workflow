"""
Configuration constants for the email verifier.
"""

from typing import Any


class Config:
    DNS_TIMEOUT = 5
    API_TIMEOUT = 6
    LIST_TIMEOUT = 10

    BLOCKLIST_SOURCES = [
        {
            "name": "disposable-email-domains (community)",
            "url": (
                "https://raw.githubusercontent.com/"
                "disposable-email-domains/disposable-email-domains/"
                "master/disposable_email_blocklist.conf"
            ),
            "format": "txt",
        },
        {
            "name": "disposable/disposable-email-domains (daily auto)",
            "url": (
                "https://raw.githubusercontent.com/"
                "disposable/disposable-email-domains/"
                "master/domains.txt"
            ),
            "format": "txt",
        },
        {
            "name": "ivolo/disposable-email-domains (Kickbox source)",
            "url": (
                "https://raw.githubusercontent.com/"
                "ivolo/disposable-email-domains/"
                "master/index.json"
            ),
            "format": "json",
        },
    ]

    FALLBACK_BLOCKLIST = {
        "mailinator.com", "guerrillamail.com", "temp-mail.org", "yopmail.com",
        "trashmail.com", "fakeinbox.com", "10minutemail.com", "maildrop.cc",
        "throwaway.email", "discard.email", "spamgourmet.com", "tempr.email",
        "mohmal.com", "tempinbox.com", "dispostable.com", "sharklasers.com",
        "dependity.com", "emailondeck.com", "drrieca.com", "hostelness.com",
    }

    MAJOR_PROVIDERS = {
        "gmail.com", "googlemail.com",
        "outlook.com", "hotmail.com", "live.com", "msn.com",
        "yahoo.com", "yahoo.fr", "yahoo.co.uk",
        "icloud.com", "me.com", "mac.com",
        "aol.com", "protonmail.com", "proton.me",
    }

    TRUSTED_MX_PROVIDERS = {
        "google.com",
        "googlemail.com",
        "outlook.com",
        "protection.outlook.com",
        "yahoodns.net",
        "zoho.com",
        "zoho.in",
        "zoho.eu",
        "mimecast.com",
        "pphosted.com",
    }
