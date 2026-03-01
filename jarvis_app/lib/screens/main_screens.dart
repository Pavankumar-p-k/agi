// lib/screens/reminders_screen.dart
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class RemindersScreen extends StatefulWidget {
  const RemindersScreen({super.key});

  @override
  State<RemindersScreen> createState() => _RemindersScreenState();
}

class _RemindersScreenState extends State<RemindersScreen> {
  final _api = ApiService();
  List<Reminder> _reminders = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _reminders = await _api.getReminders();
    } catch (e) {
      _showError('Failed to load reminders. Check connection and login.');
      debugPrint('Reminders load error: $e');
    }
    setState(() => _loading = false);
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _showAddDialog() async {
    final titleCtrl = TextEditingController();
    final descCtrl = TextEditingController();
    DateTime? picked;
    String repeat = 'none';

    await showDialog(
        context: context,
        builder: (ctx) => StatefulBuilder(
              builder: (ctx, setS) => AlertDialog(
                backgroundColor: JarvisColors.bgCard,
                shape: const RoundedRectangleBorder(
                  side: BorderSide(color: JarvisColors.border),
                  borderRadius: BorderRadius.zero,
                ),
                title: Text('NEW REMINDER',
                    style: GoogleFonts.orbitron(
                        fontSize: 13,
                        color: JarvisColors.cyan,
                        letterSpacing: 2)),
                content: SingleChildScrollView(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                  TextField(
                    controller: titleCtrl,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(hintText: 'Title'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: descCtrl,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(
                        hintText: 'Description (optional)'),
                  ),
                  const SizedBox(height: 12),
                  GestureDetector(
                    onTap: () async {
                      final d = await showDateTimePicker(ctx);
                      if (d != null) setS(() => picked = d);
                    },
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                          border: Border.all(color: JarvisColors.border)),
                      child: Row(children: [
                        const Icon(Icons.calendar_today_outlined,
                            color: JarvisColors.cyan, size: 14),
                        const SizedBox(width: 8),
                        Text(
                          picked == null
                              ? 'Select date & time'
                              : DateFormat('MMM dd, yyyy HH:mm')
                                  .format(picked!),
                          style: GoogleFonts.shareTech(
                              color: picked == null
                                  ? JarvisColors.textSecondary
                                  : JarvisColors.textPrimary,
                              fontSize: 13),
                        ),
                      ]),
                    ),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    value: repeat,
                    dropdownColor: JarvisColors.bgCard,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(hintText: 'Repeat'),
                    items: ['none', 'daily', 'weekly', 'monthly']
                        .map((v) => DropdownMenuItem(
                            value: v, child: Text(v.toUpperCase())))
                        .toList(),
                    onChanged: (v) => setS(() => repeat = v!),
                  ),
                ])),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: Text('CANCEL',
                          style: GoogleFonts.orbitron(
                              fontSize: 10,
                              color: JarvisColors.textSecondary))),
                  TextButton(
                    onPressed: () async {
                      if (titleCtrl.text.isEmpty || picked == null) return;
                      try {
                        await _api.createReminder(
                            title: titleCtrl.text,
                            remindAt: picked!,
                            description: descCtrl.text,
                            repeat: repeat);
                        Navigator.pop(ctx);
                        _load();
                      } catch (e) {
                        _showError(
                            'Failed to create reminder. Check connection and login.');
                        debugPrint('Create reminder error: $e');
                      }
                    },
                    child: Text('SAVE',
                        style: GoogleFonts.orbitron(
                            fontSize: 10, color: JarvisColors.cyan)),
                  ),
                ],
              ),
            ));
  }

  Future<DateTime?> showDateTimePicker(BuildContext ctx) async {
    final date = await showDatePicker(
      context: ctx,
      initialDate: DateTime.now().add(const Duration(hours: 1)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
      builder: (_, child) => Theme(data: ThemeData.dark(), child: child!),
    );
    if (date == null) return null;
    final time = await showTimePicker(
      context: ctx,
      initialTime: TimeOfDay.now(),
      builder: (_, child) => Theme(data: ThemeData.dark(), child: child!),
    );
    if (time == null) return null;
    return DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('REMINDERS'),
        actions: [
          IconButton(
              icon: const Icon(Icons.add, color: JarvisColors.cyan),
              onPressed: _showAddDialog),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(
                  color: JarvisColors.cyan, strokeWidth: 1.5))
          : _reminders.isEmpty
              ? Center(
                  child: Text('NO REMINDERS SET',
                      style: GoogleFonts.orbitron(
                          fontSize: 12,
                          letterSpacing: 2,
                          color: JarvisColors.textSecondary)))
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _reminders.length,
                  itemBuilder: (_, i) => _ReminderTile(
                    reminder: _reminders[i],
                    onComplete: () async {
                      try {
                        await _api.completeReminder(_reminders[i].id);
                        _load();
                      } catch (e) {
                        _showError(
                            'Failed to complete reminder. Check connection and login.');
                        debugPrint('Complete reminder error: $e');
                      }
                    },
                    onDelete: () async {
                      try {
                        await _api.deleteReminder(_reminders[i].id);
                        _load();
                      } catch (e) {
                        _showError(
                            'Failed to delete reminder. Check connection and login.');
                        debugPrint('Delete reminder error: $e');
                      }
                    },
                  ),
                ),
    );
  }
}

