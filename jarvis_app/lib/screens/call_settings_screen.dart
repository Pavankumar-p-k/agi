import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:permission_handler/permission_handler.dart';

import '../services/call_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class CallSettingsScreen extends StatefulWidget {
  const CallSettingsScreen({super.key});

  @override
  State<CallSettingsScreen> createState() => _CallSettingsScreenState();
}

class _CallSettingsScreenState extends State<CallSettingsScreen> {
  final CallService _callService = CallService();
  final TextEditingController _messageCtrl = TextEditingController(
    text:
        'Pavan is currently busy and cannot take your call right now. Please leave a note after the beep.',
  );
  final TextEditingController _pcIpCtrl =
      TextEditingController(text: '192.168.1.100');

  bool _serviceOn = false;
  bool _autoStart = false;
  double _delaySeconds = 4;
  bool _saving = false;
  bool _grantingAll = false;

  bool _runtimePermissionsGranted = false;
  bool _accessibilityEnabled = false;
  bool _notificationAccessEnabled = false;

  List<Permission> get _runtimePermissions => <Permission>[
        Permission.phone,
        Permission.microphone,
        Permission.notification,
        Permission.contacts,
      ];

  @override
  void initState() {
    super.initState();
    _loadState();
  }

  @override
  void dispose() {
    _messageCtrl.dispose();
    _pcIpCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadState() async {
    try {
      final results = await Future.wait<dynamic>([
        _callService.isRunning(),
        _callService.getAutoStart(),
        _callService.getCustomMessage(),
        _callService.getAnswerDelayMs(),
        _callService.getPcIp(),
      ]);
      if (!mounted) return;

      setState(() {
        _serviceOn = results[0] as bool;
        _autoStart = results[1] as bool;
        _messageCtrl.text = (results[2] as String).trim().isEmpty
            ? _messageCtrl.text
            : results[2] as String;
        final delayMs = (results[3] as int).clamp(2000, 10000);
        _delaySeconds = delayMs / 1000.0;
        _pcIpCtrl.text = (results[4] as String).trim().isEmpty
            ? _pcIpCtrl.text
            : results[4] as String;
      });

      await _refreshAutomationStatus();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not load call settings.')),
      );
    }
  }

