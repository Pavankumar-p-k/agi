// lib/screens/home_screen.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/services.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';
import 'chat_screen.dart';
import 'reminders_screen.dart';
import 'notes_screen.dart';
import 'activity_screen.dart';
import 'face_recognition_screen.dart';
import 'media_player_screen.dart';
import 'file_manager_screen.dart';
import 'messaging_screen.dart';
import 'talkback_screen.dart';
import 'automation_screen.dart';
import 'call_log_screen.dart';
import 'call_settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with TickerProviderStateMixin {
  int _currentIndex = 0;
  bool _serverOnline = false;
  late AnimationController _fadeCtrl;

  final _screens = const [
    _DashboardTab(),
    ChatScreen(),
    RemindersScreen(),
    NotesScreen(),
    _MoreTab(),
  ];

  @override
  void initState() {
    super.initState();
    _fadeCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 600));
    _fadeCtrl.forward();
    _checkServer();
  }

  @override
  void dispose() {
    _fadeCtrl.dispose();
    super.dispose();
  }

  Future<void> _checkServer() async {
    final api = ApiService();
    final online = await api.isOnline();
    if (mounted) setState(() => _serverOnline = online);
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthService>();
    final ws = context.read<WebSocketService>();

    return ScanlineOverlay(
      child: Scaffold(
        appBar: AppBar(
          title: Row(mainAxisSize: MainAxisSize.min, children: [
            StatusDot(active: _serverOnline),
            const SizedBox(width: 8),
            const Text('J.A.R.V.I.S'),
          ]),
          actions: [
            // Clock
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: _LiveClock(),
            ),
            // User
            PopupMenuButton<String>(
              icon: const Icon(Icons.person_outline, color: JarvisColors.cyan),
              color: JarvisColors.bgCard,
              onSelected: (v) async {
                if (v == 'logout') {
                  ws.disconnect(clearQueue: true);
                  await auth.signOut();
                }
              },
              itemBuilder: (_) => [
                PopupMenuItem(
                  enabled: false,
                  child: Text(auth.email,
                      style: GoogleFonts.shareTech(
                        fontSize: 12,
                        color: JarvisColors.textSecondary,
                      )),
                ),
                const PopupMenuDivider(),
                PopupMenuItem(
                  value: 'logout',
                  child: Row(children: [
                    const Icon(Icons.logout, size: 14, color: JarvisColors.red),
                    const SizedBox(width: 8),
                    Text('Sign Out',
                        style: GoogleFonts.shareTech(color: JarvisColors.red)),
                  ]),
                ),
              ],
            ),
          ],
        ),
        body: FadeTransition(
          opacity: _fadeCtrl,
          child: IndexedStack(index: _currentIndex, children: _screens),
        ),
        bottomNavigationBar: Container(
          decoration: const BoxDecoration(
            border:
                Border(top: BorderSide(color: JarvisColors.border, width: 1)),
          ),
          child: BottomNavigationBar(
            currentIndex: _currentIndex,
            onTap: (i) => setState(() => _currentIndex = i),
            items: const [
              BottomNavigationBarItem(
                  icon: Icon(Icons.dashboard_outlined), label: 'DASH'),
              BottomNavigationBarItem(
                  icon: Icon(Icons.chat_bubble_outline), label: 'CHAT'),
              BottomNavigationBarItem(
                  icon: Icon(Icons.alarm_outlined), label: 'ALARMS'),
              BottomNavigationBarItem(
                  icon: Icon(Icons.note_outlined), label: 'NOTES'),
              BottomNavigationBarItem(
                  icon: Icon(Icons.grid_view_outlined), label: 'MORE'),
            ],
          ),
        ),
      ),
    );
  }
}

// ── LIVE CLOCK ──
class _LiveClock extends StatefulWidget {
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
    setState(() => _time =
        '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:${now.second.toString().padLeft(2, '0')}');
  }

  @override
  Widget build(BuildContext context) => Text(
        _time,
        style: GoogleFonts.orbitron(
            fontSize: 11, color: JarvisColors.cyan, letterSpacing: 2),
      );
}

