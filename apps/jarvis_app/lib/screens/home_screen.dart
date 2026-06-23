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
import '../widgets/jarvis_drawer.dart';

// Screens
import 'chat_screen.dart';
import 'feature_registry_screen.dart';
import 'model_management_screen.dart';
import 'agent_dashboard_screen.dart';
import 'automation_screen.dart';
import 'integration_management_screen.dart';
import 'diagnostics_dashboard_screen.dart';
import 'memory_dashboard_screen.dart';
import 'placeholder_screen.dart';
import 'offline_assistant_screen.dart';
import 'build_screen.dart';
import 'settings_screen.dart';
import 'talkback_screen.dart';
import 'reply_agent_screen.dart';
import 'contacts_screen.dart';
import 'messaging_screen.dart';
import 'file_manager_screen.dart';
import 'activity_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with TickerProviderStateMixin {
  String _currentRoute = '/home';

  void _onNavigate(String route) {
    setState(() => _currentRoute = route);
    if (Navigator.canPop(context)) {
      Navigator.pop(context); // Close drawer
    }
    _fadeCtrl.forward(from: 0);
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
        drawer: JarvisDrawer(
          currentRoute: _currentRoute,
          onSelect: _onNavigate,
        ),
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
          child: _buildBody(),
        ),
      ),
    );
  }

  Widget _buildBody() {
    switch (_currentRoute) {
      case '/home':
        return _DashboardTab(
          onOpen: _openScreen,
          features: _features,
          backendConnected: _backendConnected,
          backendModel: _backendModel,
          backendType: _backendType,
          backendUrl: _backendUrl,
          backendMessage: _backendMessage,
          onNavigate: (r) => setState(() => _currentRoute = r),
        );
      case '/chat':
        return const ChatScreen();
      case '/voice':
        return const OfflineAssistantScreen();
      case '/models':
        return const ModelManagementScreen();
      case '/agents':
        return const AgentDashboardScreen();
      case '/automation':
        return const AutomationScreen();
      case '/memory':
        return const MemoryDashboardScreen();
      case '/skills':
        return const PlaceholderScreen(title: 'Skills');
      case '/plugins':
        return const PlaceholderScreen(title: 'Plugins');
      case '/integrations':
        return const IntegrationManagementScreen();
      case '/projects':
        return const BuildScreen();
      case '/diagnostics':
        return const DiagnosticsDashboardScreen();
      case '/settings':
        return const SettingsScreen();
      default:
        return const Center(child: Text('404'));
    }
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
  final Function(String) onNavigate;

  const _DashboardTab({
    required this.onOpen,
    required this.features,
    required this.backendConnected,
    required this.backendModel,
    required this.backendType,
    required this.backendUrl,
    required this.backendMessage,
    required this.onNavigate,
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
        icon: Icons.chat_bubble_outline,
        title: 'Chat',
        sub: 'Multi-model orchestration',
        color: JarvisColors.cyan,
        onTap: () => onNavigate('/chat'),
      ),
      _LaunchTile(
        icon: Icons.mic_none_outlined,
        title: 'Voice',
        sub: 'Offline speech loop',
        color: JarvisColors.green,
        onTap: () => onNavigate('/voice'),
      ),
      _LaunchTile(
        icon: Icons.psychology_outlined,
        title: 'Models',
        sub: 'Provider management',
        color: JarvisColors.orange,
        onTap: () => onNavigate('/models'),
      ),
      _LaunchTile(
        icon: Icons.construction_outlined,
        title: 'Projects',
        sub: 'Build & Automation',
        color: JarvisColors.blue,
        onTap: () => onNavigate('/projects'),
      ),
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
                        'One assistant surface. Access all JARVIS capabilities from this unified interface.',
                        style: J.shareTech(12, color: JarvisColors.textSecondary),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          JPanel(
            label: 'QUICK ACTIONS',
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
            label: 'CORE SYSTEMS',
            child: Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _MiniAction('Registry', Icons.list_alt_outlined,
                    () => onOpen(const FeatureRegistryScreen())),
                _MiniAction('Agents', Icons.group_outlined,
                    () => onNavigate('/agents')),
                _MiniAction('Automation', Icons.auto_awesome_outlined,
                    () => onNavigate('/automation')),
                _MiniAction('Integrations', Icons.hub_outlined,
                    () => onNavigate('/integrations')),
                _MiniAction('Diagnostics', Icons.analytics_outlined,
                    () => onNavigate('/diagnostics')),
              ],
            ),
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
        ],
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
      onTap: onTap,
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
