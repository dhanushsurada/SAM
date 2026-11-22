"""
SAM Apple iOS Package
"""

from connect.bridges.apple_ios.shortcuts_bridge import AppleIOSBridge, IOSShortcutRequest, IOSShortcutResponse
from connect.bridges.apple_ios.continuity import AppleContinuityManager

__all__ = ["AppleIOSBridge", "IOSShortcutRequest", "IOSShortcutResponse", "AppleContinuityManager"]
