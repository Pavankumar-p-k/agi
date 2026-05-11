// lib/screens/reminders_screen.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../models/offline_models.dart';
import '../db/local_db.dart';
import '../services/reminder_engine.dart';
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
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _reminders = await _api.getReminders();
    } catch (_) {
      final local = await localDB.getReminders();
      _reminders = local.map(_fromLocal).toList();
    }
    setState(() => _loading = false);
  }

  Future<void> _showAddDialog() async {
    final titleCtrl = TextEditingController();
    final descCtrl  = TextEditingController();
    DateTime? picked;
    String repeat = 'none';

    await showDialog(context: context, builder: (ctx) => StatefulBuilder(
      builder: (ctx, setS) => AlertDialog(
        backgroundColor: JarvisColors.bgCard,
        shape: const RoundedRectangleBorder(
          side: BorderSide(color: JarvisColors.border),
          borderRadius: BorderRadius.zero,
        ),
        title: Text('NEW REMINDER', style: GoogleFonts.orbitron(fontSize: 13, color: JarvisColors.cyan, letterSpacing: 2)),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: titleCtrl,
            style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
            decoration: const InputDecoration(hintText: 'Title'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: descCtrl,
            style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
            decoration: const InputDecoration(hintText: 'Description (optional)'),
          ),
          const SizedBox(height: 12),
          GestureDetector(
            onTap: () async {
              final d = await showDateTimePicker(ctx);
              if (d != null) setS(() => picked = d);
            },
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(border: Border.all(color: JarvisColors.border)),
              child: Row(children: [
                const Icon(Icons.calendar_today_outlined, color: JarvisColors.cyan, size: 14),
                const SizedBox(width: 8),
                Text(
                  picked == null ? 'Select date & time' : DateFormat('MMM dd, yyyy HH:mm').format(picked!),
                  style: GoogleFonts.shareTech(color: picked == null ? JarvisColors.textSecondary : JarvisColors.textPrimary, fontSize: 13),
                ),
              ]),
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: repeat,
            dropdownColor: JarvisColors.bgCard,
            style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
            decoration: const InputDecoration(hintText: 'Repeat'),
            items: ['none','daily','weekly','monthly'].map((v) =>
              DropdownMenuItem(value: v, child: Text(v.toUpperCase()))
            ).toList(),
            onChanged: (v) => setS(() => repeat = v!),
          ),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text('CANCEL', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.textSecondary))),
          TextButton(
            onPressed: () async {
              if (titleCtrl.text.isEmpty || picked == null) return;
              final local = ReminderModel(
                title: titleCtrl.text,
                description: descCtrl.text,
                remindAt: picked!,
                repeat: repeat,
                isAlarm: titleCtrl.text.toLowerCase().contains('alarm'),
              );
              final id = await localDB.insertReminder(local);
              await ReminderEngine.scheduleReminder(
                ReminderModel(
                  id: id,
                  title: local.title,
                  description: local.description,
                  remindAt: local.remindAt,
                  repeat: local.repeat,
                  isAlarm: local.isAlarm,
                ),
              );
              try {
                await _api.createReminder(
                  title: titleCtrl.text,
                  remindAt: picked!,
                  description: descCtrl.text,
                  repeat: repeat,
                );
              } catch (_) {}
              Navigator.pop(ctx);
              _load();
            },
            child: Text('SAVE', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.cyan)),
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

  Reminder _fromLocal(ReminderModel r) {
    return Reminder(
      id: r.id ?? 0,
      title: r.title,
      description: r.description,
      remindAt: r.remindAt,
      repeat: r.repeat,
      isDone: r.isDone,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('REMINDERS'),
        actions: [
          IconButton(icon: const Icon(Icons.add, color: JarvisColors.cyan), onPressed: _showAddDialog),
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1.5))
        : _reminders.isEmpty
          ? Center(child: Text('NO REMINDERS SET', style: GoogleFonts.orbitron(fontSize: 12, letterSpacing: 2, color: JarvisColors.textSecondary)))
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _reminders.length,
              itemBuilder: (_, i) => _ReminderTile(
                reminder: _reminders[i],
                onDelete: () async {
                  final r = _reminders[i];
                  await localDB.deleteReminder(r.id);
                  await ReminderEngine.cancelReminder(r.id);
                  try { await _api.deleteReminder(r.id); } catch (_) {}
                  _load();
                },
              ),
            ),
    );
  }
}

class _ReminderTile extends StatelessWidget {
  final Reminder reminder;
  final VoidCallback onDelete;
  const _ReminderTile({required this.reminder, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final isPast = reminder.remindAt.isBefore(DateTime.now());
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: JPanel(
        borderColor: isPast ? JarvisColors.textDim : JarvisColors.cyan.withOpacity(0.3),
        child: Row(children: [
          Container(
            width: 4, height: 50,
            color: isPast ? JarvisColors.textSecondary : JarvisColors.cyan,
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(reminder.title, style: GoogleFonts.orbitron(fontSize: 12, color: JarvisColors.textPrimary, letterSpacing: 1)),
            const SizedBox(height: 3),
            Text(DateFormat('MMM dd, yyyy — HH:mm').format(reminder.remindAt),
              style: GoogleFonts.shareTech(fontSize: 12, color: isPast ? JarvisColors.textSecondary : JarvisColors.cyan)),
            if (reminder.repeat != 'none')
              Text('↺ ${reminder.repeat.toUpperCase()}', style: GoogleFonts.orbitron(fontSize: 9, color: JarvisColors.blue, letterSpacing: 1)),
          ])),
          IconButton(icon: const Icon(Icons.delete_outline, color: JarvisColors.red, size: 18), onPressed: onDelete),
        ]),
      ),
    );
  }
}
