// lib/screens/build_screen.dart
// Build Dashboard: project tracking, quality scores, governor decisions, environment
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../widgets/jarvis_widgets.dart';

class BuildScreen extends StatefulWidget {
  const BuildScreen({super.key});

  @override
  State<BuildScreen> createState() => _BuildScreenState();
}

class _BuildScreenState extends State<BuildScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;
  List<BuildProject> _projects = [];
  BuildDetail? _selectedDetail;
  List<GovernorDecision> _governorDecisions = [];
  EnvironmentSnapshot? _env;
  SystemIdentity? _identity;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 4, vsync: this);
    _refresh();
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      final api = context.read<ApiService>();
      final results = await Future.wait([
        api.getBuildProjects(),
        api.getEnvironment(),
        api.getSystemIdentity(),
      ]);
      setState(() {
        _projects = results[0] as List<BuildProject>;
        _env = results[1] as EnvironmentSnapshot?;
        _identity = results[2] as SystemIdentity?;
        _error = null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
    setState(() => _loading = false);
  }

  Future<void> _selectProject(String name) async {
    final api = context.read<ApiService>();
    final detail = await api.getBuildDetail(name);
    final decisions = await api.getGovernorHistory(name);
    setState(() {
      _selectedDetail = detail;
      _governorDecisions = decisions;
    });
    if (mounted) {
      _showProjectDetail(context, name);
    }
  }

  void _showProjectDetail(BuildContext context, String name) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF0D1117),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.85,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        expand: false,
        builder: (_, scrollCtrl) => _ProjectDetailSheet(
          detail: _selectedDetail,
          decisions: _governorDecisions,
          scrollController: scrollCtrl,
          projectName: name,
        ),
      ),
    );
  }

  IconData _statusIcon(String status) {
    switch (status) {
      case 'done': return Icons.check_circle;
      case 'failed': return Icons.error;
      case 'building': return Icons.construction;
      case 'paused': return Icons.pause_circle;
      case 'cancelled': return Icons.cancel;
      default: return Icons.radio_button_unchecked;
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'done': return const Color(0xFF00C853);
      case 'failed': return const Color(0xFFFF1744);
      case 'building': return const Color(0xFF2979FF);
      case 'paused': return const Color(0xFFFFD600);
      case 'cancelled': return const Color(0xFF9E9E9E);
      default: return const Color(0xFF757575);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0E17),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D1117),
        title: const Text('Build Dashboard', style: TextStyle(fontWeight: FontWeight.w600)),
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: const Color(0xFF2979FF),
          labelColor: Colors.white,
          unselectedLabelColor: Colors.grey,
          tabs: const [
            Tab(icon: Icon(Icons.construction), text: 'Projects'),
            Tab(icon: Icon(Icons.assessment), text: 'Quality'),
            Tab(icon: Icon(Icons.account_tree), text: 'Governor'),
            Tab(icon: Icon(Icons.monitor_heart), text: 'Environment'),
          ],
        ),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh),
        ],
      ),
      body: _loading
          ? const Center(child: JLoading())
          : TabBarView(
              controller: _tabCtrl,
              children: [
                _buildProjectsTab(),
                _buildQualityTab(),
                _buildGovernorTab(),
                _buildEnvironmentTab(),
              ],
            ),
    );
  }

  Widget _buildProjectsTab() {
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text('Server offline', style: TextStyle(color: Colors.grey[400])),
          ],
        ),
      );
    }
    if (_projects.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.build_outlined, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text('No projects yet', style: TextStyle(color: Colors.grey[400])),
            const SizedBox(height: 4),
            Text('Use /build <goal> in the CLI', style: TextStyle(color: Colors.grey[600], fontSize: 12)),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _projects.length,
        itemBuilder: (_, i) {
          final p = _projects[i];
          return Card(
            color: const Color(0xFF161B22),
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              leading: Icon(_statusIcon(p.status), color: _statusColor(p.status)),
              title: Text(p.name, style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text(
                p.goal.length > 60 ? '${p.goal.substring(0, 60)}...' : p.goal,
                style: TextStyle(color: Colors.grey[400], fontSize: 12),
              ),
              trailing: Text('${p.status}  r${p.retries}',
                  style: TextStyle(color: Colors.grey[500], fontSize: 11)),
              onTap: () => _selectProject(p.name),
            ),
          );
        },
      ),
    );
  }

  Widget _buildQualityTab() {
    if (_projects.isEmpty) {
      return Center(child: Text('No projects to score', style: TextStyle(color: Colors.grey[400])));
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text('Quality Scores', style: TextStyle(color: Colors.grey[300], fontSize: 16, fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        ..._projects.map((p) => _QualityTile(project: p, api: context.read<ApiService>())),
      ],
    );
  }

  Widget _buildGovernorTab() {
    if (_projects.isEmpty) {
      return Center(child: Text('Select a project to see governor history',
          style: TextStyle(color: Colors.grey[400])));
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text('Governor History', style: TextStyle(color: Colors.grey[300], fontSize: 16, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Text('Tap a project to view its governor decisions',
            style: TextStyle(color: Colors.grey[500], fontSize: 12)),
        const SizedBox(height: 8),
        ..._projects.map((p) => Card(
          color: const Color(0xFF161B22),
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            leading: const Icon(Icons.account_tree, color: Color(0xFF2979FF)),
            title: Text(p.name),
            subtitle: Text('${p.status}, retries: ${p.retries}',
                style: TextStyle(color: Colors.grey[400], fontSize: 12)),
            trailing: const Icon(Icons.chevron_right, color: Colors.grey),
            onTap: () async {
              final api = context.read<ApiService>();
              final decisions = await api.getGovernorHistory(p.name);
              setState(() => _governorDecisions = decisions);
              if (mounted) {
                showDialog(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    backgroundColor: const Color(0xFF0D1117),
                    title: Text('Governor: ${p.name}'),
                    content: SizedBox(
                      width: double.maxFinite,
                      child: decisions.isEmpty
                          ? Text('No decisions recorded',
                              style: TextStyle(color: Colors.grey[400]))
                          : ListView.builder(
                              shrinkWrap: true,
                              itemCount: decisions.length,
                              itemBuilder: (_, i) {
                                final d = decisions[i];
                                return ListTile(
                                  dense: true,
                                  leading: Icon(
                                    d.action == 'abort' ? Icons.block :
                                    d.action == 'retry' ? Icons.refresh :
                                    d.action == 'replan' ? Icons.edit :
                                    Icons.swap_horiz,
                                    color: d.action == 'abort' ? Colors.red[300] :
                                           d.action == 'retry' ? Colors.blue[300] : Colors.amber[300],
                                    size: 18,
                                  ),
                                  title: Text(d.action, style: const TextStyle(fontSize: 14)),
                                  subtitle: Text(d.reason, style: TextStyle(color: Colors.grey[400], fontSize: 11)),
                                  trailing: Text('${d.confidence.toStringAsFixed(2)}',
                                      style: TextStyle(color: Colors.grey[500], fontSize: 12)),
                                );
                              },
                            ),
                    ),
                    actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
                  ),
                );
              }
            },
          ),
        )),
      ],
    );
  }

  Widget _buildEnvironmentTab() {
    if (_env == null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text('Environment data unavailable', style: TextStyle(color: Colors.grey[400])),
          ],
        ),
      );
    }
    final e = _env!;
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          MetricCard(
            label: 'JARVIS v${_identity?.version ?? "?"}',
            value: '${_identity?.capabilities.length ?? 0} capabilities',
            sub: '${_identity?.phasesImplemented.length ?? 0} phases',
            accent: const Color(0xFF2979FF),
            icon: Icons.memory,
          ),
          const SizedBox(height: 12),
          Text('System Health', style: TextStyle(color: Colors.grey[300], fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          _EnvRow('Disk', '${e.diskFreeGb.toStringAsFixed(1)} / ${e.diskTotalGb.toStringAsFixed(1)} GB',
              e.diskFreeGb < 5.0 ? Colors.red : Colors.green, Icons.storage),
          _EnvRow('Memory', '${e.memoryFreeMb.toStringAsFixed(0)} / ${e.memoryTotalMb.toStringAsFixed(0)} MB',
              e.memoryFreeMb < 500 ? Colors.red : Colors.green, Icons.memory),
          _EnvRow('Ollama', e.ollamaAvailable ? '${e.ollamaLatencyMs.toStringAsFixed(0)} ms' : 'Offline',
              e.ollamaAvailable ? Colors.green : Colors.red, Icons.smart_toy),
          _EnvRow('Network', e.networkReachable ? 'Connected' : 'Disconnected',
              e.networkReachable ? Colors.green : Colors.red, Icons.wifi),
          if (e.warnings.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text('Warnings', style: TextStyle(color: Colors.orange[300], fontSize: 14, fontWeight: FontWeight.w600)),
            ...e.warnings.map((w) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(children: [
                const Icon(Icons.warning_amber, color: Colors.orange, size: 16),
                const SizedBox(width: 8),
                Expanded(child: Text(w, style: TextStyle(color: Colors.orange[200], fontSize: 12))),
              ]),
            )),
          ],
        ],
      ),
    );
  }
}

