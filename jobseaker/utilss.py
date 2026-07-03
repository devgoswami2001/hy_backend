# payments/utils.py
import hashlib
from django.conf import settings

def generate_payu_hash(data):
    hash_string = (
        f"{settings.PAYU_MERCHANT_KEY}|{data['txnid']}|{data['amount']}|"
        f"{data['productinfo']}|{data['firstname']}|{data['email']}|||||||||||"
        f"{settings.PAYU_SALT}"
    )
    return hashlib.sha512(hash_string.encode()).hexdigest().lower()