from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string

def send_otp_email(user, otp_code):
    subject = "HyreSense OTP Verification"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    text_content = f"Your OTP is {otp_code}. It will expire in 10 minutes."

    html_content = render_to_string("emails/otp_email.html", {
        "user": user,
        "otp_code": otp_code,
    })

    try:
        msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        return True
    except Exception as e:
        print("GoDaddy SMTP Error:", e)
        return False