class _QualityTile extends StatefulWidget {
  final BuildProject project;
  final ApiService api;
  const _QualityTile({required this.project, required this.api});

  @override
  State<_QualityTile> createState() => _QualityTileState();
}

class _QualityTileState extends State<_QualityTile> {
  BuildDetail? _detail;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final d = await widget.api.getBuildDetail(widget.project.name);
      setState(() { _detail = d; _loading = false; });
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return Card(
        color: const Color(0xFF161B22),
        margin: const EdgeInsets.only(bottom: 8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              const Icon(Icons.error_outline, color: Colors.red, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Load failed: ' + (_error!.length > 40 ? '...' + _error!.substring(_error!.length - 37) : _error!),
                  style: TextStyle(color: Colors.grey[400], fontSize: 12),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.refresh, size: 16),
                onPressed: _load,
                padding: EdgeInsets.zero,
                constraints: BoxConstraints(),
              ),
            ],
          ),
        ),
      );
    }
    final qs = _detail?.qualityScore;
    return Card(
      color: const Color(0xFF161B22),
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.analytics, size: 16, color: Color(0xFF2979FF)),
                const SizedBox(width: 8),
                Text(widget.project.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                const Spacer(),
                if (_loading) const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            if (qs != null) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: qs.average / 10.0,
                  backgroundColor: Colors.grey[800],
                  color: qs.average >= 7 ? const Color(0xFF00C853) :
                         qs.average >= 4 ? const Color(0xFFFFD600) : const Color(0xFFFF1744),
                  minHeight: 6,
                ),
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  _ScoreChip('Design', qs.designConsistency),
                  _ScoreChip('Resp', qs.responsiveness),
                  _ScoreChip('Content', qs.contentQuality),
                  _ScoreChip('Nav', qs.navigationQuality),
                  _ScoreChip('Code', qs.codeQuality),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ScoreChip extends StatelessWidget {
  final String label;
  final double score;
  const _ScoreChip(this.label, this.score);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: const Color(0xFF21262D),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text('$label ${score.toStringAsFixed(1)}',
            style: TextStyle(fontSize: 10, color: Colors.grey[400])),
      ),
    );
  }
}

