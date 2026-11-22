"""
Offline unit & integration tests for Omnichannel Bridge Manager,
WhatsApp Bridge, Apple iOS Siri Shortcuts, and Device Fabric.
"""

import unittest
from unittest.mock import MagicMock, patch
from config.settings import Settings
from connect.core.device_registry import DeviceRegistry
from interfaces.whatsapp.whatsapp_bridge import WhatsAppBridge, format_for_whatsapp
from connect.bridges.apple_ios.shortcuts_bridge import AppleIOSBridge, IOSShortcutRequest
from connect.bridges.apple_ios.continuity import AppleContinuityManager
from connect.core.fabric import DeviceFabric
from connect.bridges.omnichannel_manager import OmnichannelBridgeManager


class DummySettings(Settings):
    telegram_bot_token = "dummy_telegram_token"
    telegram_bot_username = "sam_test_bot"
    whatsapp_phone_number_id = "1234567890"
    whatsapp_access_token = "dummy_wa_token"
    whatsapp_verify_token = "test_verify_token"
    primary_model = "qwen2.5:7b"
    incognito = False


class TestOmnichannelAndBridges(unittest.TestCase):

    def test_whatsapp_markdown_formatting(self):
        """Verify markdown conversion to native WhatsApp format."""
        orig = "This is **bold** and ~~strikethrough~~ and `code` with ```multiline code block```."
        formatted = format_for_whatsapp(orig)
        self.assertIn("*bold*", formatted)
        self.assertIn("~strikethrough~", formatted)
        self.assertIn("`code`", formatted)
        self.assertIn("```multiline code block```", formatted)

    def test_whatsapp_bridge_pairing_and_trust(self):
        """Verify pairing token generation, redemption, and trust lifecycle for WhatsApp."""
        import secrets
        settings = DummySettings()
        registry = DeviceRegistry()
        bridge = WhatsAppBridge(settings, registry=registry)
        bridge.send_message = MagicMock(return_value=True)

        sender_phone = f"+1555{secrets.randbelow(10000000):07d}"
        # 1. Untrusted sender receives pairing prompt
        resp = bridge.process_message(sender_phone, "hello sam")
        self.assertIn("not paired", resp.lower())
        self.assertFalse(registry.is_trusted(sender_phone, channel="whatsapp"))

        # 2. Generate token and redeem
        token = registry.create_pairing_token(channel="whatsapp")
        pair_resp = bridge.process_message(sender_phone, f"/start {token}", sender_name="John Doe")
        self.assertIn("successfully paired", pair_resp.lower())
        self.assertTrue(registry.is_trusted(sender_phone, channel="whatsapp"))

        # 3. Trusted sender can now chat and issue commands
        bridge.brain.process = MagicMock(return_value=MagicMock(text="I am ready.", action=None))
        chat_resp = bridge.process_message(sender_phone, "what is your status?")
        self.assertIn("I am ready.", chat_resp)

    def test_whatsapp_webhook_verification(self):
        """Verify Meta webhook challenge handshake."""
        settings = DummySettings()
        bridge = WhatsAppBridge(settings)

        # Valid challenge
        challenge = bridge.verify_webhook("subscribe", "test_verify_token", "challenge_12345")
        self.assertEqual(challenge, "challenge_12345")

        # Invalid token fails
        invalid = bridge.verify_webhook("subscribe", "wrong_token", "challenge_12345")
        self.assertIsNone(invalid)

    def test_apple_ios_siri_shortcut_execution(self):
        """Verify Apple iOS Siri shortcut execution with Tier 1 and standard execution."""
        settings = DummySettings()
        bridge = AppleIOSBridge(settings)

        # Tier 1 direct execution (e.g. greeting)
        req = IOSShortcutRequest(prompt="hello sam", voice_response=False, device_model="iPhone 16 Pro")
        res = bridge.handle_shortcut_request(req)
        self.assertTrue(res.success)
        self.assertTrue(any(word in res.spoken_text for word in ["Hello", "SAM", "Hey", "help"]))
        self.assertGreaterEqual(res.execution_time_ms, 0.0)

        # Siri shortcut definition generator
        definition = bridge.generate_apple_shortcut_definition("http://192.168.1.50:8420", auth_token="tok_123")
        self.assertEqual(definition["name"], "Ask SAM")
        self.assertIn("http://192.168.1.50:8420/api/ios/shortcut", definition["endpoint"])
        self.assertGreater(len(definition["instructions"]), 4)

    def test_apple_continuity_manager(self):
        """Verify Apple Continuity manager status report."""
        mgr = AppleContinuityManager()
        status = mgr.status()
        self.assertIn("platform", status)
        self.assertIn("continuity_services", status)
        self.assertIn("safari_handoff", status["continuity_services"])

    def test_device_fabric_topology_and_shared_clipboard(self):
        """Verify DeviceFabric manages mesh topology and cross-device shared clipboard."""
        registry = DeviceRegistry()
        fabric = DeviceFabric(registry=registry)

        # Topology
        topo = fabric.get_topology()
        self.assertGreaterEqual(topo["total_nodes"], 1)
        self.assertTrue(any(n["device_type"] == "desktop" for n in topo["nodes"]))

        # Shared Clipboard
        set_res = fabric.set_clipboard("Copied on Mac: http://github.com", source_device_id="desktop")
        self.assertTrue(set_res["synced"])

        clip = fabric.get_clipboard()
        self.assertEqual(clip["content"], "Copied on Mac: http://github.com")
        self.assertEqual(clip["source_device_id"], "desktop")

    def test_omnichannel_bridge_manager(self):
        """Verify OmnichannelBridgeManager coordinates all channels and generates pairing info."""
        settings = DummySettings()
        mgr = OmnichannelBridgeManager(settings=settings)

        status = mgr.get_status()
        self.assertIn("channels", status)
        self.assertIn("telegram", status["channels"])
        self.assertIn("whatsapp", status["channels"])
        self.assertIn("apple_ios", status["channels"])
        self.assertIn("android", status["channels"])

        # Pairing info generation
        tg_pair = mgr.generate_pairing_info("telegram")
        self.assertEqual(tg_pair["channel"], "telegram")
        self.assertIn("token", tg_pair)
        self.assertIn("deep_link", tg_pair)

        wa_pair = mgr.generate_pairing_info("whatsapp")
        self.assertEqual(wa_pair["channel"], "whatsapp")
        self.assertIn("token", wa_pair)

        ios_pair = mgr.generate_pairing_info("apple_ios")
        self.assertEqual(ios_pair["channel"], "apple_ios")
        self.assertIn("shortcut_def", ios_pair)


if __name__ == "__main__":
    unittest.main()