// ══════════════════════════════════════════════
//  DASHBOARD TAB
// ══════════════════════════════════════════════
class _DashboardTab extends StatelessWidget {
  const _DashboardTab();

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Greeting row
        Row(children: [
          HudRing(size: 80),
          const SizedBox(width: 16),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text('ONLINE',
                    style: GoogleFonts.orbitron(
                        fontSize: 9,
                        letterSpacing: 3,
                        color: JarvisColors.green)),
                const SizedBox(height: 4),
                Text(
                  'Hello, ${context.read<AuthService>().displayName.toUpperCase()}',
                  style: GoogleFonts.orbitron(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: JarvisColors.textPrimary,
                      letterSpacing: 1),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text('All systems operational',
                    style: GoogleFonts.shareTech(
                        fontSize: 12, color: JarvisColors.textSecondary)),
              ])),
        ]),

        const SizedBox(height: 20),

        // Quick action grid
        JPanel(
          label: 'QUICK ACCESS',
          child: GridView.count(
            crossAxisCount: 3,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 1.1,
            children: [
              _QuickTile(
                  icon: Icons.face_outlined,
                  label: 'FACES',
                  onTap: () =>
                      _navigate(context, const FaceRecognitionScreen())),
              _QuickTile(
                  icon: Icons.music_note_outlined,
                  label: 'MUSIC',
                  onTap: () => _navigate(context, const MediaPlayerScreen())),
              _QuickTile(
                  icon: Icons.folder_outlined,
                  label: 'FILES',
                  onTap: () => _navigate(context, const FileManagerScreen())),
              _QuickTile(
                  icon: Icons.send_outlined,
                  label: 'MSG',
                  onTap: () => _navigate(context, const MessagingScreen())),
              _QuickTile(
                  icon: Icons.bar_chart_outlined,
                  label: 'STATS',
                  onTap: () => _navigate(context, const ActivityScreen())),
              _QuickTile(
                  icon: Icons.mic_outlined,
                  label: 'VOICE',
                  color: JarvisColors.cyan,
                  onTap: () => _navigate(context, const TalkBackScreen())),
              _QuickTile(
                  icon: Icons.account_tree_outlined,
                  label: 'AUTO',
                  color: JarvisColors.blue,
                  onTap: () => _navigate(context, const AutomationScreen())),
              _QuickTile(
                  icon: Icons.call_outlined,
                  label: 'CALLS',
                  color: JarvisColors.green,
                  onTap: () => _navigate(context, const CallLogScreen())),
              _QuickTile(
                  icon: Icons.settings_phone_outlined,
                  label: 'GUARD',
                  color: JarvisColors.orange,
                  onTap: () => _navigate(context, const CallSettingsScreen())),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // System metrics
        JPanel(
          label: 'SYSTEM METRICS',
          child: Column(children: [
            const MetricBar(label: 'CPU LOAD', value: 0.42),
            const SizedBox(height: 12),
            const MetricBar(
                label: 'MEMORY', value: 0.61, color: JarvisColors.blue),
            const SizedBox(height: 12),
            const MetricBar(
                label: 'NEURAL NET', value: 0.87, color: JarvisColors.green),
          ]),
        ),

        const SizedBox(height: 16),

        // Today's date/info panel
        JPanel(
          label: 'TODAY\'S BRIEF',
          child: _TodayBrief(),
        ),
      ]),
    );
  }

  void _navigate(BuildContext context, Widget screen) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
  }
}

class _QuickTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;

  const _QuickTile(
      {required this.icon,
      required this.label,
      required this.onTap,
      this.color});

  @override
  Widget build(BuildContext context) {
    final col = color ?? JarvisColors.cyan;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: JarvisColors.bgPanel,
          border: Border.all(color: col.withOpacity(0.2)),
        ),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(icon, color: col, size: 22),
          const SizedBox(height: 6),
          Text(label,
              style: GoogleFonts.orbitron(
                  fontSize: 8, letterSpacing: 1.5, color: col)),
        ]),
      ),
    );
  }
}

class _TodayBrief extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final dayName = [
      'MONDAY',
      'TUESDAY',
      'WEDNESDAY',
      'THURSDAY',
      'FRIDAY',
      'SATURDAY',
      'SUNDAY'
    ][now.weekday - 1];
    final months = [
      'JAN',
      'FEB',
      'MAR',
      'APR',
      'MAY',
      'JUN',
      'JUL',
      'AUG',
      'SEP',
      'OCT',
      'NOV',
      'DEC'
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text(dayName,
            style: GoogleFonts.orbitron(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: JarvisColors.cyan)),
        const Spacer(),
        Text('${now.day} ${months[now.month - 1]} ${now.year}',
            style: GoogleFonts.shareTech(
                fontSize: 12, color: JarvisColors.textSecondary)),
      ]),
      const SizedBox(height: 10),
      Row(children: [
        _BriefChip(label: 'REMINDERS', value: '—', icon: Icons.alarm_outlined),
        const SizedBox(width: 10),
        _BriefChip(label: 'NOTES', value: '—', icon: Icons.note_outlined),
        const SizedBox(width: 10),
        _BriefChip(label: 'FACES', value: '—', icon: Icons.face_outlined),
      ]),
    ]);
  }
}

