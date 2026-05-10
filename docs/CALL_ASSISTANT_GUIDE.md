# JARVIS Call Assistant — Complete Integration Guide

## Files Built

```
Android (Java):
  CallAssistantService.java    ← Core service: detect + answer + record + save
  JarvisAccessibilityService.java ← WhatsApp + Instagram auto-answer
  WishEngine.java              ← Real-time greetings (time/day/holiday)
  VoskEngine.java              ← Offline STT (no internet)
  Support.java                 ← JarvisTTS + CallLogDB + WindowsSync + CallRecord

Flutter (Dart):
  call_service.dart            ← Dart bridge + CallRecord model
  call_log_screen.dart         ← Full UI (inbox, audio playback, important popup)
  (call_settings_screen.dart)  ← Settings, message editor, wish preview

Backend (Python):
  call_sync_server.py          ← Windows TCP server + FastAPI routes
```

---

## Step 1 — Add Java files to Android

Copy all Java files to:
```
android/app/src/main/java/com/jarvis/app/
├── call/
│   ├── CallAssistantService.java
│   ├── JarvisTTS.java
│   └── Support.java          ← contains CallRecord + CallLogDB + WindowsSync
├── accessibility/
│   └── JarvisAccessibilityService.java
├── vosk/
│   └── VoskEngine.java
└── wishes/
    └── WishEngine.java
```

---

## Step 2 — Download Vosk Model (offline speech recognition)

```bash
# Download Indian English model (39MB, best for Indian callers)
wget https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip
unzip vosk-model-small-en-in-0.4.zip
# Rename folder to "vosk-model"
# Place in: android/app/src/main/assets/vosk-model/
```

---

## Step 3 — Add Vosk to build.gradle

```gradle
// android/app/build.gradle
dependencies {
    // ...existing...
    implementation 'com.alphacephei:vosk-android:0.3.47'
}
```

Also increase heap for model loading:
```gradle
android {
    defaultConfig {
        // ...
        javaCompileOptions {
            annotationProcessorOptions {
                arguments += ["room.schemaLocation": "$projectDir/schemas"]
            }
        }
    }
    dexOptions {
        javaMaxHeapSize "4g"
    }
}
```

---

## Step 4 — Add accessibility_service_config.xml

Create file: `android/app/src/main/res/xml/accessibility_service_config.xml`
(already provided)

Add to strings.xml:
```xml
<string name="accessibility_service_description">
    JARVIS Call Guard — Auto-answers calls and records messages when you are busy
</string>
```

---

## Step 5 — Update MainActivity.java

Add MethodChannel for call service control:

```java
// In MainActivity.java configureFlutterEngine(), add these cases:

case "startCallService":
    Intent cs = new Intent(this, CallAssistantService.class);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(cs);
    else startService(cs);
    result.success(true); break;

case "stopCallService":
    Intent cs2 = new Intent(this, CallAssistantService.class);
    cs2.setAction(CallAssistantService.ACTION_STOP);
    startService(cs2);
    result.success(true); break;

case "isCallServiceRunning":
    result.success(isServiceRunning(CallAssistantService.class)); break;

case "getAllCallRecords":
    CallLogDB db = new CallLogDB(this);
    List<CallRecord> all = db.getAll();
    List<Map<String,Object>> mapList = new ArrayList<>();
    for (CallRecord r : all) {
        Map<String,Object> m = new HashMap<>();
        m.put("id", r.id); m.put("caller_name", r.callerName);
        m.put("platform", r.platform); m.put("transcript", r.transcript);
        m.put("audio_path", r.audioPath); m.put("timestamp", r.timestamp);
        m.put("is_important", r.isImportant); m.put("is_read", r.isRead);
        mapList.add(m);
    }
    result.success(mapList); break;

case "markCallRead":
    int rid = (int) call.argument("id");
    new CallLogDB(this).markRead(rid);
    result.success(true); break;

case "deleteCallRecord":
    int did = (int) call.argument("id");
    new CallLogDB(this).deleteRecord(did);
    result.success(true); break;
```

