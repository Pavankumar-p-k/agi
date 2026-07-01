import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_theme.dart';

class JarvisDrawer extends StatelessWidget {
  final String currentRoute;
  final Function(String) onSelect;

  const JarvisDrawer({
    super.key,
    required this.currentRoute,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: JarvisColors.bgCard,
      child: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: ListView(
              padding: EdgeInsets.zero,
              children: [
                _buildItem(Icons.home_outlined, 'HOME', '/home'),
                _buildItem(Icons.chat_bubble_outline, 'CHAT', '/chat'),
                _buildItem(Icons.mic_none_outlined, 'VOICE', '/voice'),
                _buildItem(Icons.psychology_outlined, 'MODELS', '/models'),
                _buildItem(Icons.group_outlined, 'AGENTS', '/agents'),
                _buildItem(Icons.auto_awesome_outlined, 'AUTOMATION', '/automation'),
                _buildItem(Icons.memory_outlined, 'MEMORY', '/memory'),
                _buildItem(Icons.bolt_outlined, 'SKILLS', '/skills'),
                _buildItem(Icons.extension_outlined, 'PLUGINS', '/plugins'),
                _buildItem(Icons.hub_outlined, 'INTEGRATIONS', '/integrations'),
                _buildItem(Icons.construction_outlined, 'PROJECTS', '/projects'),
                _buildItem(Icons.analytics_outlined, 'DIAGNOSTICS', '/diagnostics'),
                const Divider(color: JarvisColors.border),
                _buildItem(Icons.settings_outlined, 'SETTINGS', '/settings'),
              ],
            ),
          ),
          _buildFooter(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return DrawerHeader(
      decoration: const BoxDecoration(
        color: JarvisColors.bgPanel,
        border: Border(bottom: BorderSide(color: JarvisColors.cyan, width: 2)),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const HudRing(size: 60),
            const SizedBox(height: 12),
            Text(
              'J.A.R.V.I.S',
              style: GoogleFonts.orbitron(
                fontSize: 18,
                color: JarvisColors.cyan,
                fontWeight: FontWeight.bold,
                letterSpacing: 4,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildItem(IconData icon, String label, String route) {
    final selected = currentRoute == route;
    return ListTile(
      leading: Icon(
        icon,
        color: selected ? JarvisColors.cyan : JarvisColors.textDim,
        size: 20,
      ),
      title: Text(
        label,
        style: GoogleFonts.orbitron(
          fontSize: 11,
          color: selected ? JarvisColors.cyan : JarvisColors.textSecondary,
          letterSpacing: 1.5,
          fontWeight: selected ? FontWeight.bold : FontWeight.normal,
        ),
      ),
      selected: selected,
      selectedTileColor: JarvisColors.cyan.withValues(alpha: 0.05),
      onTap: () => onSelect(route),
    );
  }

  Widget _buildFooter() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: JarvisColors.border)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            'v0.1.0-BETA',
            style: GoogleFonts.shareTech(fontSize: 10, color: JarvisColors.textDim),
          ),
          const StatusDot(active: true, color: JarvisColors.green),
        ],
      ),
    );
  }
}

class HudRing extends StatelessWidget {
  final double size;
  const HudRing({super.key, required this.size});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: JarvisColors.cyan.withValues(alpha: 0.4), width: 1),
      ),
      padding: const EdgeInsets.all(4),
      child: Container(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: JarvisColors.cyan, width: 2),
        ),
        child: Center(
          child: Container(
            width: size * 0.4,
            height: size * 0.4,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: JarvisColors.cyan,
            ),
          ),
        ),
      ),
    );
  }
}

class StatusDot extends StatelessWidget {
  final bool active;
  final Color color;
  const StatusDot({super.key, required this.active, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: active ? color : JarvisColors.textDim,
        boxShadow: active ? [BoxShadow(color: color, blurRadius: 4)] : null,
      ),
    );
  }
}
