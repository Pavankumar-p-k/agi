import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class IntegrationManagementScreen extends StatefulWidget {
  const IntegrationManagementScreen({super.key});

  @override
  State<IntegrationManagementScreen> createState() => _IntegrationManagementScreenState();
}

class _IntegrationManagementScreenState extends State<IntegrationManagementScreen> {
  final ApiService _api = ApiService();
  List<Integration> _integrations = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final list = await _api.getIntegrations();
    setState(() {
      _integrations = list;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text('INTEGRATIONS', style: J.orbitron(14, spacing: 4)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _integrations.length,
              itemBuilder: (ctx, i) => _IntegrationTile(
                integration: _integrations[i],
                onToggle: (connected) async {
                  if (connected) {
                    // In a real app, this would open a dialog for credentials
                    // For now, we assume simple connection or OAuth
                    await _api.connectIntegration(_integrations[i].name, {});
                  } else {
                    await _api.disconnectIntegration(_integrations[i].name);
                  }
                  _load();
                },
              ),
            ),
    );
  }
}

class _IntegrationTile extends StatelessWidget {
  final Integration integration;
  final Function(bool) onToggle;

  const _IntegrationTile({required this.integration, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final connected = integration.connected;
    final healthy = integration.healthy;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: JPanel(
        accentColor: connected ? (healthy ? JarvisColors.green : JarvisColors.orange) : JarvisColors.textDim,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  _getIcon(integration.name),
                  color: connected ? JarvisColors.cyan : JarvisColors.textDim,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        integration.name.toUpperCase(),
                        style: J.orbitron(12, spacing: 0.8),
                      ),
                      Row(
                        children: [
                          Container(
                            width: 6, height: 6,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: connected ? (healthy ? JarvisColors.green : JarvisColors.orange) : JarvisColors.red,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            connected ? (healthy ? 'HEALTHY' : 'ERROR') : 'DISCONNECTED',
                            style: J.shareTech(9, color: JarvisColors.textDim),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                Switch(
                  value: connected,
                  onChanged: onToggle,
                  activeColor: JarvisColors.green,
                ),
              ],
            ),
            if (connected && !healthy && integration.error != null) ...[
              const SizedBox(height: 8),
              Text(
                'Error: ${integration.error}',
                style: J.shareTech(10, color: JarvisColors.red.withValues(alpha: 0.7)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  IconData _getIcon(String name) {
    switch (name.toLowerCase()) {
      case 'gmail': return Icons.mail_outline;
      case 'telegram': return Icons.telegram;
      case 'whatsapp': return Icons.chat_bubble_outline;
      case 'discord': return Icons.discord;
      case 'slack': return Icons.alternate_email;
      case 'github': return Icons.code;
      case 'google_drive': return Icons.cloud_outlined;
      default: return Icons.hub_outlined;
    }
  }
}