---

## Step 6 — Add Call Log to Flutter app

In `home_screen.dart`, add to More tab:
```dart
import 'screens/call_log_screen.dart';
import 'services/call_service.dart';

// In _MoreTab:
_MoreItem(
  icon: Icons.call_outlined,
  label: 'Call Guard',
  sub: 'Auto-answer & record messages',
  screen: const CallLogScreen(),
),
_MoreItem(
  icon: Icons.settings_outlined,
  label: 'Call Settings',
  sub: 'Greeting, delay, platforms',
  screen: const CallSettingsScreen(),
),
```

Also check for important messages on app startup:
```dart
// In _HomeScreenState.initState():
_checkCallMessages();

Future<void> _checkCallMessages() async {
  final svc = CallService();
  final important = await svc.getImportant();
  if (important.isNotEmpty && mounted) {
    // Navigate to call log
    Navigator.push(context, MaterialPageRoute(builder: (_) => const CallLogScreen()));
  }
}
```

---

## Step 7 — Windows sync server

```bash
pip install plyer pyttsx3 --break-system-packages

# Run alongside your JARVIS backend:
python backend/call_server/call_sync_server.py

# Or add to main.py:
from call_server.call_sync_server import get_fastapi_router
app.include_router(get_fastapi_router())
```

---

## How the Greeting Works (Real-time)

Every call JARVIS checks:

| Time | Greeting |
|------|---------|
| 5am – 12pm | "Good morning" |
| 12pm – 5pm | "Good afternoon" |
| 5pm – 9pm  | "Good evening" |
| 9pm – 5am  | "Good night" |

| Day | Addition |
|-----|---------|
| Monday | "Hope you have a productive week" |
| Friday | "Happy Friday" |
| Saturday/Sunday | "Enjoy your weekend" |

| Date | Special wish |
|------|-------------|
| Jan 1 | "Happy New Year!" |
| Jan 26 | "Happy Republic Day!" |
| Aug 15 | "Happy Independence Day!" |
| Dec 25 | "Merry Christmas!" |
| Nov 1-5 | "Happy Diwali!" |
| Mar 24-26 | "Happy Holi!" |
| + more | Valentine's, Gandhi Jayanti, Halloween, New Year's Eve |

**Full example output:**
> *"Good evening, Rahul. Happy Diwali! Pavan sir is currently busy and cannot take your call right now. You may leave a note or a reminder after the beep, and he will get back to you as soon as possible."*

---

## Required Android Permissions (grant manually)

1. **ANSWER_PHONE_CALLS** — Settings → Apps → JARVIS → Permissions → Phone
2. **RECORD_AUDIO** — Settings → Apps → JARVIS → Permissions → Microphone
3. **READ_PHONE_STATE** — Settings → Apps → JARVIS → Permissions → Phone
4. **Accessibility** — Settings → Accessibility → JARVIS Call Guard → Enable
5. **Notification Access** — Settings → Notification Access → JARVIS → Enable
6. **Battery Optimization** — Settings → Battery → JARVIS → Unrestricted

---

## Apple-style Live Voicemail comparison

| Feature | Apple Live Voicemail | JARVIS Call Guard |
|---------|---------------------|-------------------|
| Auto-answer | ✓ | ✓ |
| Offline STT | ✓ (on-device) | ✓ (Vosk, on-device) |
| Live transcript | ✓ | ✓ (real-time partial) |
| Custom greeting | ✓ | ✓ + contextual wishes |
| WhatsApp support | ✗ | ✓ |
| Instagram support | ✗ | ✓ |
| Windows sync | ✗ | ✓ |
| AI keyword detection | ✗ | ✓ (marks important) |
| Works offline 100% | ✓ | ✓ |

---

## pubspec.yaml — add these

```yaml
dependencies:
  just_audio: ^0.9.36       # audio playback of recordings
```
