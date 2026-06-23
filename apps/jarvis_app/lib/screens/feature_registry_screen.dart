import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class FeatureRegistryScreen extends StatefulWidget {
  const FeatureRegistryScreen({super.key});

  @override
  State<FeatureRegistryScreen> createState() => _FeatureRegistryScreenState();
}

class _FeatureRegistryScreenState extends State<FeatureRegistryScreen> {
  final ApiService _api = ApiService();
  List<Feature> _features = [];
  bool _loading = true;
  String _filter = 'all';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final features = await _api.getFeatures();
    setState(() {
      _features = features;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filter == 'all'
        ? _features
        : _features.where((f) => f.category == _filter).toList();

    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text('FEATURE REGISTRY', style: J.orbitron(14, spacing: 4)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: Column(
        children: [
          _buildFilterBar(),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
                : filtered.isEmpty
                    ? _buildEmpty()
                    : ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: filtered.length,
                        itemBuilder: (ctx, i) => _FeatureTile(
                          feature: filtered[i],
                          onToggle: (val) async {
                            final ok = await _api.toggleFeature(filtered[i].slug, val);
                            if (ok) _load();
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    final categories = ['all', ..._features.map((f) => f.category).toSet()];
    return Container(
      height: 50,
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: JarvisColors.border)),
      ),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: categories.length,
        itemBuilder: (ctx, i) {
          final cat = categories[i];
          final selected = _filter == cat;
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(cat.toUpperCase(), style: J.orbitron(8, weight: selected ? FontWeight.bold : FontWeight.normal)),
              selected: selected,
              onSelected: (val) => setState(() => _filter = cat),
              selectedColor: JarvisColors.cyan.withValues(alpha: 0.2),
              backgroundColor: JarvisColors.bgPanel,
              labelStyle: TextStyle(color: selected ? JarvisColors.cyan : JarvisColors.textDim),
              shape: RoundedRectangleBorder(side: BorderSide(color: selected ? JarvisColors.cyan : JarvisColors.border)),
            ),
          );
        },
      ),
    );
  }

  Widget _buildEmpty() {
    return Center(
      child: Text('NO FEATURES FOUND', style: J.orbitron(10, color: JarvisColors.textDim)),
    );
  }
}

class _FeatureTile extends StatelessWidget {
  final Feature feature;
  final Function(bool) onToggle;

  const _FeatureTile({required this.feature, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final statusColor = _getStatusColor(feature.status);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: JPanel(
        accentColor: statusColor,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        feature.name.toUpperCase(),
                        style: J.orbitron(12, spacing: 0.8),
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          _StatusBadge(label: feature.status, color: statusColor),
                          const SizedBox(width: 8),
                          Text(
                            feature.category.toUpperCase(),
                            style: J.shareTech(10, color: JarvisColors.textDim),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                Switch(
                  value: feature.enabled,
                  onChanged: onToggle,
                  activeColor: JarvisColors.cyan,
                  activeTrackColor: JarvisColors.cyan.withValues(alpha: 0.2),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              feature.description,
              style: J.shareTech(12, color: JarvisColors.textSecondary),
            ),
            if (feature.dependencies.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'Depends on: ${feature.dependencies.join(", ")}',
                style: J.shareTech(10, color: JarvisColors.orange.withValues(alpha: 0.7)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Color _getStatusColor(String status) {
    switch (status.toLowerCase()) {
      case 'stable': return JarvisColors.green;
      case 'beta': return JarvisColors.cyan;
      case 'experimental': return JarvisColors.purple;
      case 'broken': return JarvisColors.red;
      case 'planned': return JarvisColors.textDim;
      default: return JarvisColors.textSecondary;
    }
  }
}

class _StatusBadge extends StatelessWidget {
  final String label;
  final Color color;
  const _StatusBadge({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: color.withValues(alpha: 0.5)),
        color: color.withValues(alpha: 0.1),
      ),
      child: Text(
        label.toUpperCase(),
        style: J.orbitron(7, color: color, weight: FontWeight.bold),
      ),
    );
  }
}
