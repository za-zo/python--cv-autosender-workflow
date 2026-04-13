"""Batch processing with summary."""

from email_verifier.logger import Logger
from email_verifier.verifier import EmailVerifier


class EmailRunner:
    def __init__(self):
        self.verifier = EmailVerifier()

    def run(self, emails: list):
        print(Logger.color("\n" + "═" * 65, "cyan"))
        print(Logger.color("  EMAIL VERIFICATION REPORT", "bold"))
        print(Logger.color("═" * 65, "cyan"))

        valid_count = 0
        skipped_count = 0

        for email in emails:
            if self.verifier.check(email):
                valid_count += 1
            else:
                skipped_count += 1

        Logger.summary(len(emails), valid_count, skipped_count)


if __name__ == "__main__":
    test_emails = [
        "contact@saastrail.com",
        "info@cloudeasy.io",
        "hola@dosmedia.es",
        "amine.belkeziz@upline.co.ma",
        "nachrane@krafteurope.com",
        "careers@gft.com",
        "alachkar@atento.ma",
        "bouchaib.nassef@oilibya.ma",
        "benhammou@mail.cbi.net.ma",
    ]

    runner = EmailRunner()
    runner.run(test_emails)