import razorpay

# Initialize Client
client = razorpay.Client(auth=("rzp_test_RkGZ4yTFws2GHU", "nMDuDlsTAbHDfZSo8fmNw4yx"))

def create_order(amount_in_rupees):
    """
    Create a Razorpay order.
    amount_in_rupees -> integer or float (example: 500.00)
    """
    
    # Convert rupees to paise
    amount = int(amount_in_rupees * 100)

    order_data = {
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1  # Auto-capture
    }

    try:
        order = client.order.create(order_data)
        return order  # Returns order_id, amount, status, etc.

    except Exception as e:
        print("Error while creating order:", e)
        return None


# --------------------------
# Example usage:
# --------------------------




def verify_payment(order_id, payment_id, signature):
    """
    Verify Razorpay signature after payment success.
    Returns True (valid) or False (invalid).
    """

    params = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }

    try:
        client.utility.verify_payment_signature(params)
        return True   # Signature matched → Payment is valid
    
    except razorpay.errors.SignatureVerificationError:
        return False  # Signature did NOT match → Invalid/Hacked
    
    except Exception as e:
        print("Verification error:", e)
        return False