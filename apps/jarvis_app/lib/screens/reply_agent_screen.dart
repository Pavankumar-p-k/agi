import 'dart:async';

import 'package:flutter/material.dart';

import '../services/reply_agent.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class ReplyAgentScreen extends StatefulWidget {
  const ReplyAgentScreen({super.key});

  @override
  State<ReplyAgentScreen> createState() => _ReplyAgentScreenState();
}

class _ReplyAgentScreenState extends State<ReplyAgentScreen> {
  final List<Map<String, dynamic>> _feed = [];
  StreamSubscription? _resultSub;
  bool _notificationAccess = false;
  bool _accessibilityAccess = false;

  @override
  void initState() {
    super.initState();
    replyAgent.start();
    _resultSub = replyAgent.onResult.listen((event) {
      if (!mounted) return;
      setState(() {
        _feed.insert(0, event);
        if (_feed.length > 60) {
          _feed.removeLast();
        }
      });
    });
    _refreshPermissions();
  }

  @override
  void dispose() {
    _resultSub?.cancel();
    super.dispose();
  }

  Future<void> _refreshPermissions() async {
    final notification = await replyAgent.isNotificationAccessEnabled();
    final accessibility = await replyAgent.isAccessibilityEnabled();
    if (!mounted) return;
    setState(() {
      _notificationAccess = notification;
      _accessibilityAccess = accessibility;
    });
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refreshPermissions,
      color: JarvisColors.cyan,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          JPanel(
            label: 'AUTO REPLY',
            accentColor: replyAgent.masterEnabled
                ? JarvisColors.cyan
                : JarvisColors.red,
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        replyAgent.masterEnabled
                            ? 'Listener active. Replies are generated from the local model and notification actions.'
                            : 'Master switch is off. Incoming messages will be captured, but no replies are sent.',
                        style: J.shareTech(12, color: JarvisColors.textSecondary),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Switch(
                      value: replyAgent.masterEnabled,
                      onChanged: (value) => setState(
                        () => replyAgent.setMasterEnabled(value),
                      ),
                      activeColor: JarvisColors.cyan,
                      activeTrackColor: JarvisColors.cyan.withOpacity(0.2),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: MetricCard(
                        label: 'RECEIVED',
                        value: '${replyAgent.totalReceived}',
                        sub: 'Messages seen',
                        accent: JarvisColors.cyan,
                        icon: Icons.inbox_outlined,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: MetricCard(
                        label: 'REPLIED',
                        value: '${replyAgent.totalReplied}',
                        sub: 'Successful sends',
                        accent: JarvisColors.green,
                        icon: Icons.reply_outlined,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          JPanel(
            label: 'PERMISSIONS',
            accentColor: JarvisColors.orange,
            child: Column(
              children: [
                _PermissionTile(
                  title: 'Notification listener',
                  sub: 'Required to read incoming messages and capture inline reply actions.',
                  granted: _notificationAccess,
                  onOpen: () async {
                    await replyAgent.openNotificationAccessSettings();
                    await Future.delayed(const Duration(milliseconds: 500));
                    _refreshPermissions();
                  },
                ),
                const SizedBox(height: 10),
                _PermissionTile(
                  title: 'Accessibility fallback',
                  sub: 'Optional. Used for future tap-based fallback flows.',
                  granted: _accessibilityAccess,
                  onOpen: () async {
                    await replyAgent.openAccessibilitySettings();
                    await Future.delayed(const Duration(milliseconds: 500));
                    _refreshPermissions();
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          JPanel(
            label: 'PLATFORMS',
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: JButton(
                        label: 'ENABLE ALL',
                        icon: Icons.toggle_on_outlined,
                        color: JarvisColors.green,
                        onTap: () => setState(
                          () => replyAgent.setAllPlatformsEnabled(true),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: JButton(
                        label: 'DISABLE ALL',
                        icon: Icons.toggle_off_outlined,
                        color: JarvisColors.red,
                        onTap: () => setState(
                          () => replyAgent.setAllPlatformsEnabled(false),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                ...replyAgent.platforms.entries.map(
                  (entry) => _PlatformTile(
                    name: entry.key,
                    settings: entry.value,
                    onChanged: (value) => setState(
                      () => replyAgent.setPlatformEnabled(entry.key, value),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          JPanel(
            label: 'RULES',
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Quiet hours',
                        style: J.orbitron(10, spacing: 1),
                      ),
                    ),
                    Switch(
                      value: replyAgent.quietHoursEnabled,
                      onChanged: (value) => setState(
                        () => replyAgent.setQuietHours(
                          value,
                          replyAgent.quietStart,
                          replyAgent.quietEnd,
                        ),
                      ),
                      activeColor: JarvisColors.cyan,
                    ),
                  ],
                ),
                if (replyAgent.quietHoursEnabled) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: _HourBox(
                          label: 'FROM',
                          hour: replyAgent.quietStart,
                          onTap: () async {
                            final picked = await _pickHour(replyAgent.quietStart);
                            if (picked != null) {
                              setState(() {
                                replyAgent.setQuietHours(
                                  true,
                                  picked,
                                  replyAgent.quietEnd,
                                );
                              });
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _HourBox(
                          label: 'TO',
                          hour: replyAgent.quietEnd,
                          onTap: () async {
                            final picked = await _pickHour(replyAgent.quietEnd);
                            if (picked != null) {
                              setState(() {
                                replyAgent.setQuietHours(
                                  true,
                                  replyAgent.quietStart,
                                  picked,
                                );
                              });
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 12),
                Row(
                  children: [
                    Text(
                      'Max replies per hour',
                      style: J.orbitron(10, spacing: 1),
                    ),
                    const Spacer(),
                    Text(
                      '${replyAgent.maxRepliesPerHour}',
                      style: J.orbitron(16, color: JarvisColors.orange, spacing: 0),
                    ),
                  ],
                ),
                Slider(
                  value: replyAgent.maxRepliesPerHour.toDouble(),
                  min: 5,
                  max: 100,
                  divisions: 19,
                  activeColor: JarvisColors.orange,
                  inactiveColor: JarvisColors.border,
                  onChanged: (value) => setState(
                    () => replyAgent.setMaxRepliesPerHour(value.toInt()),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          JPanel(
            label: 'LIVE FEED',
            child: _feed.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text(
                      'No messages captured yet. Enable the notification listener, then send yourself a WhatsApp, SMS or Telegram message to verify the pipeline.',
                      style: J.shareTech(12, color: JarvisColors.textSecondary),
                    ),
                  )
                : Column(
                    children: _feed.take(12).map((item) {
                      final sent = item['sent'] == true;
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: JarvisColors.bgPanel,
                          border: Border(
                            left: BorderSide(
                              color: sent
                                  ? JarvisColors.green
                                  : JarvisColors.orange,
                              width: 2,
                            ),
                            top: const BorderSide(color: JarvisColors.border),
                            right: const BorderSide(color: JarvisColors.border),
                            bottom: const BorderSide(color: JarvisColors.border),
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Text(
                                  '${item['platform'] ?? 'unknown'}'.toUpperCase(),
                                  style: J.orbitron(8, color: JarvisColors.cyan),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    '${item['sender'] ?? 'Unknown'}',
                                    style: J.rajdhani(
                                      15,
                                      weight: FontWeight.w700,
                                    ),
                                  ),
                                ),
                                Text(
                                  sent ? 'SENT' : 'SKIPPED',
                                  style: J.orbitron(
                                    8,
                                    color: sent
                                        ? JarvisColors.green
                                        : JarvisColors.orange,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '${item['message'] ?? ''}',
                              style: J.shareTech(
                                12,
                                color: JarvisColors.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              sent
                                  ? '${item['reply'] ?? ''}'
                                  : '${item['reason'] ?? ''}',
                              style: J.shareTech(
                                11,
                                color: sent
                                    ? JarvisColors.textSecondary
                                    : JarvisColors.orange,
                              ),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  ),
          ),
        ],
      ),
    );
  }

  Future<int?> _pickHour(int currentHour) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: currentHour, minute: 0),
      builder: (_, child) => Theme(data: ThemeData.dark(), child: child!),
    );
    return picked?.hour;
  }
}

class _PermissionTile extends StatelessWidget {
  final String title;
  final String sub;
  final bool granted;
  final VoidCallback onOpen;

  const _PermissionTile({
    required this.title,
    required this.sub,
    required this.granted,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: JarvisColors.bgPanel,
        border: Border.all(
          color: granted ? JarvisColors.green : JarvisColors.orange,
        ),
      ),
      child: Row(
        children: [
          Icon(
            granted ? Icons.check_circle_outline : Icons.warning_amber_outlined,
            color: granted ? JarvisColors.green : JarvisColors.orange,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: J.orbitron(10, spacing: 1)),
                const SizedBox(height: 3),
                Text(sub, style: J.shareTech(10, color: JarvisColors.textSecondary)),
              ],
            ),
          ),
          JButton(
            label: granted ? 'CHECK' : 'OPEN',
            color: granted ? JarvisColors.green : JarvisColors.orange,
            onTap: onOpen,
          ),
        ],
      ),
    );
  }
}

class _PlatformTile extends StatelessWidget {
  final String name;
  final PlatformSettings settings;
  final ValueChanged<bool> onChanged;

  const _PlatformTile({
    required this.name,
    required this.settings,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: JarvisColors.bgPanel,
        border: Border.all(color: JarvisColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name.toUpperCase(), style: J.orbitron(10, spacing: 1)),
                const SizedBox(height: 4),
                Text(
                  settings.enabled
                      ? 'Replies on, ${settings.minDelayMs}-${settings.maxDelayMs}ms typing delay'
                      : 'Replies disabled',
                  style: J.shareTech(10, color: JarvisColors.textSecondary),
                ),
              ],
            ),
          ),
          Switch(
            value: settings.enabled,
            onChanged: onChanged,
            activeColor: JarvisColors.cyan,
            activeTrackColor: JarvisColors.cyan.withOpacity(0.2),
          ),
        ],
      ),
    );
  }
}

class _HourBox extends StatelessWidget {
  final String label;
  final int hour;
  final VoidCallback onTap;

  const _HourBox({
    required this.label,
    required this.hour,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: JarvisColors.bgPanel,
          border: Border.all(color: JarvisColors.border),
        ),
        child: Column(
          children: [
            Text(label, style: J.orbitron(8, color: JarvisColors.textSecondary)),
            const SizedBox(height: 4),
            Text(
              '${hour.toString().padLeft(2, '0')}:00',
              style: J.orbitron(18, color: JarvisColors.cyan, spacing: 0.6),
            ),
          ],
        ),
      ),
    );
  }
}
