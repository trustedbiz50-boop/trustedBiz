"""
payments.py — TrustedBiz Payment System
════════════════════════════════════════
Currently: WhatsApp manual payment flow (working now)
Ready for: Dgateway API (plug in when you get the key)

HOW IT WORKS NOW:
1. User clicks "Upgrade" → goes to WhatsApp with payment instructions
2. They send money via MTN/Airtel MoMo to your number
3. They send screenshot or transaction ID on WhatsApp
4. You go to /admin → click "Set Premium" on their business
5. They get notified instantly

HOW IT WILL WORK WITH DGATEWAY:
1. User clicks "Upgrade" → payment page opens
2. They enter phone number → MTN/Airtel MoMo prompt sent
3. They confirm on their phone → payment verified automatically
4. Business upgraded to premium instantly — no manual work

TO ACTIVATE DGATEWAY:
  pip install requests
  Set environment variable: DGATEWAY_API_KEY=your_key_here
  Set environment variable: DGATEWAY_MERCHANT_ID=your_merchant_id
  Change USE_DGATEWAY = True below

PRICING:
  BASIC_MONTHLY  = 7500  UGX/month
  PROMAX_MONTHLY = 15000 UGX/month
"""

import os
import json
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, redirect, flash, session, render_template

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASIC_MONTHLY  = 7500    # UGX
PROMAX_MONTHLY = 15000   # UGX
ADMIN_WHATSAPP = os.environ.get("ADMIN_WHATSAPP", "256753187966")

# Set to True when you have Dgateway API key
USE_DGATEWAY       = False
DGATEWAY_API_KEY   = os.environ.get("DGATEWAY_API_KEY", "")
DGATEWAY_MERCHANT  = os.environ.get("DGATEWAY_MERCHANT_ID", "")
DGATEWAY_BASE_URL  = "https://api.dgateway.com/v1"  # Update with real URL when confirmed

payments_bp = Blueprint('payments', __name__)

# ── PLAN DEFINITIONS ──────────────────────────────────────────────────────────
PLANS = {
    "basic": {
        "name":        "Basic",
        "price":       BASIC_MONTHLY,
        "price_label": "UGX 7,500/month",
        "features": [
            "Real AI-generated website",
            "Shareable link (trustedbiz.com/your-name)",
            "WhatsApp contact button",
            "Google Maps directions",
            "Photo gallery",
            "Services & pricing section",
            "Customer reviews",
            "Listed in TrustedBiz directory",
        ]
    },
    "promax": {
        "name":        "Pro Max",
        "price":       PROMAX_MONTHLY,
        "price_label": "UGX 15,000/month",
        "features": [
            "Everything in Basic PLUS:",
            "AI Ad Creator — create event announcements",
            "Custom domain assistance",
            "Priority search placement",
            "Price Guard featured listing",
            "Multiple branches/campuses",
            "Up to 10 photos",
            "Advanced analytics",
        ]
    }
}

# ── MANUAL WHATSAPP PAYMENT (current system) ──────────────────────────────────
def get_whatsapp_payment_link(business_name, plan, user_name):
    """
    Generates a WhatsApp link with pre-filled payment instructions.
    This is the current working system — no API needed.
    """
    price = PLANS[plan]['price']
    plan_name = PLANS[plan]['name']
    msg = (
        f"Hello TrustedBiz! I want to upgrade to {plan_name} plan.\n\n"
        f"Business: {business_name}\n"
        f"Name: {user_name}\n"
        f"Plan: {plan_name} — UGX {price:,}/month\n\n"
        f"I will send UGX {price:,} via MTN MoMo/Airtel Money. "
        f"Please confirm your payment number."
    )
    encoded = msg.replace(' ', '%20').replace('\n', '%0A')
    return f"https://wa.me/{ADMIN_WHATSAPP}?text={encoded}"

