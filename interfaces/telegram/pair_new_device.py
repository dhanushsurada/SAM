"""
SAM Telegram Interface — Pair a New Device

(Moved here in Phase 3A.5 — originated as ecosystem/pair_new_device.py.
This is a Telegram-specific pairing utility (t.me deep links), so it lives
under interfaces/telegram/ rather than connect/, even though it uses
connect/core/device_registry.py underneath. ecosystem/pair_new_device.py
now forwards here; there is only one implementation.)

Run this on the laptop to generate a one-time pairing QR code. Scanning it
opens Telegram directly to your SAM bot with the pairing token pre-filled
(via a t.me deep link), so pairing is a single scan-and-tap on the phone
side — no manual code typing needed.

Usage:
    python -m interfaces.telegram.pair_new_device

(`python -m ecosystem.pair_new_device` still works too — ecosystem/ is now
a compatibility shim forwarding here.)
"""

import sys
import logging

logging.basicConfig(level=logging.WARNING)  # keep terminal output clean for the QR


def main():
    from config.settings import Settings
    from connect.core.device_registry import DeviceRegistry

    settings = Settings()
    bot_username = getattr(settings, "telegram_bot_username", "") or ""

    if not bot_username:
        print(
            "\nsettings.telegram_bot_username isn't set. Add it to settings.yaml "
            "(the @username of the bot you created with @BotFather, without the @).\n"
        )
        sys.exit(1)

    registry = DeviceRegistry()
    token = registry.create_pairing_token(channel="telegram")
    deep_link = f"https://t.me/{bot_username}?start={token}"

    print(f"\nPairing link (valid 10 minutes):\n  {deep_link}\n")

    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(deep_link)
        qr.make()

        # ASCII in the terminal — no image viewer needed, works over SSH/Termux too
        qr.print_ascii(invert=True)

        # Also save a PNG for anyone who'd rather scan from a screen/photo
        img = qr.make_image(fill_color="black", back_color="white")
        out_path = "sam_pairing_qr.png"
        img.save(out_path)
        print(f"\nAlso saved as {out_path} — open it and scan with your phone's camera.")
        print("Scanning opens Telegram and sends the pairing code automatically.\n")

    except ImportError:
        print("qrcode package not installed — run: pip install qrcode[pil]")
        print(f"You can still pair manually: open Telegram, message @{bot_username}, "
              f"and send:\n  /start {token}\n")


if __name__ == "__main__":
    main()
