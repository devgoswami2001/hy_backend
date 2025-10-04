from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

def send_otp_email(user, otp_code):
    subject = 'Your OTP Code'
    message = f'Your OTP code is: {otp_code}. This code will expire in 10 minutes.'
    
    # Optional: Use HTML template
    html_message = render_to_string('emails/otp_email.html', {
        'user': user,
        'otp_code': otp_code
    })
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
