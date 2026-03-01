# Android Receiver Spec (ADB + Bridge)

This package defines the Android side contract for backend bridge actions.

## Actions

- `com.jarvis.TTS`
  - extras: `text` (string)
- `com.jarvis.ANSWER_CALL_TTS`
  - extras: `caller` (string, optional), `script` (string)
- `com.jarvis.SEND_MESSAGE`
  - extras: `contact` (string), `text` (string), `platform` (string: `sms` or `auto`)

## Required permissions

- `android.permission.RECEIVE_BOOT_COMPLETED`
- `android.permission.FOREGROUND_SERVICE`
- `android.permission.POST_NOTIFICATIONS` (Android 13+)
- `android.permission.SEND_SMS` (for direct SMS send)
- `android.permission.ANSWER_PHONE_CALLS` (for call answer)
- `android.permission.READ_PHONE_STATE`
- `android.permission.CALL_PHONE` (device dependent if placing/handling calls)

Some OEM ROMs also require:
- Auto-start enabled
- Battery optimization disabled for app
- Notification permission approved

## Files

- `JarvisBridgeReceiver.kt`: receives broadcasts and forwards actions to service
- `JarvisActionService.kt`: executes TTS, SMS send, and call answer logic
- `AndroidManifest.snippet.xml`: merge into app manifest

## ADB tests

```bash
adb shell am broadcast -a com.jarvis.TTS --es text "Jarvis test speech"
adb shell am broadcast -a com.jarvis.ANSWER_CALL_TTS --es caller "Mom" --es script "Sir is busy right now"
adb shell am broadcast -a com.jarvis.SEND_MESSAGE --es contact "9999999999" --es text "I will call back soon" --es platform "sms"
```

## Notes

- Automatic call answer is heavily restricted on some Android versions/vendors.
- If `TelecomManager.acceptRingingCall()` fails, fallback behavior uses TTS and logs error.
- Direct send to WhatsApp/Instagram/etc is not guaranteed without official APIs and user interaction.
