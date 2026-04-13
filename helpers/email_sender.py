import smtplib
import base64
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


def send_email(to, subject, body_html, from_email, smtp_user, smtp_password, smtp_server=None, smtp_port=None, attachment_path=None, sender_name=None):
    """Send an HTML email with optional PDF attachment via SMTP."""
    msg = MIMEMultipart()
    if sender_name:
        msg["From"] = formataddr((sender_name, from_email))
    else:
        msg["From"] = from_email
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

    host = smtp_server or DEFAULT_SMTP_HOST
    port = int(smtp_port) if smtp_port else DEFAULT_SMTP_PORT

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


def send_email_brevo_api(to, subject, body_html, api_key, sender_email, attachment_path=None, sender_name=None):
    """Send an email via Brevo API."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {
            "email": sender_email,
            "name": sender_name or sender_email,
        },
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": body_html
    }
    
    if attachment_path:
        with open(attachment_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
            payload["attachment"] = [
                {
                    "content": content,
                    "name": "cv.pdf"
                }
            ]
            
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def send_email_via_api(provider_name, to, subject, body_html, api_key, sender_email, attachment_path=None, sender_name=None):
    """Route API email sending based on provider name."""
    if provider_name.lower() == "brevo":
        return send_email_brevo_api(to, subject, body_html, api_key, sender_email, attachment_path, sender_name=sender_name)
    else:
        raise ValueError(f"Unsupported API email provider: {provider_name}")