class _ReminderTile extends StatelessWidget {
  final Reminder reminder;
  final VoidCallback onComplete;
  final VoidCallback onDelete;
  const _ReminderTile({
    required this.reminder,
    required this.onComplete,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final isPast = reminder.remindAt.isBefore(DateTime.now());
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: JPanel(
        borderColor: reminder.isDone
            ? JarvisColors.textDim
            : (isPast
                ? JarvisColors.textDim
                : JarvisColors.cyan.withOpacity(0.3)),
        child: Row(children: [
          Container(
            width: 4,
            height: 50,
            color: reminder.isDone
                ? JarvisColors.textSecondary
                : (isPast ? JarvisColors.textSecondary : JarvisColors.cyan),
          ),
          const SizedBox(width: 12),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(reminder.title,
                    style: GoogleFonts.orbitron(
                        fontSize: 12,
                        color: reminder.isDone
                            ? JarvisColors.textSecondary
                            : JarvisColors.textPrimary,
                        decoration: reminder.isDone
                            ? TextDecoration.lineThrough
                            : TextDecoration.none,
                        letterSpacing: 1)),
                const SizedBox(height: 3),
                Text(
                    DateFormat('MMM dd, yyyy â€” HH:mm')
                        .format(reminder.remindAt),
                    style: GoogleFonts.shareTech(
                        fontSize: 12,
                        color: reminder.isDone
                            ? JarvisColors.textSecondary
                            : (isPast
                                ? JarvisColors.textSecondary
                                : JarvisColors.cyan))),
                if (reminder.repeat != 'none')
                  Text('â†º ${reminder.repeat.toUpperCase()}',
                      style: GoogleFonts.orbitron(
                          fontSize: 9,
                          color: JarvisColors.blue,
                          letterSpacing: 1)),
              ])),
          IconButton(
              icon: Icon(
                reminder.isDone
                    ? Icons.check_circle
                    : Icons.check_circle_outline,
                color: reminder.isDone
                    ? JarvisColors.textSecondary
                    : JarvisColors.green,
                size: 18,
              ),
              onPressed: reminder.isDone ? null : onComplete),
          IconButton(
              icon: const Icon(Icons.delete_outline,
                  color: JarvisColors.red, size: 18),
              onPressed: onDelete),
        ]),
      ),
    );
  }
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
//  NOTES SCREEN
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});
  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  final _api = ApiService();
  List<Note> _notes = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _notes = await _api.getNotes();
    } catch (e) {
      _showError('Failed to load notes. Check connection and login.');
      debugPrint('Notes load error: $e');
    }
    setState(() => _loading = false);
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _showAddDialog() async {
    final titleCtrl = TextEditingController();
    final contentCtrl = TextEditingController();
    await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
              backgroundColor: JarvisColors.bgCard,
              shape: const RoundedRectangleBorder(
                  side: BorderSide(color: JarvisColors.border),
                  borderRadius: BorderRadius.zero),
              title: Text('NEW NOTE',
                  style: GoogleFonts.orbitron(
                      fontSize: 13,
                      color: JarvisColors.cyan,
                      letterSpacing: 2)),
              content: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(
                    controller: titleCtrl,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(hintText: 'Title')),
                const SizedBox(height: 12),
                TextField(
                    controller: contentCtrl,
                    style: GoogleFonts.shareTech(
                        color: JarvisColors.textPrimary, fontSize: 13),
                    maxLines: 4,
                    decoration: const InputDecoration(hintText: 'Content...')),
              ]),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: Text('CANCEL',
                        style: GoogleFonts.orbitron(
                            fontSize: 10, color: JarvisColors.textSecondary))),
                TextButton(
                    onPressed: () async {
                      if (titleCtrl.text.isEmpty) return;
                      try {
                        await _api.createNote(titleCtrl.text, contentCtrl.text);
                        Navigator.pop(ctx);
                        _load();
                      } catch (e) {
                        _showError(
                            'Failed to create note. Check connection and login.');
                        debugPrint('Create note error: $e');
                      }
                    },
                    child: Text('SAVE',
                        style: GoogleFonts.orbitron(
                            fontSize: 10, color: JarvisColors.cyan))),
              ],
            ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('NOTES'), actions: [
        IconButton(
            icon: const Icon(Icons.add, color: JarvisColors.cyan),
            onPressed: _showAddDialog),
      ]),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(
                  color: JarvisColors.cyan, strokeWidth: 1.5))
          : _notes.isEmpty
              ? Center(
                  child: Text('NO NOTES',
                      style: GoogleFonts.orbitron(
                          fontSize: 12,
                          letterSpacing: 2,
                          color: JarvisColors.textSecondary)))
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _notes.length,
                  itemBuilder: (_, i) {
                    final n = _notes[i];
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Dismissible(
                        key: Key('note_${n.id}'),
                        direction: DismissDirection.endToStart,
                        background: Container(
                          alignment: Alignment.centerRight,
                          padding: const EdgeInsets.only(right: 16),
                          color: JarvisColors.red.withOpacity(0.2),
                          child: const Icon(Icons.delete_outline,
                              color: JarvisColors.red),
                        ),
                        onDismissed: (_) async {
                          try {
                            await _api.deleteNote(n.id);
                            _load();
                          } catch (e) {
                            _showError(
                                'Failed to delete note. Check connection and login.');
                            debugPrint('Delete note error: $e');
                          }
                        },
                        child: JPanel(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(children: [
                                  Expanded(
                                      child: Text(n.title,
                                          style: GoogleFonts.orbitron(
                                              fontSize: 12,
                                              color: JarvisColors.textPrimary,
                                              letterSpacing: 1))),
                                  Text(DateFormat('MMM dd').format(n.updatedAt),
                                      style: GoogleFonts.shareTech(
                                          fontSize: 10,
                                          color: JarvisColors.textSecondary)),
                                ]),
                                if (n.content.isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  Text(n.content,
                                      maxLines: 3,
                                      overflow: TextOverflow.ellipsis,
                                      style: GoogleFonts.shareTech(
                                          fontSize: 13,
                                          color: JarvisColors.textPrimary
                                              .withOpacity(0.8),
                                          height: 1.5)),
                                ],
                                if ((n.tags ?? '').isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  Wrap(
                                      spacing: 6,
                                      children: n.tags!
                                          .split(',')
                                          .map((t) => Container(
                                                padding:
                                                    const EdgeInsets.symmetric(
                                                        horizontal: 8,
                                                        vertical: 3),
                                                decoration: BoxDecoration(
                                                    border: Border.all(
                                                        color: JarvisColors.blue
                                                            .withOpacity(0.4))),
                                                child: Text(t.trim(),
                                                    style: GoogleFonts.orbitron(
                                                        fontSize: 8,
                                                        color:
                                                            JarvisColors.blue,
                                                        letterSpacing: 1)),
                                              ))
                                          .toList()),
                                ],
                              ]),
                        ),
                      ),
                    );
                  },
                ),
    );
  }
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
//  ACTIVITY SCREEN
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class ActivityScreen extends StatefulWidget {
  const ActivityScreen({super.key});
  @override
  State<ActivityScreen> createState() => _ActivityScreenState();
}

