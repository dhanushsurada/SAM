# SAM Mobile Companion & Omnichannel Setup Guide

> **Command SAM on your Mac from anywhere via WhatsApp, Telegram, Android Companion, and iPhone Siri.**

---

## 1. Overview & Capabilities

SAM is engineered as a **sovereign, local-first assistant** that extends beyond your desk. Using the Omnichannel Bridge Fabric and Connect protocol, SAM accepts real-time tasks, questions, and system commands from your mobile devices, executes them on your Mac (or on the phone itself), and returns immediate answers, screenshots, and audio.

```
                    ┌────────────────────────────────────────────────────────┐
                    │                      SAM CORE                          │
                    │   Brain (Ollama/LLMs) · ReactLoop · Hands · Vision     │
                    │                REST API :8420                          │
                    └────────────────────────────────────────────────────────┘
                                     ▲    ▲    ▲    ▲
            ┌────────────────────────┘    │    │    └────────────────────────┐
            │                             │    │                             │
    Meta Cloud API                 Long-Polling│   Local Wi-Fi / USB      iOS Shortcuts
            ▼                             ▼    │           ▼                 ▼
   ┌─────────────────┐           ┌─────────────┴───┐ ┌───────────────┐ ┌───────────────┐
   │    WhatsApp     │           │    Telegram     │ │  SAM Android  │ │  iPhone Siri  │
   │  (Any phone)    │           │   (Any phone)   │ │ Companion App │ │ Action Button │
   └─────────────────┘           └─────────────────┘ └───────────────┘ └───────────────┘
```

---

## 2. Channel 1: WhatsApp Mobile Bridge

### How It Works
Messages sent to your WhatsApp bot number trigger a webhook callback to SAM Core (`/api/bridges/whatsapp/webhook`). SAM verifies the sender's phone number against its trusted device database (`~/.sam_data/ecosystem/devices.db`), executes the requested action, and sends the response back via the WhatsApp Cloud API.

### Setup Steps (2 Minutes)

