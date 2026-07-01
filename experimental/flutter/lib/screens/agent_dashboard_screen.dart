import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class AgentDashboardScreen extends StatefulWidget {
  const AgentDashboardScreen({super.key});

  @override
  State<AgentDashboardScreen> createState() => _AgentDashboardScreenState();
}

class _AgentDashboardScreenState extends State<AgentDashboardScreen> {
  final ApiService _api = ApiService();
  List<Agent> _agents = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final list = await _api.getAgents();
    setState(() {
      _agents = list;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text('AGENT DASHBOARD', style: J.orbitron(14, spacing: 4)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _agents.length,
              itemBuilder: (ctx, i) => _AgentTile(agent: _agents[i]),
            ),
    );
  }
}

class _AgentTile extends StatelessWidget {
  final Agent agent;
  const _AgentTile({required this.agent});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: JPanel(
        accentColor: JarvisColors.cyan,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                HudRing(size: 40),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(agent.name, style: J.orbitron(14, spacing: 1.2)),
                      Text(
                        'MODES: ${agent.modes.join(", ")}'.toUpperCase(),
                        style: J.shareTech(9, color: JarvisColors.textDim),
                      ),
                    ],
                  ),
                ),
                StatusDot(active: true, color: JarvisColors.green),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              agent.description,
              style: J.shareTech(12, color: JarvisColors.textSecondary),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () {},
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: JarvisColors.border),
                    ),
                    child: Text('CONFIG', style: J.orbitron(8, color: JarvisColors.textDim)),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton(
                    onPressed: () {},
                    style: ElevatedButton.styleFrom(
                      backgroundColor: JarvisColors.cyan.withValues(alpha: 0.1),
                      side: const BorderSide(color: JarvisColors.cyan),
                    ),
                    child: Text('RUN TASK', style: J.orbitron(8, color: JarvisColors.cyan)),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