class _EnvRow extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  final IconData icon;
  const _EnvRow(this.label, this.value, this.color, this.icon);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(width: 10),
          Text(label, style: TextStyle(color: Colors.grey[400], fontSize: 13)),
          const Spacer(),
          Text(value, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

class _ProjectDetailSheet extends StatelessWidget {
  final BuildDetail? detail;
  final List<GovernorDecision> decisions;
  final ScrollController scrollController;
  final String projectName;

  const _ProjectDetailSheet({
    required this.detail,
    required this.decisions,
    required this.scrollController,
    required this.projectName,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: ListView(
        controller: scrollController,
        children: [
          Center(
            child: Container(
              width: 40, height: 4,
              decoration: BoxDecoration(
                color: Colors.grey[600],
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(projectName, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text(detail?.goal ?? '', style: TextStyle(color: Colors.grey[400], fontSize: 14)),
          const SizedBox(height: 16),
          if (detail != null) ...[
            Row(children: [
              _InfoChip('Status', detail!.status),
              _InfoChip('Retries', '${detail!.retries}/${detail!.maxRetries}'),
              _InfoChip('Issues', '${detail!.issues.length}'),
            ]),
            const SizedBox(height: 16),
            if (detail!.issues.isNotEmpty) ...[
              Text('Issues', style: TextStyle(color: Colors.grey[300], fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              ...detail!.issues.map((iss) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  const Icon(Icons.bug_report, size: 14, color: Colors.red),
                  const SizedBox(width: 6),
                  Expanded(child: Text(iss, style: TextStyle(color: Colors.grey[400], fontSize: 12))),
                ]),
              )),
            ],
            if (detail!.qualityScore != null) ...[
              const SizedBox(height: 16),
              Text('Quality Score', style: TextStyle(color: Colors.grey[300], fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              Text('${detail!.qualityScore!.average.toStringAsFixed(1)}/10',
                  style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Color(0xFF2979FF))),
            ],
            if (detail!.partialProgress != null) ...[
              const SizedBox(height: 16),
              Text('Progress', style: TextStyle(color: Colors.grey[300], fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              LinearProgressIndicator(
                value: ((detail!.partialProgress!['overall'] as num?)?.toDouble() ?? 0) / 100,
                backgroundColor: Colors.grey[800],
                color: const Color(0xFF2979FF),
              ),
              Text('${detail!.partialProgress!['overall']?.toStringAsFixed(1) ?? "?"}%',
                  style: TextStyle(color: Colors.grey[400], fontSize: 12)),
            ],
            if (decisions.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Governor Decisions (${decisions.length})',
                  style: TextStyle(color: Colors.grey[300], fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              ...decisions.reversed.take(5).map((d) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  Icon(
                    d.action == 'abort' ? Icons.block :
                    d.action == 'retry' ? Icons.refresh : Icons.swap_horiz,
                    size: 16, color: Colors.grey,
                  ),
                  const SizedBox(width: 6),
                  Text('${d.action} (${d.confidence.toStringAsFixed(2)})',
                      style: TextStyle(color: Colors.grey[300], fontSize: 13)),
                  const Spacer(),
                  Text(d.reason, style: TextStyle(color: Colors.grey[500], fontSize: 11)),
                ]),
              )),
            ],
          ],
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final String label;
  final String value;
  const _InfoChip(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: Colors.grey[500], fontSize: 11)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
        ],
      ),
    );
  }
}
