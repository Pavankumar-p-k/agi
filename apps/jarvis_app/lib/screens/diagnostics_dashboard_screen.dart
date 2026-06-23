import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class DiagnosticsDashboardScreen extends StatefulWidget {
  const DiagnosticsDashboardScreen({super.key});

  @override
  State<DiagnosticsDashboardScreen> createState() => _DiagnosticsDashboardScreenState();
}

class _DiagnosticsDashboardScreenState extends State<DiagnosticsDashboardScreen> {
  final ApiService _api = ApiService();
  Map<String, dynamic> _data = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final data = await _api.getDiagnostics();
    setState(() {
      _data = data['data'] ?? {};
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text('DIAGNOSTICS', style: J.orbitron(14, spacing: 4)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _buildEnvironment(),
                  const SizedBox(height: 16),
                  _buildSystem(),
                  const SizedBox(height: 16),
                  _buildHealthGrid(),
                ],
              ),
            ),
    );
  }

  Widget _buildEnvironment() {
    final env = _data['environment'] ?? {};
    return JPanel(
      label: 'ENVIRONMENT',
      child: Column(
        children: [
          _buildDiagRow('Disk Free', '${env['disk_free_gb'] ?? '?'} GB'),
          _buildDiagRow('Memory Free', '${env['memory_free_mb'] ?? '?'} MB'),
          _buildDiagRow('Ollama', (env['ollama_available'] ?? false) ? 'ONLINE' : 'OFFLINE',
              color: (env['ollama_available'] ?? false) ? JarvisColors.green : JarvisColors.red),
          _buildDiagRow('Network', (env['network_reachable'] ?? false) ? 'CONNECTED' : 'OFFLINE',
              color: (env['network_reachable'] ?? false) ? JarvisColors.green : JarvisColors.red),
        ],
      ),
    );
  }

  Widget _buildSystem() {
    final sys = _data['system'] ?? {};
    return JPanel(
      label: 'SYSTEM INFO',
      child: Column(
        children: [
          _buildDiagRow('Hostname', sys['hostname'] ?? '?'),
          _buildDiagRow('Platform', sys['platform'] ?? '?'),
          _buildDiagRow('Python', sys['python'] ?? '?'),
          _buildDiagRow('Uptime', '${(sys['uptime_seconds'] ?? 0) ~/ 3600} hours'),
        ],
      ),
    );
  }

  Widget _buildHealthGrid() {
    final models = _data['models'] as Map? ?? {};
    final ints = _data['integrations'] as Map? ?? {};
    final voice = _data['voice'] ?? {};

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 1.5,
      children: [
        _HealthCard(label: 'MODELS', count: models.length,
            healthy: models.values.every((v) => v['healthy'] == true)),
        _HealthCard(label: 'INTEGRATIONS', count: ints.length,
            healthy: ints.values.every((v) => v['healthy'] == true)),
        _HealthCard(label: 'VOICE', healthy: voice['enabled'] ?? false),
        _HealthCard(label: 'FEATURES', healthy: true), // Placeholder
      ],
    );
  }

  Widget _buildDiagRow(String label, String value, {Color? color}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: J.shareTech(12, color: JarvisColors.textDim)),
          Text(value, style: J.shareTech(12, color: color ?? JarvisColors.textSecondary)),
        ],
      ),
    );
  }
}

class _HealthCard extends StatelessWidget {
  final String label;
  final int? count;
  final bool healthy;

  const _HealthCard({required this.label, this.count, required this.healthy});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: JarvisColors.bgPanel,
        border: Border.all(color: healthy ? JarvisColors.green.withValues(alpha: 0.3) : JarvisColors.red.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: J.orbitron(8, color: healthy ? JarvisColors.green : JarvisColors.red, spacing: 1.5)),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              if (count != null)
                Text('$count', style: J.orbitron(18, weight: FontWeight.bold)),
              Icon(
                healthy ? Icons.check_circle : Icons.error,
                color: healthy ? JarvisColors.green : JarvisColors.red,
                size: 20,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
