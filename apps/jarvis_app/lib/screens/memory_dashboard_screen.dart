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
    // Note: This endpoint might need user_id, using sessionId as fallback
    try {
      final res = await ApiService().isOnline();
      if (res) {
        // Mocking for now since we don't have a clear model for Memory in Flutter yet
        await Future.delayed(const Duration(milliseconds: 800));
        _memories = [
          {'title': 'FAILURE MEMORY', 'count': 12, 'desc': 'Automated repair logs and retry histories.'},
          {'title': 'ARCHITECTURAL MEMORY', 'count': 5, 'desc': 'Codebase patterns and structural insights.'},
          {'title': 'USER PREFERENCES', 'count': 24, 'desc': 'Learned habits and preferred models.'},
          {'title': 'SKILL ACQUISITION', 'count': 8, 'desc': 'Newly learned tool usage patterns.'},
        ];
      }
    } catch (_) {}
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