# ── DGATEWAY INTEGRATION (ready, awaiting API key) ────────────────────────────
class DgatewayClient:
    """
    Dgateway payment client.
    Supports MTN Mobile Money and Airtel Money in Uganda.

    USAGE (when API key is ready):
      client = DgatewayClient()
      result = client.initiate_payment(
          phone="256700123456",
          amount=7500,
          currency="UGX",
          reference="TB-biz123-basic",
          description="TrustedBiz Basic Plan - 1 Month"
      )
      if result['success']:
          # Store result['transaction_id']
          # Poll verify_payment() or wait for webhook
    """

    def __init__(self):
        self.api_key  = DGATEWAY_API_KEY
        self.merchant = DGATEWAY_MERCHANT
        self.base_url = DGATEWAY_BASE_URL

    def initiate_payment(self, phone, amount, currency, reference, description):
        """
        Initiate MTN/Airtel MoMo payment request.
        Returns dict with success, transaction_id, message.
        """
        if not USE_DGATEWAY or not self.api_key:
            return {
                "success": False,
                "message": "Payment gateway not configured yet. Use WhatsApp payment.",
                "transaction_id": None
            }

        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type":  "application/json",
                "X-Merchant-ID": self.merchant,
            }
            payload = {
                "phone":       phone,
                "amount":      amount,
                "currency":    currency,
                "reference":   reference,
                "description": description,
                "callback_url": os.environ.get("APP_URL", "") + "/payments/webhook",
            }
            resp = requests.post(
                f"{self.base_url}/payments/initiate",
                json=payload, headers=headers, timeout=30
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "success":
                return {
                    "success":        True,
                    "transaction_id": data.get("transaction_id"),
                    "message":        "Payment prompt sent to your phone. Please confirm."
                }
            else:
                return {
                    "success": False,
                    "message": data.get("message", "Payment initiation failed."),
                    "transaction_id": None
                }
        except Exception as e:
            print(f"Dgateway error: {e}")
            return {"success": False, "message": str(e), "transaction_id": None}

    def verify_payment(self, transaction_id):
        """
        Check if a payment was completed.
        Returns dict with paid (bool), status, amount.
        """
        if not USE_DGATEWAY or not self.api_key:
            return {"paid": False, "status": "gateway_disabled"}

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.get(
                f"{self.base_url}/payments/{transaction_id}",
                headers=headers, timeout=15
            )
            data = resp.json()
            return {
                "paid":   data.get("status") == "completed",
                "status": data.get("status"),
                "amount": data.get("amount"),
            }
        except Exception as e:
            print(f"Dgateway verify error: {e}")
            return {"paid": False, "status": "error"}


# ── FLASK ROUTES ──────────────────────────────────────────────────────────────
@payments_bp.route('/upgrade/<int:biz_id>')
def upgrade_page(biz_id):
    """Show upgrade options for a business."""
    from app import get_current_user, db_fetchone, q
    user = get_current_user()
    if not user:
        return redirect(f'/login?next=/upgrade/{biz_id}')

    biz = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"),
                      (biz_id, user['id']))
    if not biz:
        flash("Business not found.")
        return redirect('/dashboard')

    # Generate WhatsApp links for both plans
    basic_link  = get_whatsapp_payment_link(biz['name'], 'basic',  user['name'])
    promax_link = get_whatsapp_payment_link(biz['name'], 'promax', user['name'])

    return render_template('upgrade.html',
        business=dict(biz),
        plans=PLANS,
        basic_link=basic_link,
        promax_link=promax_link,
        use_dgateway=USE_DGATEWAY,
        current_user=user)


@payments_bp.route('/upgrade/<int:biz_id>/pay', methods=['POST'])
def initiate_payment(biz_id):
    """
    Initiate Dgateway payment (when API key is ready).
    Currently returns WhatsApp fallback.
    """
    from app import get_current_user, db_fetchone, db_insert, q
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "message": "Login required"}), 401

    plan  = request.form.get('plan', 'basic')
    phone = request.form.get('phone', '').strip()
    biz   = db_fetchone(q("SELECT * FROM business WHERE id=? AND owner_id=?"),
                        (biz_id, user['id']))
    if not biz:
        return jsonify({"success": False, "message": "Business not found"}), 404

    amount    = PLANS.get(plan, PLANS['basic'])['price']
    reference = f"TB-{biz_id}-{plan}-{secrets.token_hex(4)}"

    if USE_DGATEWAY and phone:
        client = DgatewayClient()
        result = client.initiate_payment(
            phone=phone,
            amount=amount,
            currency="UGX",
            reference=reference,
            description=f"TrustedBiz {PLANS[plan]['name']} — {biz['name']}"
        )
        if result['success']:
            # Store pending transaction
            db_insert(q("""
                INSERT INTO payment_transactions
                  (business_id, user_id, plan, amount, reference, transaction_id, status)
                VALUES (?,?,?,?,?,?,'pending')
            """), (biz_id, user['id'], plan, amount, reference, result['transaction_id']))
        return jsonify(result)
    else:
        # Fallback — WhatsApp
        wa_link = get_whatsapp_payment_link(biz['name'], plan, user['name'])
        return jsonify({
            "success":    False,
            "whatsapp":   wa_link,
            "message":    "Please complete payment via WhatsApp."
        })


@payments_bp.route('/payments/webhook', methods=['POST'])
def payment_webhook():
    """
    Dgateway webhook — called automatically when payment completes.
    Upgrades the business instantly without admin action.
    """
    if not USE_DGATEWAY:
        return jsonify({"status": "gateway_disabled"}), 200

    try:
        data = request.get_json() or {}
        transaction_id = data.get('transaction_id')
        status         = data.get('status')
        reference      = data.get('reference', '')

        if status != 'completed' or not transaction_id:
            return jsonify({"status": "ignored"}), 200

        from app import db_fetchone, db_execute, db_insert, q
        # Find the pending transaction
        tx = db_fetchone(q("SELECT * FROM payment_transactions WHERE transaction_id=?"),
                         (transaction_id,))
        if not tx:
            return jsonify({"status": "tx_not_found"}), 200

        # Upgrade the business
        db_execute(q("""
            UPDATE business SET
              is_premium=1,
              last_payment_date=CURRENT_DATE,
              payment_months_late=0
            WHERE id=?
        """), (tx['business_id'],))

        # Update transaction status
        db_execute(q("UPDATE payment_transactions SET status='completed' WHERE transaction_id=?"),
                   (transaction_id,))

        # Notify owner
        db_insert(q("INSERT INTO notifications (user_id, message) VALUES (?,?)"),
                  (tx['user_id'],
                   f"✅ Payment received! Your business is now Premium. Your website is being generated."))

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@payments_bp.route('/payments/verify/<transaction_id>')
def verify_payment_status(transaction_id):
    """Poll endpoint — frontend checks if payment completed."""
    client = DgatewayClient()
    result = client.verify_payment(transaction_id)
    return jsonify(result)