1. **Get Meta Cloud API Credentials:**
   - Log into the [Meta for Developers Portal](https://developers.facebook.com/).
   - Create a free App &rarr; Select **Other** &rarr; **Business** &rarr; Add the **WhatsApp** product.
   - Navigate to **WhatsApp &rarr; API Setup**:
     - Copy your **Phone Number ID** (e.g. `102938475610293`).
     - Generate a **Permanent System User Access Token** in Meta Business Settings (with `whatsapp_business_messaging` permission).

2. **Configure SAM:**
   - Add the credentials to `config/settings.yaml` (or export as environment variables):
     ```yaml
     whatsapp_phone_number_id: "102938475610293"
     whatsapp_access_token: "EAAB..."
     whatsapp_verify_token: "sam_whatsapp_verify_token"
     whatsapp_phone_number: "+15551234567"
     ```
   - Alternatively, add them to your `.env` file:
     ```bash
     WHATSAPP_PHONE_NUMBER_ID="102938475610293"
     WHATSAPP_ACCESS_TOKEN="EAAB..."
     WHATSAPP_VERIFY_TOKEN="sam_whatsapp_verify_token"
     ```

3. **Configure Webhook in Meta Dashboard:**
   - In WhatsApp &rarr; Configuration &rarr; Webhook:
     - **Callback URL:** `http://<your-public-ip-or-tunnel>:8420/api/bridges/whatsapp/webhook`
     - **Verify Token:** `sam_whatsapp_verify_token`
   - Subscribe to the `messages` field.

4. **Pair Your Phone Number:**
   - In SAM Desktop &rarr; **Connect** tab &rarr; **WhatsApp Bridge**, click **"Pair WhatsApp"**.
   - SAM will generate a 10-minute pairing token (e.g. `WA-8A3F9B`).
   - From your phone's WhatsApp, send:
     ```text
     /start WA-8A3F9B
     ```
   - SAM will reply: `✅ Successfully paired! You can now send instructions directly to SAM.`

### Example WhatsApp Commands
- `"Open Safari and summarize latest news on autonomous agents"`
- `"Take a screenshot of my Mac screen and tell me what is open"`
- `"What's on my plate today?"` (Triggers morning briefing & calendar reflex)
- `"Run pytest in ~/Projects/SAM and report failing tests"`
- `/status` — View model, uptime, and system health
- `/devices` — View all paired devices

---

## 3. Channel 2: Telegram Companion Bot

### How It Works
The Telegram Bridge uses **outbound long-polling**. This means **zero port forwarding, zero webhook URLs, and zero router configuration** are needed. It works behind firewalls and NATs.

### Setup Steps (1 Minute)

1. **Create Bot with BotFather:**
   - In Telegram on your phone or computer, message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`.
   - Choose a display name (e.g. `My SAM Assistant`) and username (e.g. `my_sam_agent_bot`).
   - Copy the HTTP API token provided by BotFather (e.g. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).

2. **Configure SAM:**
   - In `config/settings.yaml`:
     ```yaml
     telegram_bot_token: "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
     telegram_bot_username: "my_sam_agent_bot"
     ```
   - Or set in your shell:
     ```bash
     export TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
     ```

3. **Pair Your Telegram Account:**
   - Open SAM Desktop &rarr; **Connect** tab &rarr; **Telegram Bot**.
   - Click **"Pair Telegram"**.
   - Click the **"Open in Telegram"** button or open the link `https://t.me/my_sam_agent_bot?start=<TOKEN>`.
   - Tap **Start** in Telegram. SAM verifies your unique Telegram `chat_id` and binds your account.

### Example Telegram Commands
- `"Check git status in ~/Projects/SAM and summarize recent commits"`
- `"Lock my Mac screen"`
- `"Check CPU temperature and RAM usage"`
- `"Draft an email to client about project milestone"`
- `/devices` — View trusted devices
- `/status` — View live system status

---

## 4. Channel 3: SAM Android Companion App

### How It Works
The SAM Android companion client (`sam-android/`) is a native Android application (Kotlin · Jetpack Compose · Android 8.0+ / API 26+) that acts as an authenticated execution node in SAM's device fabric.

It features:
- **Asymmetric Ed25519 Keypair Authentication:** Private keys are secured in Android Keystore.
- **Bi-directional Task Routing:** You can command your Mac from the phone, and SAM on your Mac can dispatch mobile actions to your phone.
- **Accessibility Automation:** SAM can launch mobile apps, tap buttons, and type text.
- **Notification Listener:** SAM reads incoming mobile notifications and summarizes them on Desktop.
- **Scoped Storage File Sync:** Direct file transfer with SHA-256 integrity checks.

### Building & Installing the Android App

1. **Open in Android Studio:**
   - Launch **Android Studio Ladybug (2024.2+)** or newer.
   - Open the directory `sam-android/`.
   - Ensure **JDK 17** is configured in Project Structure.

2. **Build Debug APK via CLI (Alternative):**
   ```bash
   cd sam-android
   ./gradlew assembleDebug
   ```
   The APK will be generated at:
   `sam-android/app/build/outputs/apk/debug/app-debug.apk`

3. **Install on Phone:**
   - Connect phone via USB with USB Debugging enabled, then run:
     ```bash
     adb install sam-android/app/build/outputs/apk/debug/app-debug.apk
     ```
   - Or copy the APK to your phone and install it using your file manager.

### Pairing the Android App

1. **Network Setup:**
   - **Wi-Fi:** Connect both Mac and Android phone to the same local Wi-Fi router.
   - **USB Cable (Zero Latency / Bypasses Hotel Firewalls):**
     Connect phone via USB and run on your Mac:
     ```bash
     adb reverse tcp:8420 tcp:8420
     ```

2. **Generate Token on Mac:**
   - Open SAM Desktop &rarr; **Connect** &rarr; **Android / Wi-Fi**.
   - Click **"Generate Pairing Key"**. Note the Server Address (e.g. `http://192.168.1.50:8420`) and Token.

3. **Redeem Token in App:**
   - Open SAM on your phone &rarr; tap **"Pair with SAM Core"**.
   - Enter Server Address (`http://192.168.1.50:8420`, or `http://127.0.0.1:8420` if using USB).
   - Paste the Pairing Code and tap **Pair**.

4. **Grant Android Permissions:**
   - **Notification Access:** Allows SAM to summarize mobile notifications on Desktop.
   - **Accessibility Service:** Allows SAM to click buttons and automate mobile apps.

---

## 5. Channel 4: Apple iPhone Siri & Action Button Companion

### How It Works
Allows triggering SAM directly from iPhone 15/16 Pro Action Button, Siri voice (`"Hey Siri, ask SAM..."`), and returns spoken audio to AirPods via local REST API streaming.

### Setup (1 Minute)
1. In SAM Desktop &rarr; **Connect** tab &rarr; **Apple iOS & Siri**.
2. Click **"Generate Shortcut Setup"**.
3. Import the generated Shortcut into your iPhone Shortcuts app.
4. Assign the Shortcut to your **Action Button** in iOS Settings &rarr; Action Button.

---

## 6. Remote Command Reference Cheat Sheet

| Category | Example Command | Execution Target |
|:---|:---|:---|
| **System & Desktop** | `"Take a screenshot of my Mac"` | Hands (ScreenCapture) |
| **System & Desktop** | `"Lock my Mac screen"` | Mac System / Lock |
| **Web Research** | `"Open Safari and search for Quantum AI papers"` | Browser Automation |
| **Productivity** | `"What's on my plate today?"` | JEV Morning Briefing / Notes |
| **Productivity** | `"Note down idea: Launch decentralized storage bridge"` | Notes Vault |
| **Developer / CLI** | `"Run git status in ~/Projects/SAM and report diff"` | Terminal Runner |
| **Developer / CLI** | `"Check test suite status"` | Pytest Execution |
| **Mobile Actions** | `"Launch WhatsApp on my phone"` | Android App Launcher |
| **Mobile Actions** | `"Read my unread mobile notifications"` | Android Notification Listener |
| **Bot Commands** | `/status`, `/devices`, `/health` | Core Gateway Diagnostics |

---

## 7. Troubleshooting & FAQs

### Q: Why does my phone say "Connection Refused"?
- **Cause:** macOS Application Firewall is blocking port 8420.
- **Fix:** Go to **System Settings &rarr; Network &rarr; Firewall &rarr; Options**, and set SAM to "Allow incoming connections".
- **Alternative:** Connect your phone via USB cable and run `adb reverse tcp:8420 tcp:8420`. In the app, connect to `http://127.0.0.1:8420`.

### Q: Can someone else control my Mac if they message my Telegram or WhatsApp bot?
- **No.** SAM operates on a strict **fail-closed trust registry** (`~/.sam_data/ecosystem/devices.db`).
- Only device IDs / phone numbers paired using a valid, one-time token generated from your desktop app are authorized. All unauthorized messages are immediately rejected.
