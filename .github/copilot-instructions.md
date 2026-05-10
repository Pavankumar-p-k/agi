# JARVIS App — GitHub Copilot Master Instructions
# Save this as: .github/copilot-instructions.md
# Copilot reads this file automatically for every session.
# ============================================================


## PROJECT IDENTITY

This is JARVIS — a Flutter (Dart) Android app that auto-replies to
incoming messages on WhatsApp, SMS, Telegram, and Instagram using a
local AI model (Ollama) with a Gemini API fallback.

Key files:
- lib/services/reply_agent.dart       — core auto-reply pipeline
- lib/ai/social_prompt_builder.dart   — LLM prompt construction
- lib/ai/local_model.dart             — Ollama + Gemini API calls
- lib/db/local_db.dart                — SQLite via sqflite
- lib/services/feature_settings.dart  — SharedPreferences wrapper
- lib/models/models.dart              — InboxMessage and other models
- lib/screens/settings_screen.dart    — user-facing settings UI


## WHAT THIS APP DOES

- Listens to Android notifications via NotificationListenerService
- Intercepts incoming messages from social apps
- Generates a short, human-like reply using a local LLM
- Sends the reply back via Android RemoteInput notification action
- Stores all messages and reply state in a local SQLite database
- Uses Vosk for offline speech recognition
- Has a self-learning feedback loop in lib/ai/self_learning.dart


## ARCHITECTURE RULES — ALWAYS FOLLOW THESE

1. ReplyAgent is a singleton. Never instantiate it with `new ReplyAgent()`.
   Always use `ReplyAgent()` (factory constructor returns `_instance`).

2. The reply pipeline has a strict gate order. Never change this order:
   a. _inFlightKeys in-memory lock  (prevents OS duplicate notifications)
   b. LocalDb.isReplySent() DB check (survives app restarts)
   c. _isOnCooldown() per-sender cooldown check
   d. _isReplyable() message sanity check
   e. _generateReply() LLM call
   f. LocalDb.markReplySent() — ALWAYS before _sendReply(), never after
   g. _sendReply() platform dispatch

3. _buildDedupKey() MUST include the message timestamp.
   Format: '${platform}:${sender}:${timestamp_to_second}'
   Never use only sender+platform — different messages share the same key.

4. LocalDb.markReplySent() must always be called BEFORE the send.
   If the send fails, the DB record prevents infinite retry loops.
   This is intentional — do not reorder it.

5. _inFlightKeys must be released in a finally block.
   Never return early from the try block without the finally.

6. Never call _sendReply() or _generateReply() from outside ReplyAgent.
   All entry points go through handleIncomingMessage().


## DATABASE RULES

- Table: inbox_messages
- Key dedup columns: sender, platform, cache_key, text, timestamp
- reply_sent INTEGER DEFAULT 0 — 0 = not replied, 1 = replied
- Always use parameterised queries. Never string-interpolate SQL.
- getRecentMessages() returns rows oldest-first (reversed after DESC query)
- Schema migrations use ALTER TABLE, never DROP TABLE


## AI / LLM RULES

- Primary model: Ollama at the URL stored in FeatureSettings.getOllamaUrl()
  Default: http://127.0.0.1:11434
  Endpoint: POST /api/generate
  stream: false always

- Fallback model: Gemini 1.5 Flash via FeatureSettings.getGeminiApiKey()
  Only call Gemini if Ollama returns null or empty string.
  If API key is null, empty, or equals 'YOUR_ANDROID_API_KEY' — skip silently.

- num_predict / maxOutputTokens: 80 hard cap. Never raise this.
  Replies must be short. The model must not ramble.

- stop sequences always include: ['\n\n', 'Them:', 'Me:', '---']

- Ollama timeout: 15 seconds. Gemini timeout: 20 seconds.
  Never remove timeouts.

- After getting a raw model response, always call _cleanReply().
  Never send raw LLM output directly.


