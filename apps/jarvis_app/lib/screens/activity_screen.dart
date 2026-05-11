// lib/screens/activity_screen.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';


class ActivityScreen extends StatefulWidget {
  const ActivityScreen({super.key});
  @override State<ActivityScreen> createState() => _ActivityScreenState();
}

class _ActivityScreenState extends State<ActivityScreen> {
  final _api = ApiService();
  List<Activity> _activities = [];
  DailySummary?  _summary;
  bool _loading = true;

  @override void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([_api.getTodayActivity(), _api.getDailySummary()]);
      _activities = results[0] as List<Activity>;
      _summary    = results[1] as DailySummary;
    } catch (_) {}
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ACTIVITY'), actions: [
        IconButton(icon: const Icon(Icons.refresh_outlined, color: JarvisColors.cyan), onPressed: _load),
      ]),
      body: _loading
        ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1.5))
        : ListView(padding: const EdgeInsets.all(16), children: [
            if (_summary != null) ...[
              JPanel(label: 'TODAY\'S SUMMARY', child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(_summary!.summary, style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textPrimary, height: 1.6)),
                const SizedBox(height: 14),
                MetricBar(label: 'PRODUCTIVITY', value: _summary!.productivityScore / 10),
                const SizedBox(height: 16),
                if (_summary!.insights.isNotEmpty) ...[
                  Text('// INSIGHTS', style: GoogleFonts.orbitron(fontSize: 9, letterSpacing: 2, color: JarvisColors.cyan.withOpacity(0.7))),
                  const SizedBox(height: 8),
                  ..._summary!.insights.map((ins) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('▸ ', style: GoogleFonts.shareTech(color: JarvisColors.cyan, fontSize: 13)),
                      Expanded(child: Text(ins, style: GoogleFonts.shareTech(fontSize: 12, color: JarvisColors.textPrimary, height: 1.4))),
                    ]),
                  )),
                ],
              ])),
              const SizedBox(height: 16),
            ],
            JPanel(label: 'ACTIVITY LOG (${_activities.length})', child: _activities.isEmpty
              ? Text('No activities recorded today', style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textSecondary))
              : Column(children: _activities.reversed.map((a) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Container(
                      width: 4, height: 4,
                      margin: const EdgeInsets.only(top: 7, right: 10),
                      decoration: const BoxDecoration(shape: BoxShape.circle, color: JarvisColors.cyan),
                    ),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(a.description, style: GoogleFonts.shareTech(fontSize: 12, color: JarvisColors.textPrimary)),
                      Text(DateFormat('HH:mm').format(a.timestamp),
                        style: GoogleFonts.orbitron(fontSize: 9, color: JarvisColors.textSecondary, letterSpacing: 1)),
                    ])),
                  ]),
                )).toList()),
            ),
          ]),
    );
  }
}


// ════════════════════════════════════════
//  MESSAGING SCREEN
// ════════════════════════════════════════
