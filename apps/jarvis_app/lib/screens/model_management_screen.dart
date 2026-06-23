import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class ModelManagementScreen extends StatefulWidget {
  const ModelManagementScreen({super.key});

  @override
  State<ModelManagementScreen> createState() => _ModelManagementScreenState();
}

class _ModelManagementScreenState extends State<ModelManagementScreen> {
  final ApiService _api = ApiService();
  Map<String, dynamic> _info = {};
  Map<String, dynamic> _groups = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final info = await _api.getModelInfo();
    final groups = await _api.getModelGroups();
    setState(() {
      _info = info;
      _groups = groups;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text('MODEL MANAGEMENT', style: J.orbitron(14, spacing: 4)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildOllamaStatus(),
                  const SizedBox(height: 16),
                  _buildModelGroups(),
                  const SizedBox(height: 16),
                  _buildAvailableModels(),
                ],
              ),
            ),
    );
  }

  Widget _buildOllamaStatus() {
    final available = _info['ollama_available'] ?? false;
    return JPanel(
      label: 'OLLAMA BACKEND',
      accentColor: available ? JarvisColors.green : JarvisColors.red,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                available ? Icons.check_circle_outline : Icons.error_outline,
                color: available ? JarvisColors.green : JarvisColors.red,
                size: 16,
              ),
              const SizedBox(width: 8),
              Text(
                available ? 'ONLINE' : 'OFFLINE',
                style: J.orbitron(10, color: available ? JarvisColors.green : JarvisColors.red, weight: FontWeight.bold),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'URL: ${_info['ollama_url'] ?? 'N/A'}',
            style: J.shareTech(12, color: JarvisColors.textSecondary),
          ),
          if (!available && _info['ollama_error'] != null) ...[
            const SizedBox(height: 4),
            Text(
              'Error: ${_info['ollama_error']}',
              style: J.shareTech(10, color: JarvisColors.red.withValues(alpha: 0.7)),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildModelGroups() {
    final groups = _groups['groups'] as Map<String, dynamic>? ?? {};
    return JPanel(
      label: 'TASK ASSIGNMENTS',
      child: Column(
        children: groups.entries.map((e) => _buildGroupItem(e.key, e.value)).toList(),
      ),
    );
  }

  Widget _buildGroupItem(String task, String model) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(task.toUpperCase(), style: J.orbitron(9, color: JarvisColors.textDim)),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              model,
              style: J.shareTech(12, color: JarvisColors.cyan),
              textAlign: TextAlign.right,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAvailableModels() {
    final models = _info['models'] as List? ?? [];
    return JPanel(
      label: 'AVAILABLE MODELS',
      child: Column(
        children: models.map((m) => _buildModelTile(m)).toList(),
      ),
    );
  }

  Widget _buildModelTile(Map<String, dynamic> model) {
    final provider = model['provider'] ?? 'unknown';
    final isOllama = provider == 'ollama';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: JarvisColors.bgPanel,
        border: Border.all(color: JarvisColors.border),
      ),
      child: Row(
        children: [
          Icon(
            isOllama ? Icons.storage_outlined : Icons.cloud_queue_outlined,
            size: 18,
            color: isOllama ? JarvisColors.orange : JarvisColors.purple,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(model['name'] ?? 'Unknown', style: J.orbitron(10)),
                Text(provider.toUpperCase(), style: J.shareTech(9, color: JarvisColors.textDim)),
              ],
            ),
          ),
          if (isOllama && model['size'] != null)
            Text(
              '${(model['size'] / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB',
              style: J.shareTech(10, color: JarvisColors.textSecondary),
            ),
        ],
      ),
    );
  }
}
