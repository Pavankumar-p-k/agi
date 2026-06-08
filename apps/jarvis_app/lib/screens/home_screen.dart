import 'dart:async';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '../services/api_service.dart';
import '../services/feature_settings.dart';
import '../services/laptop_sync.dart';
import '../ai/model_detector.dart';
import '../services/services.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';
import 'activity_screen.dart';
import 'alarm_screen.dart';
import 'contacts_screen.dart';
import 'file_manager_screen.dart';
import 'media_player_screen.dart';
import 'messaging_screen.dart';
import 'notes_screen.dart';
import 'offline_assistant_screen.dart';
import 'reply_agent_screen.dart';
import 'settings_screen.dart';
import 'talkback_screen.dart';
import 'build_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with TickerProviderStateMixin {
  int _tab = 0;

  void changeTab(int index) {
    setState(() => _tab = index);
  }

  bool _serverOnline = false;
  bool _backendConnected = false;
  String _backendType = 'Unknown';
  String _backendModel = 'Unknown';
  String _backendUrl = 'Unknown';
  String _backendMessage = 'Local model status unknown.';
  FeatureSettings _features = FeatureSettings.defaults();
  late final AnimationController _fadeCtrl;
  Timer? _serverTimer;

  static const List<_NavItem> _items = [
    _NavItem(icon: Icons.dashboard_outlined, active: Icons.dashboard, label: 'HOME'),
    _NavItem(icon: Icons.smart_toy_outlined, active: Icons.smart_toy, label: 'ASSIST'),
    _NavItem(icon: Icons.alarm_outlined, active: Icons.alarm, label: 'ALARMS'),
    _NavItem(icon: Icons.note_alt_outlined, active: Icons.note_alt, label: 'NOTES'),
    _NavItem(icon: Icons.library_music_outlined, active: Icons.library_music, label: 'MEDIA'),
    _NavItem(icon: Icons.tune_outlined, active: Icons.tune, label: 'SYSTEM'),
  ];

  @override
  void initState() {
    super.initState();
    _fadeCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 360),
    )..forward();
    _serverTimer = Timer.periodic(const Duration(seconds: 20), (_) => _checkServer());
    _checkServer();
    _loadFeatures();
    _checkLocalModelStatus();
    context.read<WebSocketService>().connect();
  }

  Future<void> _checkLocalModelStatus() async {
    try {
      final result = await ModelDetector.detectOnly();
      if (!mounted) return;
      setState(() {
        _backendConnected = result != null;
        _backendType = result != null ? 'Detected' : 'Unknown';
        _backendModel = result ?? 'None';
        _backendUrl = FeatureSettings.getOllamaUrl();
        _backendMessage = result != null
            ? 'Local model detected: $result'
            : 'No local model backend found.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _backendConnected = false;
        _backendType = 'Unknown';
        _backendModel = 'Unknown';
        _backendUrl = 'Unknown';
        _backendMessage = 'Unable to query local model status.';
      });
    }
  }

  @override
  void dispose() {
    _serverTimer?.cancel();
    _fadeCtrl.dispose();
    super.dispose();
  }

  Future<void> _checkServer() async {
    final online = await ApiService().isOnline();
    if (!mounted) return;
    setState(() => _serverOnline = online);
  }

  Future<void> _loadFeatures() async {
    final features = await FeatureSettings.load();
    if (!mounted) return;
    setState(() => _features = features);
  }

  Future<void> _openScreen(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    await _loadFeatures();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthService>();

    return ScanlineOverlay(
      child: Scaffold(
        appBar: AppBar(
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              StatusDot(active: _serverOnline, color: JarvisColors.green),
              const SizedBox(width: 8),
              const Text('J.A.R.V.I.S'),
              const SizedBox(width: 10),
              _ModeChip(
                label: LaptopSync.isConnected ? 'SYNCED' : 'OFFLINE',
                color: LaptopSync.isConnected
                    ? JarvisColors.cyan
                    : JarvisColors.orange,
              ),
            ],
          ),
          actions: [
            const Padding(
              padding: EdgeInsets.only(right: 12),
              child: _LiveClock(),
            ),
            PopupMenuButton<String>(
              icon: const Icon(Icons.person_outline, color: JarvisColors.cyan),
              color: JarvisColors.bgCard,
              onSelected: (value) {
                if (value == 'logout') {
                  auth.signOut();
                }
              },
              itemBuilder: (_) => [
                PopupMenuItem(
                  enabled: false,
                  child: Text(
                    auth.email,
                    style: GoogleFonts.shareTech(
                      fontSize: 12,
                      color: JarvisColors.textSecondary,
                    ),
                  ),
                ),
                const PopupMenuDivider(),
                PopupMenuItem(
                  value: 'logout',
                  child: Row(
                    children: [
                      const Icon(Icons.logout, size: 14, color: JarvisColors.red),
                      const SizedBox(width: 8),
                      Text(
                        'Sign Out',
                        style: GoogleFonts.shareTech(color: JarvisColors.red),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
        body: FadeTransition(
          opacity: _fadeCtrl,
          child: IndexedStack(
            index: _tab,
            children: [
              _DashboardTab(
                onOpen: _openScreen,
                features: _features,
                backendConnected: _backendConnected,
                backendModel: _backendModel,
                backendType: _backendType,
                backendUrl: _backendUrl,
                backendMessage: _backendMessage,
              ),
              _features.voiceEnabled
                  ? const OfflineAssistantScreen()
                  : const _DisabledModuleCard(
                      title: 'Assistant disabled',
                      message: 'Enable Voice + TalkBack in Settings to use the local assistant.',
                    ),
              _features.alarmsEnabled
                  ? const AlarmScreen()
                  : const _DisabledModuleCard(
                      title: 'Alarms disabled',
                      message: 'Enable Alarms in Settings to use reminders and alarm tools.',
                    ),
              _features.notesEnabled
                  ? const NotesScreen()
                  : const _DisabledModuleCard(
                      title: 'Notes disabled',
                      message: 'Enable Notes in Settings to store local notes.',
                    ),
              _features.mediaEnabled
                  ? const MediaPlayerScreen()
                  : const _DisabledModuleCard(
                      title: 'Media disabled',
                      message: 'Enable Media player in Settings to browse device audio.',
                    ),
              _SystemTab(onOpen: _openScreen, features: _features),
            ],
          ),
        ),
        bottomNavigationBar: _buildNavBar(),
      ),
    );
  }

  Widget _buildNavBar() {
    return Container(
      decoration: const BoxDecoration(
        color: JarvisColors.bgCard,
        border: Border(top: BorderSide(color: JarvisColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: List.generate(_items.length, (index) {
            final item = _items[index];
            final selected = _tab == index;
            return Expanded(
              child: InkWell(
                onTap: () => setState(() {
                  _tab = index;
                  _fadeCtrl.forward(from: 0);
                }),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  padding: const EdgeInsets.symmetric(vertical: 9),
                  decoration: BoxDecoration(
                    color: selected
                        ? JarvisColors.cyan.withValues(alpha: 0.08)
                        : Colors.transparent,
                    border: Border(
                      top: BorderSide(
                        color: selected
                            ? JarvisColors.cyan
                            : Colors.transparent,
                        width: 2,
                      ),
                    ),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        selected ? item.active : item.icon,
                        size: 19,
                        color: selected
                            ? JarvisColors.cyan
                            : JarvisColors.textDim,
                      ),
                      const SizedBox(height: 3),
                      Text(
                        item.label,
                        style: GoogleFonts.orbitron(
                          fontSize: 8,
                          letterSpacing: 0.9,
                          color: selected
                              ? JarvisColors.cyan
                              : JarvisColors.textDim,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}

class _DashboardTab extends StatelessWidget {
  final ValueChanged<Widget> onOpen;
  final FeatureSettings features;
  final bool backendConnected;
  final String backendModel;
  final String backendType;
  final String backendUrl;
  final String backendMessage;

  const _DashboardTab({
    required this.onOpen,
    required this.features,
    required this.backendConnected,
    required this.backendModel,
    required this.backendType,
    required this.backendUrl,
    required this.backendMessage,
  });

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthService>();
    final now = DateTime.now();
    final greeting = now.hour < 12
        ? 'Good Morning'
        : now.hour < 17
            ? 'Good Afternoon'
            : 'Good Evening';

    final primaryActions = <Widget>[
      _LaunchTile(
        icon: Icons.smart_toy_outlined,
        title: 'Assistant',
        sub: 'Local dataset + task actions',
        color: JarvisColors.cyan,
        onTap: () {},
      ),
      if (features.voiceEnabled)
        _LaunchTile(
          icon: Icons.record_voice_over_outlined,
          title: 'TalkBack',
          sub: 'Offline speech loop',
          color: JarvisColors.green,
          onTap: () => onOpen(const TalkBackScreen()),
        ),
      if (features.autoReplyEnabled)
        _LaunchTile(
          icon: Icons.quickreply_outlined,
          title: 'Auto Reply',
          sub: 'Notification listener control',
          color: JarvisColors.orange,
          onTap: () => onOpen(const ReplyAgentScreen()),
        ),
    ];

    final quickTools = <Widget>[
      if (features.contactsEnabled)
        _MiniAction('Contacts', Icons.contacts_outlined,
            () => onOpen(const ContactsScreen())),
      if (features.automationEnabled)
        _MiniAction('Messages', Icons.send_outlined,
            () => onOpen(const MessagingScreen())),
      _MiniAction('Remote Files', Icons.folder_outlined,
          () => onOpen(const FileManagerScreen())),
      _MiniAction('Remote Activity', Icons.analytics_outlined,
          () => onOpen(const ActivityScreen())),
      _MiniAction('Settings', Icons.settings_outlined,
          () => onOpen(const SettingsScreen())),
    ];

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          JPanel(
            accentColor: JarvisColors.cyan,
            child: Row(
              children: [
                const HudRing(size: 82),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        greeting.toUpperCase(),
                        style: J.orbitron(
                          9,
                          color: JarvisColors.green,
                          spacing: 2.4,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        auth.displayName.toUpperCase(),
                        style: J.orbitron(
                          18,
                          weight: FontWeight.w800,
                          spacing: 1.2,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'One assistant surface. Offline AI, voice control, auto-reply and core tools are grouped here.',
                        style: J.shareTech(12, color: JarvisColors.textSecondary),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: MetricCard(
                  label: 'AI MODE',
                  value: LaptopSync.isConnected ? 'SYNC' : 'LOCAL',
                  sub: LaptopSync.isConnected
                      ? 'Laptop bridge ready'
                      : 'Local dataset active',
                  accent: LaptopSync.isConnected
                      ? JarvisColors.cyan
                      : JarvisColors.orange,
                  icon: Icons.psychology_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: const MetricCard(
                  label: 'VOICE',
                  value: 'OFFLINE',
                  sub: 'TTS + STT on device',
                  accent: JarvisColors.green,
                  icon: Icons.mic_none_outlined,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          JPanel(
            label: 'LOCAL MODEL STATUS',
            accentColor: backendConnected ? JarvisColors.green : JarvisColors.orange,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Model: ${backendModel.toUpperCase()}',
                    style: J.shareTech(12, color: JarvisColors.textPrimary)),
                const SizedBox(height: 6),
                Text('Backend: $backendType',
                    style: J.shareTech(11, color: JarvisColors.textSecondary)),
                const SizedBox(height: 2),
                Text(
                  backendConnected
                      ? 'Connected at $backendUrl'
                      : backendMessage,
                  style: J.shareTech(11, color: JarvisColors.textSecondary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          JPanel(
            label: 'PRIMARY ACTIONS',
              child: GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                childAspectRatio: 1.45,
              children: primaryActions,
            ),
          ),
          const SizedBox(height: 16),
          JPanel(
            label: 'QUICK TOOLS',
            child: Wrap(
              spacing: 10,
              runSpacing: 10,
              children: quickTools,
            ),
          ),
        ],
      ),
    );
  }
}

class _SystemTab extends StatelessWidget {
  final ValueChanged<Widget> onOpen;
  final FeatureSettings features;

  const _SystemTab({required this.onOpen, required this.features});

  @override
  Widget build(BuildContext context) {
    final items = <_SystemItem>[
      if (features.autoReplyEnabled)
        _SystemItem(
        title: 'Reply Listener',
        sub: 'Notification listener and platform toggles',
        icon: Icons.quickreply_outlined,
        color: JarvisColors.orange,
        screen: const ReplyAgentScreen(),
      ),
      if (features.voiceEnabled)
        _SystemItem(
        title: 'TalkBack',
        sub: 'Offline TTS to STT loop',
        icon: Icons.record_voice_over_outlined,
        color: JarvisColors.green,
        screen: const TalkBackScreen(),
      ),
      if (features.automationEnabled)
        _SystemItem(
        title: 'Messaging',
        sub: 'Compose native drafts for SMS, WhatsApp and email',
        icon: Icons.send_outlined,
        color: JarvisColors.cyan,
        screen: const MessagingScreen(),
      ),
      if (features.contactsEnabled)
        _SystemItem(
        title: 'Contacts',
        sub: 'Device contacts, dialer and compose actions',
        icon: Icons.contacts_outlined,
        color: JarvisColors.cyan,
        screen: const ContactsScreen(),
      ),
      _SystemItem(
        title: 'Remote Files',
        sub: 'Backend file explorer',
        icon: Icons.folder_outlined,
        color: JarvisColors.textPrimary,
        screen: const FileManagerScreen(),
      ),
      _SystemItem(
        title: 'Remote Activity',
        sub: 'Backend usage and status summary',
        icon: Icons.analytics_outlined,
        color: JarvisColors.green,
        screen: const ActivityScreen(),
      ),
      _SystemItem(
        title: 'Build Dashboard',
        sub: 'Project tracking, quality scores, governor, env',
        icon: Icons.construction_outlined,
        color: JarvisColors.blue,
        screen: const BuildScreen(),
      ),
      _SystemItem(
        title: 'Settings',
        sub: 'Feature toggles and startup rules',
        icon: Icons.settings_outlined,
        color: JarvisColors.textSecondary,
        screen: const SettingsScreen(),
      ),
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: items.length,
      itemBuilder: (_, index) {
        final item = items[index];
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: GestureDetector(
            onTap: () => onOpen(item.screen),
            child: JPanel(
              borderColor: item.color.withValues(alpha: 0.25),
              accentColor: item.color,
              child: Row(
                children: [
                  Container(
                    width: 46,
                    height: 46,
                    decoration: BoxDecoration(
                      color: item.color.withValues(alpha: 0.08),
                      border: Border.all(color: item.color.withValues(alpha: 0.35)),
                    ),
                    child: Icon(item.icon, color: item.color, size: 22),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          item.title,
                          style: J.orbitron(12, spacing: 0.8),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          item.sub,
                          style: J.shareTech(
                            12,
                            color: JarvisColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    size: 18,
                    color: JarvisColors.textSecondary,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _DisabledModuleCard extends StatelessWidget {
  final String title;
  final String message;

  const _DisabledModuleCard({
    required this.title,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: JPanel(
          label: 'MODULE DISABLED',
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(title, style: J.orbitron(14, color: JarvisColors.orange)),
              const SizedBox(height: 10),
              Text(
                message,
                textAlign: TextAlign.center,
                style: J.shareTech(13, color: JarvisColors.textSecondary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModeChip extends StatelessWidget {
  final String label;
  final Color color;

  const _ModeChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        border: Border.all(color: color.withValues(alpha: 0.4)),
        color: color.withValues(alpha: 0.08),
      ),
      child: Text(
        label,
        style: J.orbitron(7, color: color, spacing: 1.4),
      ),
    );
  }
}

class _LaunchTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String sub;
  final Color color;
  final VoidCallback onTap;

  const _LaunchTile({
    required this.icon,
    required this.title,
    required this.sub,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: title == 'Assistant'
          ? () {
              final state = context.findAncestorStateOfType<_HomeScreenState>();
              state?.changeTab(1);
            }
          : onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: JarvisColors.bgPanel,
          border: Border.all(color: color.withValues(alpha: 0.28)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 20, color: color),
            const Spacer(),
            Text(title, style: J.orbitron(11, color: color, spacing: 0.8)),
            const SizedBox(height: 4),
            Text(sub, style: J.shareTech(11, color: JarvisColors.textSecondary)),
          ],
        ),
      ),
    );
  }
}

class _MiniAction extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const _MiniAction(this.label, this.icon, this.onTap);

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        width: 108,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
        decoration: BoxDecoration(
          color: JarvisColors.bgPanel,
          border: Border.all(color: JarvisColors.border),
        ),
        child: Row(
          children: [
            Icon(icon, size: 14, color: JarvisColors.cyan),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                label,
                style: J.shareTech(11, color: JarvisColors.textPrimary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SystemItem {
  final String title;
  final String sub;
  final IconData icon;
  final Color color;
  final Widget screen;

  const _SystemItem({
    required this.title,
    required this.sub,
    required this.icon,
    required this.color,
    required this.screen,
  });
}

class _NavItem {
  final IconData icon;
  final IconData active;
  final String label;

  const _NavItem({
    required this.icon,
    required this.active,
    required this.label,
  });
}

class _LiveClock extends StatefulWidget {
  const _LiveClock();

  @override
  State<_LiveClock> createState() => _LiveClockState();
}

class _LiveClockState extends State<_LiveClock> {
  late String _time;

  @override
  void initState() {
    super.initState();
    _update();
    Future.doWhile(() async {
      await Future.delayed(const Duration(seconds: 1));
      if (!mounted) return false;
      _update();
      return true;
    });
  }

  void _update() {
    final now = DateTime.now();
    setState(() {
      _time =
          '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:${now.second.toString().padLeft(2, '0')}';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Text(
      _time,
      style: J.orbitron(11, color: JarvisColors.cyan, spacing: 1.8),
    );
  }
}
