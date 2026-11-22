"""
SAM WhatsApp Interface — Pair a New Device

Generates a one-time WhatsApp pairing token and deep link:
https://wa.me/<bot_number>?text=/start%20<token>

Run this on the SAM host to pair an authorized phone number.
"""

import sys
import logging

logging.basicConfig(level=logging.WARNING)


def generate_whatsapp_pairing_link(phone_number: str = "") -> dict:
    from config.settings import Settings
    from connect.core.device_registry import DeviceRegistry

    settings = Settings()
    bot_phone = phone_number or getattr(settings, "whatsapp_phone_number", "") or ""
    # Clean phone number (strip spaces, +, hyphens)
    clean_bot = "".join(filter(str.isdigit, bot_phone))

    registry = DeviceRegistry()
    token = registry.create_pairing_token(channel="whatsapp")
    
    if clean_bot:
        deep_link = f"https://wa.me/{clean_bot}?text=/start%20{token}"
    else:
        deep_link = f"Send '/start {token}' to your SAM WhatsApp bot number."

    return {
        "channel": "whatsapp",
        "token": token,
        "deep_link": deep_link,
        "bot_phone": clean_bot or None
    }


def main():
    info = generate_whatsapp_pairing_link()
    print(f"\nWhatsApp Pairing Code (valid 10 minutes):\n  {info['token']}")
    print(f"\nPairing Link:\n  {info['deep_link']}\n")

    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(info['deep_link'])
        qr.make()
        qr.print_ascii(invert=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save("sam_whatsapp_pairing_qr.png")
        print("\nSaved QR to sam_whatsapp_pairing_qr.png — scan to open chat with prefilled token.\n")
    except ImportError:
        print("Tip: Install qrcode (pip install qrcode[pil]) to render ASCII QR in terminal.")


if __name__ == "__main__":
    main()
