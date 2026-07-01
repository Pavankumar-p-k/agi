import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class MemoryDashboardScreen extends StatefulWidget {
  const MemoryDashboardScreen({super.key});

  @override
  State<MemoryDashboardScreen> createState() => _MemoryDashboardScreenState();
}

class _MemoryDashboardScreenState extends State<MemoryDashboardScreen> {
  final ApiService _api = ApiService();
  List<dynamic> _memories = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final stats = await _api.getMemoryStats();
      if (stats != null) {
        final categories = stats['by_category'] as Map<String, dynamic>?;
        if (categories != null && categories.isNotEmpty) {
          _memories = categories.entries.map((e) => {
            'title': e.key.toUpperCase(),
            'count': e.value is int ? e.value : (e.value as num).toInt(),
            'desc': 'Category: ${e.key}',
          }).toList();
        } else if (stats['total'] != null) {
          final total = stats['total'] is int ? stats['total'] : (stats['total'] as num).toInt();
          _memories = [
            {'title': 'MEMORY ENTRIES', 'count': total, 'desc': 'Total stored knowledge items.'},
          ];
        }
      }
    } catch (e) {
      debugPrint('[MemoryDashboard] load error: $e');
    }
    if (_memories.isEmpty) {
      _memories = [
        {'title': 'NO DATA', 'count': 0, 'desc': 'Memory data unavailable — check backend connection.'},
      ];
    }
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: Text('MEMORY SYSTEM', style: J.orbitron(14, spacing: 4)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _memories.length,
              itemBuilder: (ctx, i) => _MemoryTile(data: _memories[i]),
            ),
    );
  }
}

class _MemoryTile extends StatelessWidget {
  final Map<String, dynamic> data;
  const _MemoryTile({required this.data});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: JPanel(
        accentColor: JarvisColors.purple,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(data['title'], style: J.orbitron(12, spacing: 1.2)),
                _CountBadge(count: data['count']),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              data['desc'],
              style: J.shareTech(12, color: JarvisColors.textSecondary),
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () {},
                  child: Text('VIEW DETAILS', style: J.orbitron(8, color: JarvisColors.cyan)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CountBadge extends StatelessWidget {
  final int count;
  const _CountBadge({required this.count});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: JarvisColors.purple.withValues(alpha: 0.1),
        border: Border.all(color: JarvisColors.purple.withValues(alpha: 0.4)),
      ),
      child: Text(
        '$count ENTRIES',
        style: J.orbitron(8, color: JarvisColors.purple, weight: FontWeight.bold),
      ),
    );
  }
}

