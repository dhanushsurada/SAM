"""
SAM Interfaces — ways humans and services communicate WITH SAM.

    interfaces/web/       SAM Web Interface (phone browser client, static assets)
    interfaces/telegram/  Telegram bot channel
    interfaces/api/       Phone-task HTTP + SSE API

An interface receives a request, normalizes it into a SAM request, hands it
to SAM Core (Brain / ReactLoop) for execution, and formats the response for
its channel. Interfaces may depend on SAM Connect (interfaces/telegram/
depends on connect/core/device_registry.py for trust checks) but SAM Core
must never depend on a specific interface.
"""
