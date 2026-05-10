# JARVIS Flutter App

This app is the desktop/mobile client for the JARVIS backend in this monorepo.

## What it needs

- Flutter installed and available on `PATH`
- Windows desktop support enabled if you run `-d windows`
- The Python backend running at `http://127.0.0.1:8000` by default

## Run directly

From the repo root:

```powershell
cd apps/jarvis_app
flutter pub get
flutter run -d windows --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=WS_URL=ws://127.0.0.1:8000/ws
```

Or use the root launcher:

```powershell
jarvis gui
```

## Common startup issues

### `jarvis gui` fails with `FileNotFoundError`

That usually means the launcher could not resolve Flutter from Windows `PATH`.
The root launcher now handles `flutter.bat` and `flutter.cmd`, but you should still verify Flutter itself with:

```powershell
flutter doctor
```

### The app starts but cannot talk to the backend

- Make sure the backend is running with `jarvis server`
- Confirm the API URL passed through `--dart-define`
- If using another machine or emulator, point `API_BASE_URL` to the reachable host IP

### Firebase errors

Generate or replace `lib/firebase_options.dart` using:

```powershell
flutterfire configure
```

## Related docs

- Root overview: `README.md`
- Command reference: `docs/COMMANDS.md`
- Flutter setup notes: `docs/FLUTTER_GUIDE.md`