class _ActivityScreenState extends State<ActivityScreen> {
  final _api = ApiService();
  List<Activity> _activities = [];
  DailySummary? _summary;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results =
          await Future.wait([_api.getTodayActivity(), _api.getDailySummary()]);
      _activities = results[0] as List<Activity>;
      _summary = results[1] as DailySummary;
    } catch (e) {
      _showError('Failed to load activity. Check connection and login.');
      debugPrint('Activity load error: $e');
    }
    setState(() => _loading = false);
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ACTIVITY'), actions: [
        IconButton(
            icon: const Icon(Icons.refresh_outlined, color: JarvisColors.cyan),
            onPressed: _load),
      ]),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(
                  color: JarvisColors.cyan, strokeWidth: 1.5))
          : ListView(padding: const EdgeInsets.all(16), children: [
              if (_summary != null) ...[
                JPanel(
                    label: 'TODAY\'S SUMMARY',
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(_summary!.summary,
                              style: GoogleFonts.shareTech(
                                  fontSize: 13,
                                  color: JarvisColors.textPrimary,
                                  height: 1.6)),
                          const SizedBox(height: 14),
                          MetricBar(
                              label: 'PRODUCTIVITY',
                              value: _summary!.productivityScore / 10),
                          const SizedBox(height: 16),
                          if (_summary!.insights.isNotEmpty) ...[
                            Text('// INSIGHTS',
                                style: GoogleFonts.orbitron(
                                    fontSize: 9,
                                    letterSpacing: 2,
                                    color: JarvisColors.cyan.withOpacity(0.7))),
                            const SizedBox(height: 8),
                            ..._summary!.insights.map((ins) => Padding(
                                  padding: const EdgeInsets.only(bottom: 6),
                                  child: Row(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text('â–¸ ',
                                            style: GoogleFonts.shareTech(
                                                color: JarvisColors.cyan,
                                                fontSize: 13)),
                                        Expanded(
                                            child: Text(ins,
                                                style: GoogleFonts.shareTech(
                                                    fontSize: 12,
                                                    color: JarvisColors
                                                        .textPrimary,
                                                    height: 1.4))),
                                      ]),
                                )),
                          ],
                        ])),
                const SizedBox(height: 16),
              ],
              JPanel(
                label: 'ACTIVITY LOG (${_activities.length})',
                child: _activities.isEmpty
                    ? Text('No activities recorded today',
                        style: GoogleFonts.shareTech(
                            fontSize: 13, color: JarvisColors.textSecondary))
                    : Column(
                        children: _activities.reversed
                            .map((a) => Padding(
                                  padding: const EdgeInsets.only(bottom: 10),
                                  child: Row(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Container(
                                          width: 4,
                                          height: 4,
                                          margin: const EdgeInsets.only(
                                              top: 7, right: 10),
                                          decoration: const BoxDecoration(
                                              shape: BoxShape.circle,
                                              color: JarvisColors.cyan),
                                        ),
                                        Expanded(
                                            child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                              Text(a.description,
                                                  style: GoogleFonts.shareTech(
                                                      fontSize: 12,
                                                      color: JarvisColors
                                                          .textPrimary)),
                                              Text(
                                                  DateFormat('HH:mm')
                                                      .format(a.timestamp),
                                                  style: GoogleFonts.orbitron(
                                                      fontSize: 9,
                                                      color: JarvisColors
                                                          .textSecondary,
                                                      letterSpacing: 1)),
                                            ])),
                                      ]),
                                ))
                            .toList()),
              ),
            ]),
    );
  }
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
//  MESSAGING SCREEN
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class MessagingScreen extends StatefulWidget {
  const MessagingScreen({super.key});
  @override
  State<MessagingScreen> createState() => _MessagingScreenState();
}