## PROMPT RULES (SocialPromptBuilder)

- Always include: persona name, platform name, tone guide, time hint
- Always include: last 6 conversation turns from DB as context
- Prompt must end with the reply on the last line, no other text after
- Never ask the model to introduce itself or explain itself
- Tone options: casual, friendly, formal, brief
  Read from FeatureSettings.getReplyTone(), default = 'casual'


## SETTINGS KEYS (SharedPreferences)

Use only these exact key strings — never create new ones without adding
them to feature_settings.dart:

  'auto_reply_enabled'     bool
  'reply_user_name'        String
  'reply_tone'             String  (casual/friendly/formal/brief)
  'ollama_url'             String
  'ollama_model'           String
  'gemini_api_key'         String
  'whatsapp_enabled'       bool
  'sms_enabled'            bool
  'telegram_enabled'      bool
  'instagram_enabled'      bool


## CODE STYLE

- Dart style: follow dart format defaults
- All debug output uses debugPrint(), never print()
- All log lines are prefixed: '[ClassName] message'
  Examples: '[ReplyAgent]', '[LocalModel]', '[SocialPromptBuilder]'
- All public methods have a one-line dartdoc comment
- Use const constructors wherever possible
- Prefer async/await over .then() chains
- All catch blocks: catch (e, stack) — always log stack for service classes
- No hardcoded strings outside of constants or feature_settings.dart


## FLUTTER / ANDROID RULES

- Min SDK: as defined in android/app/build.gradle — do not change it
- Target SDK: do not change without explicit instruction
- Never add new permissions to AndroidManifest.xml without asking first
- Never add new pub dependencies without checking pubspec.yaml first
  and confirming the package exists on pub.dev
- Always run flutter analyze after edits — fix all warnings, not just errors
- Release builds only: flutter build apk --release
  Never suggest debug builds for deployment


## WHAT COPILOT MUST NOT DO

- Do NOT reorder the 7-gate pipeline in reply_agent.dart
- Do NOT move markReplySent() to after _sendReply()
- Do NOT remove the _inFlightKeys finally block
- Do NOT remove or shorten the Ollama/Gemini timeouts
- Do NOT increase num_predict above 80 or maxOutputTokens above 80
- Do NOT add new SharedPreferences keys without updating feature_settings.dart
- Do NOT use print() — always debugPrint()
- Do NOT instantiate ReplyAgent with new — it is a singleton
- Do NOT add network permissions or new manifest entries silently
- Do NOT use string interpolation in SQL queries
- Do NOT call the LLM directly from UI widgets or screens
- Do NOT skip _cleanReply() and send raw model output
- Do NOT change the dedupKey format to remove the timestamp
- Do NOT drop or recreate tables during migrations
- Do NOT commit API keys or secrets into source files
- Do NOT use setState() in service classes
- Do NOT create new files without showing the full file path first


## BEFORE EVERY EDIT — COPILOT MUST

1. Read the full current file before making changes
2. Show the exact lines being replaced (old → new)
3. After edits, confirm: does the 7-gate order still hold?
4. Run flutter analyze and resolve all issues
5. If adding a new method: add a one-line dartdoc comment above it


## VERIFICATION CHECKLIST AFTER ANY reply_agent.dart EDIT

Copilot must confirm all 5 are true before finishing:

  [ ] _inFlightKeys.contains(key) is checked before any DB call
  [ ] _inFlightKeys is added before the try block begins
  [ ] _inFlightKeys.remove(key) is inside a finally block
  [ ] LocalDb.markReplySent() is called before _sendReply()
  [ ] _cleanReply() is called on every model response before sending


## SUGGESTED WORKFLOW FOR FEATURES

When asked to add a new feature:
1. Identify which existing file(s) need changing
2. Read those files fully first
3. Make the smallest possible change that achieves the goal
4. Do not refactor unrelated code in the same edit
5. Test with flutter analyze
6. Summarise exactly what changed and why BRO DO THESE ALL