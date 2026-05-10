# Background Wake Service — Integration Guide

## What Was Built

```
Android (Java):
  JarvisWakeService.java   ← Foreground service, always running, audio listener
  MainActivity.java        ← MethodChannel bridge Flutter ↔ Android
  BootReceiver.java        ← Auto-starts service after phone reboot

Flutter (Dart):
  wake_service.dart        ← Dart bridge to the Android service
  wake_settings_screen.dart ← Settings UI with on/off, battery guide
  wake_overlay.dart        ← Animated banner that drops down when triggered
```

---

## Step 1 — Copy Java Files

Copy the 3 Java files to your project:
```
android/app/src/main/java/com/jarvis/app/
├── JarvisWakeService.java    ← copy here
├── MainActivity.java         ← REPLACE existing MainActivity.java
└── BootReceiver.java         ← copy here
```

> ⚠️ Check your package name. If yours is different from `com.jarvis.app`,
> change the first line of each Java file: `package com.yourname.yourapp;`
> Find your package name in `android/app/build.gradle` → `applicationId`

---

## Step 2 — Replace AndroidManifest.xml

Replace `android/app/src/main/AndroidManifest.xml` with the provided file.

---

## Step 3 — Add Dart files to your project

```
lib/services/wake_service.dart
lib/screens/wake_settings_screen.dart
lib/widgets/wake_overlay.dart
```

---

## Step 4 — Register WakeService in main.dart

```dart
// lib/main.dart
import 'services/wake_service.dart';
import 'widgets/wake_overlay.dart';

MultiProvider(
  providers: [
    ChangeNotifierProvider(create: (_) => AuthService()),
    ChangeNotifierProvider(create: (_) => WebSocketService()),
    ChangeNotifierProvider(create: (_) => TalkBackService()),
    ChangeNotifierProvider(create: (_) => WakeService()),   // ← ADD THIS
    Provider(create: (_) => ApiService()),
  ],
  child: MaterialApp(
    home: const _AuthGate(),
  ),
)
```

---

## Step 5 — Initialize WakeService on login

In `home_screen.dart`, initialize and wire up the overlay:

```dart
// In _HomeScreenState.initState():
@override
void initState() {
  super.initState();
  _initWakeService();
}

Future<void> _initWakeService() async {
  final wake     = context.read<WakeService>();
  final talkback = context.read<TalkBackService>();

  await wake.initialize();
  await talkback.initialize();

  // Wire wake → talkback
  wake.onWakeDetected = () {
    talkback.startListening();
  };

  // Auto-start if was previously enabled
  final prefs = await SharedPreferences.getInstance();
  if (prefs.getBool('wake_service_enabled') ?? false) {
    await wake.start();
  }
}
```

---

## Step 6 — Wrap your app with the overlay

In `home_screen.dart`, wrap your Scaffold with `WakeOverlayWrapper`:

```dart
@override
Widget build(BuildContext context) {
  final wake     = context.read<WakeService>();
  final talkback = context.read<TalkBackService>();

  return WakeOverlayWrapper(          // ← WRAP HERE
    wakeService: wake,
    talkback: talkback,
    child: Scaffold(
      appBar: AppBar(...),
      body: ...,
      bottomNavigationBar: ...,
    ),
  );
}
```

---

## Step 7 — Add Wake Settings to your app

Add a button to navigate to `WakeSettingsScreen` (e.g. in the More tab):

```dart
_MoreItem(
  icon: Icons.hearing_outlined,
  label: 'Wake Service',
  sub: 'Background "Hey Jarvis" detection',
  screen: WakeSettingsScreen(
    wakeService: context.read<WakeService>(),
    talkback:    context.read<TalkBackService>(),
  ),
),
```

---

## Step 8 — Build and install

```bash
flutter build apk --release
# Transfer to phone and install
```

---

## For Production: Replace SimpleKeywordDetector with Porcupine

The included `SimpleKeywordDetector` uses basic energy detection.
For accurate "Hey Jarvis" recognition, replace it with **Porcupine**:

```bash
# 1. Sign up free at https://picovoice.ai
# 2. Download the "jarvis" wake word model (.ppn file)
# 3. Add to android/app/src/main/assets/jarvis_android.ppn
```

```java
// In JarvisWakeService.java, replace SimpleKeywordDetector with:
import ai.picovoice.porcupine.*;

Porcupine porcupine = new Porcupine.Builder()
    .setAccessKey("YOUR_PICOVOICE_ACCESS_KEY")
    .setKeywordPath("jarvis_android.ppn")
    .setSensitivity(0.7f)
    .build(getApplicationContext());

// In the audio loop:
int keyword = porcupine.process(frameBuffer);
if (keyword >= 0) {
    onWakeWordDetected();
}
```

Porcupine free tier: 3 months free, unlimited wake word detections.

---

## How Android Keeps It Alive

```
┌─────────────────────────────────┐
│   JarvisWakeService             │
│   (Foreground Service)          │
│                                 │
│  ┌──────────────────────────┐   │
│  │ Persistent Notification  │   │  ← Android won't kill services
│  │ "J.A.R.V.I.S — Online"  │   │    with visible notifications
│  └──────────────────────────┘   │
│                                 │
│  ┌──────────────────────────┐   │
│  │ PARTIAL_WAKE_LOCK        │   │  ← CPU stays on for audio
│  │ (CPU never sleeps)       │   │
│  └──────────────────────────┘   │
│                                 │
│  ┌──────────────────────────┐   │
│  │ AudioRecord thread       │   │  ← Mic always listening
│  │ 16kHz, 16-bit PCM        │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
         ↓ Wake word!
┌─────────────────────────────────┐
│  SCREEN_BRIGHT_WAKE_LOCK        │  ← Screen turns on
│  + ACQUIRE_CAUSES_WAKEUP        │
└─────────────────────────────────┘
         ↓
┌─────────────────────────────────┐
│  Broadcast → Flutter            │  ← App receives event
│  → WakeOverlay slides down      │  ← UI responds
│  → TalkBack starts listening    │  ← You speak
└─────────────────────────────────┘
```

---

## Battery Impact

| Setting | Battery drain |
|---|---|
| Wake service OFF | 0% |
| Wake service ON, idle | ~2–4% per day |
| Wake service ON, actively listening | ~5–8% per day |

The `PARTIAL_WAKE_LOCK` is the main battery user. This is comparable to
Google Assistant or Siri always-on mode.
