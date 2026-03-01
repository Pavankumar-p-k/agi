import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:just_audio/just_audio.dart';

import '../services/call_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class CallLogScreen extends StatefulWidget {
  const CallLogScreen({super.key});

  @override
  State<CallLogScreen> createState() => _CallLogScreenState();
}

class _CallLogScreenState extends State<CallLogScreen>
    with TickerProviderStateMixin {
  final CallService _callService = CallService();
  final AudioPlayer _player = AudioPlayer();
  late TabController _tabs;
  StreamSubscription<Map<dynamic, dynamic>>? _eventsSub;

  List<CallRecord> _all = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _load();
    _eventsSub = _callService.recordsStream().listen((event) async {
      await _load();
      if (mounted && (event['important'] == true || event['important'] == 1)) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Important call message captured.')),
        );
      }
    });
  }

  @override
  void dispose() {
    _eventsSub?.cancel();
    _tabs.dispose();
    _player.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _all = await _callService.getAllRecords();
    } catch (_) {
      _all = const [];
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _playAudio(CallRecord record) async {
    if (record.audioPath.isEmpty) return;
    try {
      await _player.stop();
      await _player.setFilePath(record.audioPath);
      await _player.play();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Audio playback failed for this record.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final important = _all.where((e) => e.isImportant).toList();
    final unreadImportant = important.where((e) => !e.isRead).length;
    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('CALL GUARD'),
            if (unreadImportant > 0) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: const BoxDecoration(
                    color: JarvisColors.red, shape: BoxShape.rectangle),
                child: Text(
                  '$unreadImportant',
                  style:
                      GoogleFonts.orbitron(fontSize: 10, color: Colors.white),
                ),
              ),
            ],
          ],
        ),
        actions: [
          IconButton(
              onPressed: _load, icon: const Icon(Icons.refresh_outlined)),
        ],
        bottom: TabBar(
          controller: _tabs,
          indicatorColor: JarvisColors.cyan,
          tabs: const [
            Tab(text: 'IMPORTANT'),
            Tab(text: 'ALL'),
          ],
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: JarvisColors.cyan))
          : TabBarView(
              controller: _tabs,
              children: [
                _RecordList(
                  records: important,
                  onMarkRead: (id) async {
                    await _callService.markRead(id);
                    await _load();
                  },
                  onDelete: (id) async {
                    await _callService.deleteRecord(id);
                    await _load();
                  },
                  onPlay: _playAudio,
                ),
                _RecordList(
                  records: _all,
                  onMarkRead: (id) async {
                    await _callService.markRead(id);
                    await _load();
                  },
                  onDelete: (id) async {
                    await _callService.deleteRecord(id);
                    await _load();
                  },
                  onPlay: _playAudio,
                ),
              ],
            ),
    );
  }
}

class _RecordList extends StatelessWidget {
  final List<CallRecord> records;
  final Future<void> Function(int id) onMarkRead;
  final Future<void> Function(int id) onDelete;
  final Future<void> Function(CallRecord record) onPlay;

  const _RecordList({
    required this.records,
    required this.onMarkRead,
    required this.onDelete,
    required this.onPlay,
  });

  @override
  Widget build(BuildContext context) {
    if (records.isEmpty) {
      return Center(
        child: Text(
          'NO CALL RECORDS',
          style: GoogleFonts.orbitron(
              fontSize: 12,
              letterSpacing: 2,
              color: JarvisColors.textSecondary),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: records.length,
      itemBuilder: (_, i) {
        final record = records[i];
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: JPanel(
            borderColor: record.isImportant
                ? JarvisColors.red.withOpacity(0.5)
                : JarvisColors.border,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        border: Border.all(
                            color: record.isImportant
                                ? JarvisColors.red
                                : JarvisColors.cyan.withOpacity(0.4)),
                      ),
                      child: Text(
                        record.isImportant ? 'IMPORTANT' : 'NORMAL',
                        style: GoogleFonts.orbitron(
                          fontSize: 8,
                          color: record.isImportant
                              ? JarvisColors.red
                              : JarvisColors.cyan,
                          letterSpacing: 1.3,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      record.platform.toUpperCase(),
                      style: GoogleFonts.orbitron(
                          fontSize: 9,
                          letterSpacing: 1.2,
                          color: JarvisColors.blue),
                    ),
                    const Spacer(),
                    Text(
                      DateFormat('MMM dd, HH:mm').format(record.time),
                      style: GoogleFonts.shareTech(
                          fontSize: 11, color: JarvisColors.textSecondary),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  record.callerName,
                  style: GoogleFonts.orbitron(
                      fontSize: 12,
                      color: JarvisColors.textPrimary,
                      letterSpacing: 1.0),
                ),
                const SizedBox(height: 6),
                Text(
                  record.transcript.isEmpty
                      ? '(No transcript captured)'
                      : record.transcript,
                  style: GoogleFonts.shareTech(
                      fontSize: 13,
                      color: JarvisColors.textPrimary,
                      height: 1.45),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    if (record.audioPath.isNotEmpty)
                      IconButton(
                        onPressed: () => onPlay(record),
                        icon: const Icon(Icons.play_circle_outline,
                            color: JarvisColors.cyan),
                        tooltip: 'Play recording',
                      ),
                    if (!record.isRead)
                      IconButton(
                        onPressed: () => onMarkRead(record.id),
                        icon: const Icon(Icons.mark_email_read_outlined,
                            color: JarvisColors.green),
                        tooltip: 'Mark read',
                      ),
                    const Spacer(),
                    IconButton(
                      onPressed: () => onDelete(record.id),
                      icon: const Icon(Icons.delete_outline,
                          color: JarvisColors.red),
                      tooltip: 'Delete',
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