class _BriefChip extends StatelessWidget {
  final String label, value;
  final IconData icon;
  const _BriefChip(
      {required this.label, required this.value, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Expanded(
        child: Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: Border.all(color: JarvisColors.border),
        color: JarvisColors.bgPanel,
      ),
      child: Column(children: [
        Icon(icon, size: 16, color: JarvisColors.cyan),
        const SizedBox(height: 4),
        Text(value,
            style: GoogleFonts.orbitron(
                fontSize: 14, color: JarvisColors.textPrimary)),
        Text(label,
            style: GoogleFonts.orbitron(
                fontSize: 7,
                letterSpacing: 1,
                color: JarvisColors.textSecondary)),
      ]),
    ));
  }
}

// ── MORE TAB ──
class _MoreTab extends StatelessWidget {
  const _MoreTab();

  @override
  Widget build(BuildContext context) {
    final items = [
      _MoreItem(
          icon: Icons.face_outlined,
          label: 'Face Recognition',
          sub: 'Identify & register people',
          screen: const FaceRecognitionScreen()),
      _MoreItem(
          icon: Icons.music_note_outlined,
          label: 'Media Player',
          sub: 'Music & audio playback',
          screen: const MediaPlayerScreen()),
      _MoreItem(
          icon: Icons.folder_outlined,
          label: 'File Manager',
          sub: 'Browse PC files remotely',
          screen: const FileManagerScreen()),
      _MoreItem(
          icon: Icons.send_outlined,
          label: 'Message Sender',
          sub: 'WhatsApp & Instagram DMs',
          screen: const MessagingScreen()),
      _MoreItem(
          icon: Icons.auto_awesome_outlined,
          label: 'Automation',
          sub: 'Run PC automation commands',
          screen: const AutomationScreen()),
      _MoreItem(
          icon: Icons.call_outlined,
          label: 'Call Log',
          sub: 'Important and all auto-captured calls',
          screen: const CallLogScreen()),
      _MoreItem(
          icon: Icons.settings_phone_outlined,
          label: 'Call Assistant Settings',
          sub: 'Auto-answer behavior and sync options',
          screen: const CallSettingsScreen()),
      _MoreItem(
          icon: Icons.bar_chart_outlined,
          label: 'Activity Tracker',
          sub: 'Daily summary & insights',
          screen: const ActivityScreen()),
    ];

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('MORE FEATURES',
            style: GoogleFonts.orbitron(
              fontSize: 11,
              letterSpacing: 3,
              color: JarvisColors.textSecondary,
            )),
        const SizedBox(height: 12),
        ...items.map((item) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: GestureDetector(
                onTap: () => Navigator.push(
                    context, MaterialPageRoute(builder: (_) => item.screen)),
                child: JPanel(
                  child: Row(children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        border: Border.all(
                            color: JarvisColors.cyan.withOpacity(0.3)),
                        color: JarvisColors.cyan.withOpacity(0.07),
                      ),
                      child:
                          Icon(item.icon, color: JarvisColors.cyan, size: 20),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                          Text(item.label,
                              style: GoogleFonts.orbitron(
                                  fontSize: 12,
                                  color: JarvisColors.textPrimary,
                                  letterSpacing: 1)),
                          const SizedBox(height: 3),
                          Text(item.sub,
                              style: GoogleFonts.shareTech(
                                  fontSize: 12,
                                  color: JarvisColors.textSecondary)),
                        ])),
                    const Icon(Icons.chevron_right,
                        color: JarvisColors.textSecondary, size: 16),
                  ]),
                ),
              ),
            )),
      ],
    );
  }
}

class _MoreItem {
  final IconData icon;
  final String label, sub;
  final Widget screen;
  const _MoreItem(
      {required this.icon,
      required this.label,
      required this.sub,
      required this.screen});
}