class _MessagingScreenState extends State<MessagingScreen> {
  final _api = ApiService();
  final _recipientCtrl = TextEditingController();
  final _incomingCtrl = TextEditingController();
  final _messageCtrl = TextEditingController();
  final _styleCtrl = TextEditingController();
  String _platform = 'whatsapp';
  bool _loading = false;
  bool _loginLoading = false;
  bool _aiLoading = false;
  bool _profileLoading = false;
  bool _profileSaving = false;
  String? _result;

  @override
  void initState() {
    super.initState();
    _loadAutoReplyProfile();
  }

  @override
  void dispose() {
    _recipientCtrl.dispose();
    _incomingCtrl.dispose();
    _messageCtrl.dispose();
    _styleCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadAutoReplyProfile() async {
    setState(() => _profileLoading = true);
    try {
      final resp = await _api.getAutoReplyProfile();
      final profile = resp['profile'];
      if (profile is Map) {
        final style = (profile['style_prompt'] ?? '').toString().trim();
        if (style.isNotEmpty) {
          _styleCtrl.text = style;
        }
      }
    } catch (_) {
      // Keep local defaults if API call fails.
    } finally {
      if (mounted) {
        setState(() => _profileLoading = false);
      }
    }
  }

  Future<void> _saveAutoReplyProfile() async {
    if (_styleCtrl.text.trim().isEmpty) {
      setState(() => _result = 'ERR: Style prompt cannot be empty.');
      return;
    }
    setState(() {
      _profileSaving = true;
      _result = null;
    });
    try {
      final resp = await _api.updateAutoReplyProfile(
        stylePrompt: _styleCtrl.text.trim(),
      );
      final success = resp['success'] == true;
      setState(() => _result = success
          ? 'OK: Reply style saved.'
          : 'ERR: Failed to save reply style.');
    } catch (e) {
      setState(() => _result = 'ERR: Save style error: ${e.toString()}');
    } finally {
      if (mounted) {
        setState(() => _profileSaving = false);
      }
    }
  }

  Future<void> _login() async {
    setState(() {
      _loginLoading = true;
      _result = null;
    });
    try {
      final resp = await _api.loginMessagingPlatform(_platform);
      final success = resp['success'] == true;
      final error = (resp['error'] ?? '').toString();
      setState(() => _result = success
          ? 'OK: Login ready for ${_platform.toUpperCase()}'
          : 'ERR: Login failed: ${error.isEmpty ? 'unknown error' : error}');
    } catch (e) {
      setState(() => _result = 'ERR: Login error: ${e.toString()}');
    } finally {
      setState(() => _loginLoading = false);
    }
  }

  Future<void> _generateReply({required bool autoSend}) async {
    if (_recipientCtrl.text.trim().isEmpty) {
      setState(() => _result = 'ERR: Enter recipient first.');
      return;
    }
    if (_incomingCtrl.text.trim().isEmpty) {
      setState(() => _result = 'ERR: Enter incoming message first.');
      return;
    }

    setState(() {
      _aiLoading = true;
      _result = null;
    });

    try {
      final generated = await _api.generateAutoReply(
        platform: _platform,
        incomingMessage: _incomingCtrl.text.trim(),
        sender: _recipientCtrl.text.trim(),
      );
      final ok = generated['success'] == true;
      if (!ok) {
        final error = (generated['error'] ?? 'generation failed').toString();
        setState(() => _result = 'ERR: Auto-reply failed: $error');
        return;
      }

      final reply = (generated['reply'] ?? '').toString().trim();
      if (reply.isEmpty) {
        setState(() => _result = 'ERR: Generated reply is empty.');
        return;
      }
      _messageCtrl.text = reply;

      if (!autoSend) {
        setState(() => _result = 'OK: Reply generated. Review and send.');
        return;
      }

      final sent = await _api.sendMessageDetailed(
        _platform,
        _recipientCtrl.text.trim(),
        reply,
      );
      final success = sent['success'] == true;
      final error = (sent['error'] ?? '').toString();
      setState(() => _result = success
          ? 'OK: Auto-reply generated and sent.'
          : 'ERR: Reply generated but send failed: ${error.isEmpty ? 'unknown error' : error}');
    } catch (e) {
      setState(() => _result = 'ERR: Auto-reply error: ${e.toString()}');
    } finally {
      if (mounted) {
        setState(() => _aiLoading = false);
      }
    }
  }

  Future<void> _send() async {
    if (_recipientCtrl.text.trim().isEmpty || _messageCtrl.text.trim().isEmpty) {
      setState(() => _result = 'ERR: Recipient and message are required.');
      return;
    }
    setState(() {
      _loading = true;
      _result = null;
    });
    try {
      final resp = await _api.sendMessageDetailed(
        _platform,
        _recipientCtrl.text.trim(),
        _messageCtrl.text.trim(),
      );
      final success = resp['success'] == true;
      final error = (resp['error'] ?? '').toString();
      setState(() => _result = success
          ? 'OK: Message sent successfully'
          : 'ERR: Failed to send: ${error.isEmpty ? 'unknown error' : error}');
    } catch (e) {
      setState(() => _result = 'ERR: Error: ${e.toString()}');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MESSAGE SENDER')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          JPanel(
              label: 'PLATFORM',
              child: Row(children: [
                _PlatformChip(
                    label: 'WHATSAPP',
                    icon: Icons.chat_bubble_outline,
                    selected: _platform == 'whatsapp',
                    onTap: () => setState(() => _platform = 'whatsapp'),
                    color: JarvisColors.green),
                const SizedBox(width: 10),
                _PlatformChip(
                    label: 'INSTAGRAM',
                    icon: Icons.photo_camera_outlined,
                    selected: _platform == 'instagram',
                    onTap: () => setState(() => _platform = 'instagram'),
                    color: JarvisColors.orange),
              ])),
          const SizedBox(height: 14),
          JPanel(
              label: 'AUTO REPLY LIKE ME',
              child: Column(children: [
                TextField(
                  controller: _incomingCtrl,
                  style: GoogleFonts.shareTech(
                      color: JarvisColors.textPrimary, fontSize: 13),
                  maxLines: 3,
                  decoration: const InputDecoration(
                    hintText: 'Incoming message from other person...',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _styleCtrl,
                  style: GoogleFonts.shareTech(
                      color: JarvisColors.textPrimary, fontSize: 12),
                  maxLines: 3,
                  decoration: InputDecoration(
                    hintText: _profileLoading
                        ? 'Loading style...'
                        : 'How to reply like you (tone, style, phrases)',
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: _profileSaving ? 'SAVING STYLE...' : 'SAVE MY STYLE',
                    icon: Icons.save_outlined,
                    onTap: _profileSaving ? null : _saveAutoReplyProfile,
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: _aiLoading
                        ? 'GENERATING...'
                        : 'GENERATE REPLY LIKE ME',
                    icon: Icons.auto_awesome_outlined,
                    onTap: _aiLoading ? null : () => _generateReply(autoSend: false),
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: _aiLoading
                        ? 'WORKING...'
                        : 'GENERATE + SEND AUTO REPLY',
                    icon: Icons.bolt_outlined,
                    onTap: _aiLoading ? null : () => _generateReply(autoSend: true),
                  ),
                ),
              ])),
          const SizedBox(height: 14),
          JPanel(
              label: 'COMPOSE / SEND',
              child: Column(children: [
                TextField(
                  controller: _recipientCtrl,
                  style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                  decoration: InputDecoration(
                    hintText: _platform == 'whatsapp'
                        ? 'Contact name or phone'
                        : '@username or name',
                    prefixIcon: const Icon(Icons.person_outline,
                        color: JarvisColors.textSecondary, size: 16),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _messageCtrl,
                  style: GoogleFonts.shareTech(
                      color: JarvisColors.textPrimary, fontSize: 13),
                  maxLines: 4,
                  decoration:
                      const InputDecoration(hintText: 'Message content...'),
                ),
                const SizedBox(height: 16),
                if (_result != null)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      border: Border.all(
                          color: _result!.startsWith('OK:')
                              ? JarvisColors.green
                              : JarvisColors.red,
                          width: 0.8),
                      color: (_result!.startsWith('OK:')
                              ? JarvisColors.green
                              : JarvisColors.red)
                          .withOpacity(0.07),
                    ),
                    child: Text(_result!,
                        style: GoogleFonts.shareTech(
                            fontSize: 13,
                            color: _result!.startsWith('OK:')
                                ? JarvisColors.green
                                : JarvisColors.red)),
                  ),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: _loginLoading
                        ? 'OPENING LOGIN...'
                        : 'LOGIN PLATFORM (QR)',
                    icon: Icons.login_outlined,
                    onTap: _loginLoading ? null : _login,
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: _loading ? 'SENDING...' : 'SEND CURRENT REPLY',
                    icon: Icons.send,
                    onTap: _loading ? null : _send,
                  ),
                ),
              ])),
          const SizedBox(height: 16),
          JPanel(
              label: 'NOTE',
              child: Text(
                (!kIsWeb && defaultTargetPlatform == TargetPlatform.android)
                    ? 'Android: send opens WhatsApp/Instagram directly on your phone. Auto-reply generation is done by backend, then sent via phone automation.'
                    : 'Windows: use LOGIN PLATFORM first for web automation, then generate/send auto-replies.',
                style: GoogleFonts.shareTech(
                    fontSize: 11,
                    color: JarvisColors.textSecondary,
                    height: 1.5),
              )),
        ]),
      ),
    );
  }
}

class _PlatformChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final Color color;
  const _PlatformChip({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
    required this.color,
  });

  @override
  Widget build(BuildContext context) => Expanded(
          child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: selected ? color.withOpacity(0.12) : Colors.transparent,
            border: Border.all(color: selected ? color : JarvisColors.border),
          ),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icon,
                size: 14, color: selected ? color : JarvisColors.textSecondary),
            const SizedBox(width: 6),
            Text(label,
                style: GoogleFonts.orbitron(
                    fontSize: 10,
                    letterSpacing: 1.5,
                    color: selected ? color : JarvisColors.textSecondary)),
          ]),
        ),
      ));
}