  Future<void> _toggleService() async {
    if (!_serviceOn) {
      final ok = await _ensurePermissions();
      if (!ok) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Grant runtime permissions, Accessibility, and Notification access for full automation.',
            ),
          ),
        );
        return;
      }
    }

    setState(() => _saving = true);
    try {
      if (_serviceOn) {
        await _callService.stopService();
      } else {
        await _callService.startService();
      }
      await _loadState();
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<bool> _hasRuntimePermissions() async {
    final statuses = await Future.wait(
      _runtimePermissions.map((p) => p.status),
    );
    return statuses.every((s) => s.isGranted || s.isLimited);
  }

  Future<bool> _requestRuntimePermissions() async {
    final statuses = await _runtimePermissions.request();
    return statuses.values.every((s) => s.isGranted || s.isLimited);
  }

  Future<void> _refreshAutomationStatus() async {
    final runtimeOk = await _hasRuntimePermissions();

    bool accessibility = false;
    bool notificationAccess = false;
    try {
      accessibility = await _callService.isAccessibilityServiceEnabled();
      notificationAccess = await _callService.isNotificationAccessEnabled();
    } catch (_) {}

    if (!mounted) return;
    setState(() {
      _runtimePermissionsGranted = runtimeOk;
      _accessibilityEnabled = accessibility;
      _notificationAccessEnabled = notificationAccess;
    });
  }

  Future<void> _grantAllAutomationAccess() async {
    if (_grantingAll) return;
    setState(() => _grantingAll = true);

    try {
      final runtimeOk = await _requestRuntimePermissions();

      if (!runtimeOk) {
        final statuses =
            await Future.wait(_runtimePermissions.map((p) => p.status));
        final permanentlyDenied = statuses.any((s) => s.isPermanentlyDenied);
        if (permanentlyDenied) {
          await _callService.openAppPermissionSettings();
        }
      }

      await _refreshAutomationStatus();

      if (!_accessibilityEnabled) {
        await _callService.openAccessibilitySettings();
      }

      await _refreshAutomationStatus();

      if (!_notificationAccessEnabled) {
        await _callService.openNotificationAccessSettings();
      }

      await _refreshAutomationStatus();

      if (!mounted) return;
      final fullyReady = _runtimePermissionsGranted &&
          _accessibilityEnabled &&
          _notificationAccessEnabled;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            fullyReady
                ? 'Automation permissions ready. Start the service now.'
                : 'Some access is still pending. Enable missing items from settings and tap Refresh.',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _grantingAll = false);
    }
  }

  Future<bool> _ensurePermissions() async {
    final runtimeOk = await _requestRuntimePermissions();
    await _refreshAutomationStatus();
    return runtimeOk && _accessibilityEnabled && _notificationAccessEnabled;
  }

  Future<void> _saveSettings() async {
    setState(() => _saving = true);
    try {
      await _callService.setCustomMessage(_messageCtrl.text.trim());
      await _callService.setAnswerDelayMs((_delaySeconds * 1000).round());
      await _callService.setPcIp(_pcIpCtrl.text.trim());
      await _callService.setAutoStart(_autoStart);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Call assistant settings saved.')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('CALL SETTINGS')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          JPanel(
            label: 'SERVICE',
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _serviceOn ? 'Call guard running' : 'Call guard stopped',
                    style: GoogleFonts.shareTech(
                      fontSize: 13,
                      color: JarvisColors.textPrimary,
                    ),
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: _saving ? null : _toggleService,
                  icon: Icon(
                    _serviceOn
                        ? Icons.stop_circle_outlined
                        : Icons.play_circle_outline,
                  ),
                  label: Text(_serviceOn ? 'STOP' : 'START'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          JPanel(
            label: 'AUTOMATION ACCESS',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _statusRow('Runtime permissions', _runtimePermissionsGranted),
                const SizedBox(height: 6),
                _statusRow('Accessibility service', _accessibilityEnabled),
                const SizedBox(height: 6),
                _statusRow('Notification access', _notificationAccessEnabled),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: _grantingAll
                        ? 'GRANTING ACCESS...'
                        : 'GRANT ALL AUTOMATION ACCESS',
                    icon: Icons.admin_panel_settings_outlined,
                    onTap: _grantingAll ? null : _grantAllAutomationAccess,
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: 'REFRESH ACCESS STATUS',
                    icon: Icons.refresh_outlined,
                    onTap: _refreshAutomationStatus,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          JPanel(
            label: 'STARTUP',
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                'Auto-start after reboot',
                style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
              ),
              subtitle: Text(
                'Starts Call Guard automatically when phone reboots.',
                style: GoogleFonts.shareTech(
                  fontSize: 12,
                  color: JarvisColors.textSecondary,
                ),
              ),
              value: _autoStart,
              onChanged: (value) => setState(() => _autoStart = value),
            ),
          ),
          const SizedBox(height: 12),
          JPanel(
            label: 'GREETING MESSAGE',
            child: TextField(
              controller: _messageCtrl,
              maxLines: 4,
              style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
              decoration: const InputDecoration(
                hintText: 'Message spoken after wish greeting',
              ),
            ),
          ),
          const SizedBox(height: 12),
          JPanel(
            label: 'ANSWER DELAY',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Delay before answering',
                      style: GoogleFonts.shareTech(
                        color: JarvisColors.textSecondary,
                      ),
                    ),
                    Text(
                      '${_delaySeconds.toInt()}s',
                      style: GoogleFonts.orbitron(
                        fontSize: 11,
                        color: JarvisColors.cyan,
                      ),
                    ),
                  ],
                ),
                Slider(
                  value: _delaySeconds,
                  min: 2,
                  max: 10,
                  divisions: 8,
                  onChanged: (value) => setState(() => _delaySeconds = value),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          JPanel(
            label: 'WINDOWS SYNC',
            child: TextField(
              controller: _pcIpCtrl,
              style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
              decoration: const InputDecoration(hintText: 'PC IP address'),
            ),
          ),
          const SizedBox(height: 12),
          JButton(
            label: _saving ? 'SAVING...' : 'SAVE SETTINGS',
            icon: Icons.save_outlined,
            onTap: _saving ? null : _saveSettings,
          ),
          const SizedBox(height: 12),
          JPanel(
            label: 'MANUAL SETUP',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _step(
                  'Enable Accessibility service for WhatsApp/Instagram auto-send.',
                ),
                _step(
                    'Grant phone, microphone, notification, and contacts permissions.'),
                _step(
                    'Enable Notification access so JARVIS can read notifications and auto-reply.'),
                _step(
                    'Place Vosk model in android/app/src/main/assets/vosk-model/.'),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: 'OPEN ACCESSIBILITY SETTINGS',
                    icon: Icons.accessibility_new_outlined,
                    onTap: _callService.openAccessibilitySettings,
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: 'OPEN NOTIFICATION ACCESS',
                    icon: Icons.notifications_active_outlined,
                    onTap: _callService.openNotificationAccessSettings,
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: 'OPEN APP PERMISSION PAGE',
                    icon: Icons.settings_outlined,
                    onTap: _callService.openAppPermissionSettings,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusRow(String label, bool ok) {
    final color = ok ? JarvisColors.green : JarvisColors.red;
    return Row(
      children: [
        Icon(
          ok ? Icons.check_circle_outline : Icons.cancel_outlined,
          color: color,
          size: 16,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            '$label: ${ok ? 'ENABLED' : 'NOT ENABLED'}',
            style: GoogleFonts.shareTech(
              fontSize: 12,
              color: JarvisColors.textPrimary,
            ),
          ),
        ),
      ],
    );
  }

  Widget _step(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('- ', style: GoogleFonts.shareTech(color: JarvisColors.cyan)),
          Expanded(
            child: Text(
              text,
              style: GoogleFonts.shareTech(
                fontSize: 12,
                color: JarvisColors.textPrimary,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
