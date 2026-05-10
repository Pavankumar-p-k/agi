# JARVIS — Copilot Drop-In Instructions
# Give this entire file to Copilot as one single prompt
# ============================================================

Read every file listed below FULLY before touching anything.
Then apply all changes in the exact order listed.
Do NOT skip any step. Do NOT refactor unrelated code.
Run flutter analyze after every file change.

FILES TO READ FIRST:
  lib/main.dart
  lib/services/feature_settings.dart
  lib/services/reply_agent.dart
  lib/ai/local_model.dart
  lib/db/local_db.dart
  lib/screens/settings_screen.dart
  android/app/src/main/AndroidManifest.xml

============================================================
STEP 1 — Replace lib/models/platform_type.dart (full replace)
Use the file I provided: platform_type.dart
============================================================

============================================================
STEP 2 — Replace lib/services/feature_settings.dart (full replace)
Use the file I provided: feature_settings.dart
============================================================

============================================================
STEP 3 — Create lib/ai/model_detector.dart (new file)
Use the file I provided: model_detector.dart
============================================================

============================================================
STEP 4 — Replace lib/ai/local_model.dart (full replace)
Use the file I provided: local_model.dart
============================================================

============================================================
STEP 5 — Create lib/ai/gemini_model.dart (new file)
Use the file I provided: gemini_model.dart
============================================================

============================================================
STEP 6 — Replace lib/ai/social_prompt_builder.dart (full replace)
Use the file I provided: social_prompt_builder.dart
============================================================

============================================================
STEP 7 — Replace lib/services/reply_agent.dart (full replace)
Use the file I provided: reply_agent.dart
============================================================

============================================================
STEP 8 — Add methods to lib/db/local_db.dart
Open local_db.dart. Find the class LocalDb { } body.
Add these 3 methods from local_db_additions.dart INSIDE the class:
  - getRecentMessages()
  - isReplySent()
  - markReplySent()
Also run the DB migration for missing columns (see comments in file).
Do NOT replace the whole file — only add these 3 methods.
============================================================

============================================================
STEP 9 — Replace lib/screens/settings_screen.dart (full replace)
Use the file I provided: settings_screen.dart
============================================================

============================================================
STEP 10 — Replace lib/main.dart (full replace)
Use the file I provided: main.dart
============================================================

============================================================
STEP 11 — DELETE these files entirely (Call Guard removed):
  lib/services/call_service.dart
  lib/screens/call_settings_screen.dart

Remove ALL references to CallService and call_settings_screen
from any file that imports them (home_screen.dart, main.dart,
any navigation file). Search the whole project for:
  import.*call_service
  import.*call_settings_screen
  CallService
  callGuardEnabled
  feature_call_guard
  startupCallGuard
  startup_call_guard
Remove every import, every usage, every setting key.
============================================================

============================================================
STEP 12 — Final verification checklist (confirm ALL true):
  [ ] _inFlightKeys Set exists in reply_agent.dart
  [ ] _inFlightKeys.contains(key) is FIRST check in _process()
  [ ] _inFlightKeys.remove(key) is in a finally block
  [ ] LocalDb.markReplySent() is called BEFORE _sendReply()
  [ ] _cleanReply() is called on every model response
  [ ] All 7 platforms have enable flags in feature_settings.dart
  [ ] ModelDetector.autoDetectAndSave() called in main.dart with .then()
  [ ] No import of call_service or call_settings_screen anywhere
  [ ] flutter analyze passes with zero errors
============================================================

============================================================
STEP 13 — Rebuild APK:
  flutter clean
  flutter build apk --release
============================================================
