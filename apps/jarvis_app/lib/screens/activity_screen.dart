import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class ActivityScreen extends StatefulWidget {
  const ActivityScreen({super.key});
  @override
  State<ActivityScreen> createState() => _ActivityScreenState();
}

class _ActivityScreenState extends State<ActivityScreen> {
  final _api = ApiService();
  List<Map<String, dynamic>> _activities = [];
  Map<String, dynamic> _counts = {};
  bool _loading = true;
  bool _showDetail = false;
  String? _selectedId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        _api.getActivities(),
        _api.getActivityCounts(),
      ]);
      setState(() {
        _activities = results[0] as List<Map<String, dynamic>>;
        _counts = results[1] as Map<String, dynamic>;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'RUNNING': return Colors.green;
      case 'PENDING': return Colors.orange;
      case 'SUSPENDED': return Colors.blue;
      case 'FAILED': return Colors.red;
      case 'COMPLETED': return Colors.grey;
      case 'CANCELLED': return Colors.grey.shade600;
      default: return Colors.white;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: JarvisColors.bg,
      appBar: AppBar(
        title: const Text('Activity Graph', style: TextStyle(fontFamily: 'Share Tech', letterSpacing: 1.0)),
        backgroundColor: JarvisColors.bgCard,
        foregroundColor: JarvisColors.cyan,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
          if (_showDetail)
            IconButton(
              icon: const Icon(Icons.arrow_back),
              onPressed: () => setState(() => _showDetail = false),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan))
          : _showDetail
              ? _ActivityDetailView(
                  id: _selectedId!,
                  api: _api,
                  onBack: () => setState(() => _showDetail = false),
                  onRefresh: _load,
                )
              : _buildList(),
    );
  }

  Widget _buildList() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              _countChip('Total', _counts['total'] ?? 0, Colors.grey),
              _countChip('Running', _counts['running'] ?? 0, Colors.green),
              _countChip('Pending', _counts['pending'] ?? 0, Colors.orange),
              _countChip('Failed', _counts['failed'] ?? 0, Colors.red),
              _countChip('Suspended', _counts['suspended'] ?? 0, Colors.blue),
              _countChip('Completed', _counts['completed'] ?? 0, Colors.grey.shade600),
            ],
          ),
        ),
        Expanded(
          child: _activities.isEmpty
              ? const Center(child: Text('No active activities', style: TextStyle(color: JarvisColors.textSecondary)))
              : ListView.builder(
                  itemCount: _activities.length,
                  itemBuilder: (context, index) {
                    final a = _activities[index];
                    final status = a['status'] as String? ?? '';
                    final id = a['node_id'] as String? ?? '';
                    final label = a['label'] as String? ?? '';
                    final type = a['node_type'] as String? ?? '';
                    final agent = a['agent_id'] as String?;
                    return Card(
                      color: JarvisColors.bgCard,
                      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      child: ListTile(
                        title: Text(label.length > 60 ? '${label.substring(0, 60)}...' : label,
                            style: const TextStyle(color: JarvisColors.textPrimary, fontSize: 14)),
                        subtitle: Text(
                          '$id  |  $type${agent != null ? '  |  $agent' : ''}',
                          style: const TextStyle(color: JarvisColors.textSecondary, fontSize: 11),
                        ),
                        trailing: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: _statusColor(status).withOpacity(0.2),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(status, style: TextStyle(color: _statusColor(status), fontSize: 11, fontWeight: FontWeight.bold)),
                        ),
                        onTap: () => setState(() {
                          _selectedId = id;
                          _showDetail = true;
                        }),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _countChip(String label, dynamic count, Color color) {
    final c = count is int ? count : (count is num ? count.toInt() : 0);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Text('$label: $c', style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.bold)),
    );
  }
}

class _ActivityDetailView extends StatefulWidget {
  final String id;
  final ApiService api;
  final VoidCallback onBack;
  final VoidCallback onRefresh;

  const _ActivityDetailView({
    required this.id,
    required this.api,
    required this.onBack,
    required this.onRefresh,
  });

  @override
  State<_ActivityDetailView> createState() => _ActivityDetailViewState();
}

class _ActivityDetailViewState extends State<_ActivityDetailView> {
  Map<String, dynamic>? _detail;
  Map<String, dynamic>? _summary;
  Map<String, dynamic>? _tree;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        widget.api.getActivityDetail(widget.id),
        widget.api.getActivitySummaryById(widget.id),
        widget.api.getActivityTree(widget.id),
      ]);
      setState(() {
        _detail = results[0] as Map<String, dynamic>;
        _summary = results[1] as Map<String, dynamic>;
        _tree = results[2] as Map<String, dynamic>;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'RUNNING': return Colors.green;
      case 'PENDING': return Colors.orange;
      case 'SUSPENDED': return Colors.blue;
      case 'FAILED': return Colors.red;
      case 'COMPLETED': return Colors.grey;
      case 'CANCELLED': return Colors.grey.shade600;
      default: return Colors.white;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: JarvisColors.cyan));
    }

    final detail = _detail;
    if (detail == null) {
      return const Center(child: Text('Activity not found', style: TextStyle(color: JarvisColors.textSecondary)));
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(detail['label'] as String? ?? '', style: const TextStyle(color: JarvisColors.cyan, fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          _detailRow('ID', detail['node_id'] as String? ?? ''),
          _detailRow('Type', detail['node_type'] as String? ?? ''),
          _detailRow('Status', detail['status'] as String? ?? ''),
          _detailRow('Depth', '${detail['depth'] ?? 0}'),
          if (detail['agent_id'] != null) _detailRow('Agent', detail['agent_id'] as String),
          if (detail['workflow_id'] != null) _detailRow('Workflow', detail['workflow_id'] as String),
          if (detail['parent_id'] != null) _detailRow('Parent', detail['parent_id'] as String),
          const SizedBox(height: 16),
          if (_summary != null) ...[
            const Text('Summary', style: TextStyle(color: JarvisColors.cyan, fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _detailRow('Total Nodes', '${_summary!['total_nodes'] ?? 0}'),
            _detailRow('Max Depth', '${_summary!['depth'] ?? 0}'),
            _detailRow('Agents', (_summary!['agents_used'] as List?)?.join(', ') ?? 'none'),
            if (_summary!['by_status'] != null) ...[
              const SizedBox(height: 4),
              const Text('By Status:', style: TextStyle(color: JarvisColors.textSecondary, fontSize: 13)),
              ...(_summary!['by_status'] as Map<String, dynamic>).entries.map((e) =>
                Padding(
                  padding: const EdgeInsets.only(left: 16, top: 2),
                  child: Text('${e.key}: ${e.value}', style: TextStyle(color: _statusColor(e.key), fontSize: 12)),
                ),
              ),
            ],
            const SizedBox(height: 16),
          ],
          if (_tree != null) ...[
            const Text('Tree', style: TextStyle(color: JarvisColors.cyan, fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _buildTreeView(_tree!),
            const SizedBox(height: 16),
          ],
          Row(
            children: [
              ElevatedButton.icon(
                onPressed: () => _action('pause'),
                icon: const Icon(Icons.pause, size: 16),
                label: const Text('Pause'),
                style: ElevatedButton.styleFrom(backgroundColor: Colors.orange, foregroundColor: Colors.black),
              ),
              const SizedBox(width: 8),
              ElevatedButton.icon(
                onPressed: () => _action('resume'),
                icon: const Icon(Icons.play_arrow, size: 16),
                label: const Text('Resume'),
                style: ElevatedButton.styleFrom(backgroundColor: Colors.green, foregroundColor: Colors.black),
              ),
              const SizedBox(width: 8),
              ElevatedButton.icon(
                onPressed: () => _action('cancel'),
                icon: const Icon(Icons.cancel, size: 16),
                label: const Text('Cancel'),
                style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _action(String action) async {
    try {
      if (action == 'pause') await widget.api.pauseActivity(widget.id);
      if (action == 'resume') await widget.api.resumeActivity(widget.id);
      if (action == 'cancel') await widget.api.cancelActivity(widget.id);
      widget.onRefresh();
      _load();
    } catch (e) {
      // ignore
    }
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text('$label:', style: const TextStyle(color: JarvisColors.textSecondary, fontSize: 13)),
          ),
          Expanded(
            child: Text(value, style: const TextStyle(color: JarvisColors.textPrimary, fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _buildTreeView(Map<String, dynamic> tree) {
    final nodes = (tree['nodes'] as List?) ?? [];
    if (nodes.isEmpty) return const Text('No nodes', style: TextStyle(color: JarvisColors.textSecondary));

    final Map<String, List> children = {};
    for (final n in nodes) {
      final p = (n as Map<String, dynamic>)['parent_id'] as String? ?? '';
      children.putIfAbsent(p, () => []).add(n);
    }

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: JarvisColors.bgCard,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: JarvisColors.border),
      ),
      child: _buildTreeNodes('', children, 0),
    );
  }

  Widget _buildTreeNodes(String parentId, Map<String, List> children, int indent) {
    final items = children[parentId];
    if (items == null || items.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: items.map((n) {
        final node = n as Map<String, dynamic>;
        final status = node['status'] as String? ?? '';
        final iconMap = <String, String>{
          'PENDING': '\u25CB', 'RUNNING': '\u25B6', 'COMPLETED': '\u2713',
          'FAILED': '\u2717', 'SUSPENDED': '\u23F8', 'CANCELLED': '\u2298',
        };
        final icon = iconMap[status] ?? '?';
        final label = node['label'] as String? ?? '';
        final type = node['node_type'] as String? ?? '';
        final agent = node['agent_id'] as String?;
        final displayLabel = label.length > 40 ? '${label.substring(0, 40)}...' : label;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsets.only(left: indent * 16.0),
              child: Text(
                '$icon $type: $displayLabel${agent != null ? ' [$agent]' : ''} [$status]',
                style: TextStyle(color: _statusColor(status), fontSize: 11, fontFamily: 'monospace'),
              ),
            ),
            _buildTreeNodes(node['node_id'] as String? ?? '', children, indent + 1),
          ],
        );
      }).toList(),
    );
  }
}
