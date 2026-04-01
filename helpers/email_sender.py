import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(to, subject, body_html, smtp_email, smtp_password, attachment_path=None):
    """Send an HTML email with optional PDF attachment via SMTP."""
    msg = MIMEMultipart()
    msg["From"] = smtp_email
    msg["To"] = to
    msg["Subject"] = subject

    msg.attach(MIMEText(body_html, "html", "utf-8"))

    if attachment_path:
        with open(attachment_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", "attachment", filename="cv.pdf"
            )
            msg.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.send_message(msg)
