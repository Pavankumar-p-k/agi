# TalkBack Feature — Integration Guide

## New packages to add in pubspec.yaml

```yaml
dependencies:
  # Add these to your existing pubspec.yaml
  speech_to_text: ^6.6.0      # Microphone → text (works offline)
  flutter_tts: ^4.0.2         # Text → voice (on-device, no internet)
```

Run: `flutter pub get`

---

## Files Added

```
lib/
├── services/
│   └── talkback_service.dart    ← Core engine (STT + TTS + wake word)
├── widgets/
│   └── talkback_button.dart     ← Mic button + wave visualizer + transcript bubble
└── screens/
    └── talkback_screen.dart     ← Full-screen TalkBack UI
```

---

## Step 1 — Register TalkBackService as a Provider

In your `main.dart`, add TalkBackService to MultiProvider:

```dart
// lib/main.dart
import 'services/talkback_service.dart';

MultiProvider(
  providers: [
    ChangeNotifierProvider(create: (_) => AuthService()),
    ChangeNotifierProvider(create: (_) => WebSocketService()),
    ChangeNotifierProvider(create: (_) => TalkBackService()),  // ← ADD THIS
    Provider(create: (_) => ApiService()),
  ],
  child: MaterialApp(...),
)
```

---

## Step 2 — Add TalkBack button to Home Screen

In your `home_screen.dart` dashboard, you can add a quick-access button:

```dart
// In _DashboardTab build(), add to quick action grid:
_QuickTile(
  icon: Icons.mic_outlined,
  label: 'VOICE',
  color: JarvisColors.cyan,
  onTap: () => Navigator.push(context,
    MaterialPageRoute(builder: (_) => const TalkBackScreen())),
),
```

---

## Step 3 — Add TalkBack to Bottom Navigation (optional)

Replace one of the bottom nav items in `home_screen.dart`:

```dart
// In HomeScreen._screens list:
final _screens = const [
  _DashboardTab(),
  ChatScreen(),
  TalkBackScreen(),   // ← REPLACE RemindersScreen or add as new tab
  NotesScreen(),
  _MoreTab(),
];

// In BottomNavigationBar items:
BottomNavigationBarItem(
  icon: Icon(Icons.mic_outlined),
  label: 'VOICE',
),
```

---

## Step 4 — Embed Mic Button inside Chat Screen (optional)

You can embed the mic button directly in `chat_screen.dart` for hands-free chatting:

```dart
// In chat_screen.dart, import talkback:
import '../services/talkback_service.dart';
import '../widgets/talkback_button.dart';

// In _ChatScreenState, get talkback service:
late TalkBackService _talkback;

@override
void initState() {
  super.initState();
  _talkback = context.read<TalkBackService>();

  // Wire speech to chat
  _talkback.onUserSpeech = (text) async {
    _textCtrl.text = text;
    await _send();
  };
}

// In build(), add mic button next to send button:
Row(children: [
  Expanded(child: TextFormField(...)),

  // Mic button
  const SizedBox(width: 8),
  GestureDetector(
    onTap: () {
      if (_talkback.isListening) {
        _talkback.stopListening();
      } else {
        _talkback.startListening();
      }
    },
    child: AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _talkback.isListening
            ? JarvisColors.cyan.withOpacity(0.2)
            : JarvisColors.bgPanel,
        border: Border.all(
          color: _talkback.isListening
              ? JarvisColors.cyan
              : JarvisColors.border,
        ),
      ),
      child: Icon(
        _talkback.isListening ? Icons.mic : Icons.mic_none_outlined,
        color: _talkback.isListening ? JarvisColors.cyan : JarvisColors.textSecondary,
        size: 20,
      ),
    ),
  ),

  // Send button
  const SizedBox(width: 8),
  GestureDetector(onTap: _send, child: ...),
]),
```

---

## Step 5 — Make JARVIS speak responses automatically

In `chat_screen.dart`, after receiving AI response, call speak:

```dart
// In _send() method, after receiving response:
final result = await _api.chat(text);
final response = result['response'] as String;

setState(() {
  _messages.add(ChatMessage(role: 'assistant', message: response));
});

// ← Add this line to speak every AI response:
await context.read<TalkBackService>().respondWithSpeech(response);
```

---

## Android Permissions (already in AndroidManifest.xml)

```xml
<!-- Already added in your AndroidManifest.xml -->
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
```

---

## How TalkBack Works (flow)

```
User taps mic
    ↓
STT starts recording (on-device, offline)
    ↓
Live transcript shown on screen
    ↓
User stops speaking (auto-detected after 3s silence)
    ↓
Text sent to JARVIS Python backend via HTTP
    ↓
AI response received
    ↓
TTS reads response aloud (on-device voice)
    ↓
[Continuous Mode: auto-starts listening again]
[Wake Word Mode:  waits for "Hey Jarvis"]
```

---

## TalkBack Modes

| Mode | How it works |
|------|-------------|
| **Manual** | Tap mic to start, tap again to stop |
| **Continuous** | Auto-listens after every response — hands-free |
| **Wake Word** | Always listening in background, activates on "Hey Jarvis" |

---

## Voice Customization

Users can adjust in the settings sheet (⚙ button):
- **Volume** — how loud JARVIS speaks
- **Speech Rate** — slow / normal / fast
- **Voice Pitch** — low / normal / high

---

## Troubleshooting

**Microphone permission denied** → Go to Settings → Apps → JARVIS → Permissions → Microphone → Allow

**Speech not recognized** → Check device language matches `_language = 'en-US'` in talkback_service.dart

**TTS not speaking** → Call `talkback.testVoice()` to check if TTS engine works

**Continuous mode drains battery** → Use Wake Word mode instead — listens only for the trigger phrase
