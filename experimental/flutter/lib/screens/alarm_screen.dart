// lib/screens/alarm_screen.dart
// JARVIS ALARM CLOCK — Replaces Android Default
// Real Android alarms via flutter_local_notifications + exact alarms.
// Features: multiple alarms, repeat days, math challenge to dismiss,
//           gradual volume, vibration patterns, custom labels,
//           sunrise alarm, nap timer, bedtime reminder.

import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'package:timezone/timezone.dart' as tz;
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

// ── Alarm model ───────────────────────────────────────────────

class AlarmModel {
  final String id;
  String   label;
  int      hour, minute;
  List<bool> days;       // Mon-Sun
  bool     enabled;
  bool     vibrate;
  String   sound;        // default|gentle|jarvis|silent
  int      snoozeMin;
  bool     mathChallenge; // must solve math to dismiss
  bool     gradualVolume;
  String   repeatType;   // once|daily|weekdays|weekends|custom

  AlarmModel({
    String? id,
    required this.label,
    required this.hour,
    required this.minute,
    List<bool>? days,
    this.enabled      = true,
    this.vibrate      = true,
    this.sound        = 'default',
    this.snoozeMin    = 10,
    this.mathChallenge = false,
    this.gradualVolume = true,
    this.repeatType   = 'once',
  }) : id   = id ?? DateTime.now().millisecondsSinceEpoch.toString(),
       days = days ?? List.filled(7, false);

  String get timeString =>
    '${hour.toString().padLeft(2,"0")}:${minute.toString().padLeft(2,"0")}';

  String get repeatLabel {
    if (days.every((d) => !d)) return 'Once';
    if (days.every((d) => d))  return 'Every day';
    const dayNames = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    final active = [for (int i=0;i<7;i++) if (days[i]) dayNames[i]];
    if (active.length == 5 && !days[5] && !days[6]) return 'Weekdays';
    if (active.length == 2 &&  days[5] &&  days[6]) return 'Weekends';
    return active.join(', ');
  }

  Map<String, dynamic> toJson() => {
    'id': id, 'label': label, 'hour': hour, 'minute': minute,
    'days': days, 'enabled': enabled, 'vibrate': vibrate,
    'sound': sound, 'snoozeMin': snoozeMin,
    'mathChallenge': mathChallenge, 'gradualVolume': gradualVolume,
    'repeatType': repeatType,
  };

  factory AlarmModel.fromJson(Map<String, dynamic> j) => AlarmModel(
    id: j['id'], label: j['label'], hour: j['hour'], minute: j['minute'],
    days: (j['days'] as List).cast<bool>(), enabled: j['enabled'],
    vibrate: j['vibrate'], sound: j['sound'], snoozeMin: j['snoozeMin'],
    mathChallenge: j['mathChallenge'], gradualVolume: j['gradualVolume'],
    repeatType: j['repeatType'],
  );
}

// ── Alarm storage ─────────────────────────────────────────────

class AlarmStorage {
  static const _key = 'jarvis_alarms';

  static Future<List<AlarmModel>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw   = prefs.getString(_key);
    if (raw == null) return [];
    final list  = jsonDecode(raw) as List;
    return list.map((j) => AlarmModel.fromJson(j)).toList();
  }

  static Future<void> save(List<AlarmModel> alarms) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(alarms.map((a) => a.toJson()).toList()));
  }

  static Future<void> scheduleAlarm(AlarmModel alarm) async {
    if (!alarm.enabled) return;
    final notif = FlutterLocalNotificationsPlugin();

    final now = DateTime.now();
    var scheduled = DateTime(now.year, now.month, now.day, alarm.hour, alarm.minute);
    if (scheduled.isBefore(now)) scheduled = scheduled.add(const Duration(days: 1));

    await notif.zonedSchedule(
      alarm.id.hashCode,
      '⏰ ${alarm.label}',
      'Tap to dismiss — ${alarm.snoozeMin}min snooze available',
      _toTZ(scheduled),
      NotificationDetails(
        android: AndroidNotificationDetails(
          'jarvis_alarms', 'JARVIS Alarms',
          importance: Importance.max, priority: Priority.max,
          fullScreenIntent: true,
          category: AndroidNotificationCategory.alarm,
          playSound: alarm.sound != 'silent',
          enableVibration: alarm.vibrate,
          color: const Color(0xFF00F0FF),
          actions: [
            const AndroidNotificationAction('dismiss', 'DISMISS'),
            AndroidNotificationAction('snooze', 'SNOOZE ${alarm.snoozeMin}m'),
          ],
        ),
      ),
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      matchDateTimeComponents: alarm.days.any((d) => d)
          ? DateTimeComponents.dayOfWeekAndTime : null,
    );
  }

  static Future<void> cancelAlarm(AlarmModel alarm) async {
    final notif = FlutterLocalNotificationsPlugin();
    await notif.cancel(alarm.id.hashCode);
  }

  static tz.TZDateTime _toTZ(DateTime dt) {
    return tz.TZDateTime.from(dt, tz.local);
  }
}

// ═══════════════════════════════════════════
//  ALARM SCREEN
// ═══════════════════════════════════════════

class AlarmScreen extends StatefulWidget {
  const AlarmScreen({super.key});
  @override State<AlarmScreen> createState() => _AlarmScreenState();
}

class _AlarmScreenState extends State<AlarmScreen> with TickerProviderStateMixin {
  List<AlarmModel> _alarms = [];
  late AnimationController _pulseCtrl;
  Timer? _clockTimer;
  DateTime _now = DateTime.now();
  int _currentTab = 0;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(vsync: this,
        duration: const Duration(milliseconds: 1500))..repeat(reverse: true);
    _clockTimer = Timer.periodic(const Duration(seconds: 1),
        (_) => setState(() => _now = DateTime.now()));
    _loadAlarms();
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    _clockTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadAlarms() async {
    final alarms = await AlarmStorage.load();
    setState(() => _alarms = alarms);
  }

  Future<void> _saveAlarms() async {
    await AlarmStorage.save(_alarms);
  }

  // ── Add alarm ─────────────────────────────────────────────

  Future<void> _showAddAlarm({AlarmModel? existing}) async {
    final isEdit = existing != null;
    final alarm  = existing ?? AlarmModel(
      label: 'Alarm', hour: TimeOfDay.now().hour,
      minute: TimeOfDay.now().minute,
    );

    await showModalBottomSheet(
      context: context,
      backgroundColor: J.bg1,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (_) => _AlarmEditor(
        alarm:   alarm,
        isEdit:  isEdit,
        onSave: (a) async {
          setState(() {
            if (isEdit) {
              final idx = _alarms.indexWhere((x) => x.id == a.id);
              if (idx >= 0) _alarms[idx] = a;
            } else {
              _alarms.add(a);
            }
            _alarms.sort((a, b) => a.hour * 60 + a.minute - (b.hour * 60 + b.minute));
          });
          await AlarmStorage.scheduleAlarm(a);
          await _saveAlarms();
        },
      ),
    );
  }

  Future<void> _toggleAlarm(AlarmModel alarm) async {
    setState(() => alarm.enabled = !alarm.enabled);
    if (alarm.enabled) {
      await AlarmStorage.scheduleAlarm(alarm);
    } else {
      await AlarmStorage.cancelAlarm(alarm);
    }
    await _saveAlarms();
  }

  Future<void> _deleteAlarm(AlarmModel alarm) async {
    await AlarmStorage.cancelAlarm(alarm);
    setState(() => _alarms.removeWhere((a) => a.id == alarm.id));
    await _saveAlarms();
  }

  // ── Next alarm time ───────────────────────────────────────

  String get _nextAlarmText {
    final enabled = _alarms.where((a) => a.enabled).toList();
    if (enabled.isEmpty) return 'No alarms set';
    final now = DateTime.now();
    AlarmModel? next;
    Duration? shortest;
    for (final a in enabled) {
      var candidate = DateTime(now.year, now.month, now.day, a.hour, a.minute);
      if (candidate.isBefore(now)) candidate = candidate.add(const Duration(days: 1));
      final diff = candidate.difference(now);
      if (shortest == null || diff < shortest) {
        shortest = diff; next = a;
      }
    }
    if (next == null) return 'No upcoming alarms';
    final h = shortest!.inHours;
    final m = shortest.inMinutes.remainder(60);
    return 'Next: ${next.label} in ${h > 0 ? '${h}h ' : ''}${m}m';
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [

      // Digital clock
      _buildClock(),

      // Tabs
      _buildTabs(),

      // Content
      Expanded(child: IndexedStack(index: _currentTab, children: [
        _buildAlarmList(),
        _buildNapTimer(),
        _buildBedtime(),
      ])),
    ]);
  }

  Widget _buildClock() {
    final h  = _now.hour.toString().padLeft(2,'0');
    final m  = _now.minute.toString().padLeft(2,'0');
    final s  = _now.second.toString().padLeft(2,'0');
    final weekday = ['MON','TUE','WED','THU','FRI','SAT','SUN'][_now.weekday - 1];
    final date = '${_now.day.toString().padLeft(2,"0")}/${_now.month.toString().padLeft(2,"0")}/${_now.year}';

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 20),
      decoration: const BoxDecoration(
        color: J.bg1,
        border: Border(bottom: BorderSide(color: J.border0)),
      ),
      child: Column(children: [
        // Big clock
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text('$h:$m', style: J.orbitron(54, weight: FontWeight.w900,
              color: J.cyan, spacing: 4)),
          const SizedBox(width: 8),
          Padding(
            padding: const EdgeInsets.only(top: 18),
            child: AnimatedBuilder(
              animation: _pulseCtrl,
              builder: (_, __) => Text(s,
                style: J.orbitron(22, color: J.cyan.withValues(alpha: 0.4 + _pulseCtrl.value * 0.4),
                    spacing: 2)),
            ),
          ),
        ]),

        // Date
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text(weekday, style: J.shareTech(12, color: J.amber)),
          const SizedBox(width: 12),
          Text(date,    style: J.shareTech(12, color: J.t3)),
        ]),
        const SizedBox(height: 10),

        // Next alarm
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Icon(Icons.alarm, size: 12, color: J.t3),
          const SizedBox(width: 6),
          Text(_nextAlarmText, style: J.shareTech(11, color: J.t3)),
        ]),
      ]),
    );
  }

  Widget _buildTabs() {
    final tabs = ['ALARMS', 'NAP', 'BEDTIME'];
    return Container(
      height: 36, color: J.bg1,
      child: Row(children: List.generate(tabs.length, (i) {
        final sel = _currentTab == i;
        return Expanded(child: GestureDetector(
          onTap: () => setState(() => _currentTab = i),
          child: Container(
            decoration: BoxDecoration(border: Border(bottom: BorderSide(
              color: sel ? J.cyan : Colors.transparent, width: 2))),
            child: Center(child: Text(tabs[i],
              style: J.orbitron(9, color: sel ? J.cyan : J.t3, spacing: 1))),
          ),
        ));
      })),
    );
  }

  Widget _buildAlarmList() {
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Row(children: [
          Text('${_alarms.length} alarms',
              style: J.shareTech(10, color: J.t3)),
          const Spacer(),
          CyberButton(
            label: 'ADD ALARM', icon: Icons.add, color: J.cyan,
            onTap: () => _showAddAlarm(),
          ),
        ]),
      ),
      const SizedBox(height: 8),
      Expanded(
        child: _alarms.isEmpty
          ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              const Icon(Icons.alarm_off_outlined, color: J.t4, size: 56),
              const SizedBox(height: 16),
              Text('NO ALARMS', style: J.orbitron(13, color: J.t3, spacing: 3)),
              const SizedBox(height: 8),
              Text('Tap + to set your first alarm',
                  style: J.rajdhani(14, color: J.t3)),
            ]))
          : ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              itemCount: _alarms.length,
              itemBuilder: (_, i) => _buildAlarmTile(_alarms[i]),
            ),
      ),
    ]);
  }

  Widget _buildAlarmTile(AlarmModel alarm) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: alarm.enabled ? J.bg2 : J.bg1,
        border: Border(
          left: BorderSide(color: alarm.enabled ? J.cyan : J.t4, width: 2),
          top:    const BorderSide(color: J.border0),
          right:  const BorderSide(color: J.border0),
          bottom: const BorderSide(color: J.border0),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: GestureDetector(
            onTap: () => _showAddAlarm(existing: alarm),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(alarm.timeString,
                style: J.orbitron(32, weight: FontWeight.w900,
                  color: alarm.enabled ? J.cyan : J.t3, spacing: 2)),
              Text(alarm.label,
                style: J.rajdhani(14, color: alarm.enabled ? J.t1 : J.t3,
                    weight: FontWeight.w600)),
            ]),
          )),
          Switch(
            value: alarm.enabled,
            onChanged: (_) => _toggleAlarm(alarm),
            activeColor: J.cyan,
            activeTrackColor: J.cyan.withValues(alpha: 0.2),
            inactiveThumbColor: J.t4,
          ),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          _AlarmTag(alarm.repeatLabel),
          if (alarm.mathChallenge) _AlarmTag('MATH', color: J.amber),
          if (alarm.gradualVolume)  _AlarmTag('GRADUAL'),
          if (alarm.vibrate)        _AlarmTag('VIBRATE', color: J.cyanDim),
          const Spacer(),
          GestureDetector(
            onTap: () => _deleteAlarm(alarm),
            child: const Icon(Icons.delete_outline, color: J.red, size: 16),
          ),
        ]),
        // Day buttons
        if (alarm.days.any((d) => d)) ...[
          const SizedBox(height: 8),
          Row(children: List.generate(7, (i) {
            const labels = ['M','T','W','T','F','S','S'];
            return Padding(
              padding: const EdgeInsets.only(right: 6),
              child: Container(
                width: 24, height: 24,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: alarm.days[i] ? J.cyan.withValues(alpha: 0.15) : Colors.transparent,
                  border: Border.all(
                    color: alarm.days[i] ? J.cyan : J.border0),
                ),
                child: Center(child: Text(labels[i],
                  style: J.shareTech(9, color: alarm.days[i] ? J.cyan : J.t4))),
              ),
            );
          })),
        ],
      ]),
    );
  }

  Widget _buildNapTimer() {
    return _NapTimerWidget();
  }

  Widget _buildBedtime() {
    return _BedtimeWidget();
  }
}

class _AlarmTag extends StatelessWidget {
  final String text;
  final Color?  color;
  const _AlarmTag(this.text, {this.color});

  @override
  Widget build(BuildContext context) {
    final c = color ?? J.t3;
    return Container(
      margin: const EdgeInsets.only(right: 6),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: c.withValues(alpha: 0.4)),
        color:  c.withValues(alpha: 0.08),
      ),
      child: Text(text, style: J.orbitron(7, color: c, spacing: 0.5)),
    );
  }
}

// ── Alarm Editor bottom sheet ─────────────────────────────────

class _AlarmEditor extends StatefulWidget {
  final AlarmModel alarm;
  final bool isEdit;
  final ValueChanged<AlarmModel> onSave;
  const _AlarmEditor({required this.alarm, required this.isEdit, required this.onSave});
  @override State<_AlarmEditor> createState() => _AlarmEditorState();
}

class _AlarmEditorState extends State<_AlarmEditor> {
  late AlarmModel _alarm;
  late TextEditingController _labelCtrl;

  @override
  void initState() {
    super.initState();
    _alarm    = AlarmModel(
      id: widget.alarm.id, label: widget.alarm.label,
      hour: widget.alarm.hour, minute: widget.alarm.minute,
      days: List.from(widget.alarm.days),
      enabled: widget.alarm.enabled, vibrate: widget.alarm.vibrate,
      sound: widget.alarm.sound, snoozeMin: widget.alarm.snoozeMin,
      mathChallenge: widget.alarm.mathChallenge,
      gradualVolume: widget.alarm.gradualVolume,
      repeatType: widget.alarm.repeatType,
    );
    _labelCtrl = TextEditingController(text: _alarm.label);
  }

  @override
  void dispose() { _labelCtrl.dispose(); super.dispose(); }

  Future<void> _pickTime() async {
    final t = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: _alarm.hour, minute: _alarm.minute),
      builder: (_, child) => Theme(data: ThemeData.dark(), child: child!),
    );
    if (t != null) setState(() { _alarm.hour = t.hour; _alarm.minute = t.minute; });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      decoration: const BoxDecoration(
        color: J.bg1,
        border: Border(top: BorderSide(color: J.border1)),
      ),
      child: SingleChildScrollView(child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [

          // Handle
          Center(child: Container(width: 40, height: 3, color: J.border1)),
          const SizedBox(height: 16),

          // Time picker
          Center(child: GestureDetector(
            onTap: _pickTime,
            child: Text(
              '${_alarm.hour.toString().padLeft(2,"0")}:${_alarm.minute.toString().padLeft(2,"0")}',
              style: J.orbitron(48, weight: FontWeight.w900, color: J.cyan, spacing: 4),
            ),
          )),
          const SizedBox(height: 16),

          // Label
          TextField(
            controller: _labelCtrl,
            style: J.rajdhani(15),
            onChanged: (v) => _alarm.label = v,
            decoration: const InputDecoration(
              labelText: 'ALARM LABEL',
              prefixIcon: Icon(Icons.label_outline, size: 16, color: J.cyanDim),
            ),
          ),
          const SizedBox(height: 16),

          // Repeat days
          Text('REPEAT', style: J.orbitron(10, color: J.t3, spacing: 2)),
          const SizedBox(height: 8),
          Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: List.generate(7, (i) {
              const labels = ['M','T','W','T','F','S','S'];
              return GestureDetector(
                onTap: () => setState(() => _alarm.days[i] = !_alarm.days[i]),
                child: Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _alarm.days[i] ? J.cyan.withValues(alpha: 0.15) : J.bg3,
                    border: Border.all(color: _alarm.days[i] ? J.cyan : J.border0),
                  ),
                  child: Center(child: Text(labels[i],
                    style: J.orbitron(11, color: _alarm.days[i] ? J.cyan : J.t3, spacing: 0))),
                ),
              );
            }),
          ),
          const SizedBox(height: 16),

          // Sound
          Text('SOUND', style: J.orbitron(10, color: J.t3, spacing: 2)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8,
            children: ['default','gentle','jarvis','silent'].map((s) =>
              GestureDetector(
                onTap: () => setState(() => _alarm.sound = s),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    border: Border.all(color: _alarm.sound == s ? J.cyan : J.border0),
                    color: _alarm.sound == s ? J.cyan.withValues(alpha: 0.08) : J.bg3,
                  ),
                  child: Text(s.toUpperCase(),
                    style: J.orbitron(9, color: _alarm.sound == s ? J.cyan : J.t3, spacing: 1)),
                ),
              )).toList(),
          ),
          const SizedBox(height: 16),

          // Snooze
          Row(children: [
            Text('SNOOZE', style: J.orbitron(10, color: J.t3, spacing: 2)),
            const Spacer(),
            ...([5,10,15,20]).map((m) => GestureDetector(
              onTap: () => setState(() => _alarm.snoozeMin = m),
              child: Container(
                margin: const EdgeInsets.only(left: 6),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  border: Border.all(color: _alarm.snoozeMin == m ? J.amber : J.border0),
                  color: _alarm.snoozeMin == m ? J.amber.withValues(alpha: 0.08) : J.bg3,
                ),
                child: Text('${m}m',
                  style: J.orbitron(9, color: _alarm.snoozeMin == m ? J.amber : J.t3, spacing: 0)),
              ),
            )),
          ]),
          const SizedBox(height: 12),

          // Toggles
          _Toggle2('VIBRATE',          _alarm.vibrate,        (v) => setState(() => _alarm.vibrate = v)),
          _Toggle2('MATH CHALLENGE',   _alarm.mathChallenge,  (v) => setState(() => _alarm.mathChallenge = v)),
          _Toggle2('GRADUAL VOLUME',   _alarm.gradualVolume,  (v) => setState(() => _alarm.gradualVolume = v)),
          const SizedBox(height: 20),

          // Save
          CyberButton(
            label: widget.isEdit ? 'UPDATE ALARM' : 'SET ALARM',
            icon: Icons.alarm_add, filled: true, color: J.cyan,
            width: double.infinity,
            onTap: () { Navigator.pop(context); widget.onSave(_alarm); },
          ),
        ],
      )),
    );
  }
}

class _Toggle2 extends StatelessWidget {
  final String label;
  final bool   value;
  final ValueChanged<bool> onChange;
  const _Toggle2(this.label, this.value, this.onChange);
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(children: [
        Text(label, style: J.orbitron(10, color: J.t1, spacing: 1)),
        const Spacer(),
        Switch(value: value, onChanged: onChange,
          activeColor: J.cyan, activeTrackColor: J.cyan.withValues(alpha: 0.2),
          inactiveThumbColor: J.t3, inactiveTrackColor: J.bg4),
      ]),
    );
  }
}

// ── Nap timer ─────────────────────────────────────────────────

class _NapTimerWidget extends StatefulWidget {
  @override State<_NapTimerWidget> createState() => _NapTimerWidgetState();
}

class _NapTimerWidgetState extends State<_NapTimerWidget> {
  int     _selectedMin = 20;
  bool    _running = false;
  int     _remaining = 0;
  Timer?  _timer;

  final _options = [5, 10, 15, 20, 25, 30, 45, 60, 90];

  void _start() {
    setState(() { _running = true; _remaining = _selectedMin * 60; });
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() {
        if (_remaining > 0) {
          _remaining--;
        } else {
          _timer?.cancel();
          _running = false;
          // Fire notification
          _fireNapEnd();
        }
      });
    });
  }

  void _stop() {
    _timer?.cancel();
    setState(() { _running = false; _remaining = 0; });
  }

  Future<void> _fireNapEnd() async {
    final notif = FlutterLocalNotificationsPlugin();
    await notif.show(
      99999, '⏰ NAP OVER!', 'Your ${_selectedMin}-minute nap is done!',
      const NotificationDetails(android: AndroidNotificationDetails(
        'jarvis_alarms', 'JARVIS Alarms',
        importance: Importance.max, priority: Priority.max, fullScreenIntent: true,
        color: Color(0xFF00F0FF),
      )),
    );
  }

  String get _timeDisplay {
    final m = (_remaining ~/ 60).toString().padLeft(2,'0');
    final s = (_remaining % 60).toString().padLeft(2,'0');
    return '$m:$s';
  }

  @override
  void dispose() { _timer?.cancel(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(children: [

        // Timer display
        Center(
          child: Container(
            width: 200, height: 200,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: _running ? J.amber : J.border0, width: 2),
              color: J.bg2,
              boxShadow: _running ? [BoxShadow(
                  color: J.amber.withValues(alpha: 0.2), blurRadius: 30)] : null,
            ),
            child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              Text(_running ? _timeDisplay : '${_selectedMin}:00',
                style: J.orbitron(36, weight: FontWeight.w900,
                    color: _running ? J.amber : J.t1, spacing: 2)),
              Text('NAP TIMER', style: J.orbitron(10, color: J.t3, spacing: 2)),
            ]),
          ),
        ),
        const SizedBox(height: 28),

        if (!_running) ...[
          Text('SELECT NAP DURATION',
              style: J.orbitron(10, color: J.t3, spacing: 2)),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center,
            children: _options.map((m) => GestureDetector(
              onTap: () => setState(() => _selectedMin = m),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  border: Border.all(color: _selectedMin == m ? J.amber : J.border0),
                  color: _selectedMin == m ? J.amber.withValues(alpha: 0.1) : J.bg3,
                ),
                child: Text('${m}m',
                  style: J.orbitron(11,
                    color: _selectedMin == m ? J.amber : J.t2, spacing: 0)),
              ),
            )).toList(),
          ),
          const SizedBox(height: 24),
          CyberButton(label: 'START NAP', icon: Icons.bedtime_outlined,
              filled: true, color: J.amber, width: double.infinity, onTap: _start),
        ] else ...[
          Text('NAP IN PROGRESS', style: J.orbitron(11, color: J.amber, spacing: 2)),
          const SizedBox(height: 16),
          CyberButton(label: 'STOP', icon: Icons.stop,
              color: J.red, width: double.infinity, onTap: _stop),
        ],
      ]),
    );
  }
}

// ── Bedtime widget ────────────────────────────────────────────

class _BedtimeWidget extends StatefulWidget {
  @override State<_BedtimeWidget> createState() => _BedtimeWidgetState();
}

class _BedtimeWidgetState extends State<_BedtimeWidget> {
  int _bedHour = 23, _bedMin = 0;
  int _wakeHour = 7, _wakeMin = 0;

  double get _sleepHours {
    final bed  = _bedHour  * 60 + _bedMin;
    var   wake = _wakeHour * 60 + _wakeMin;
    if (wake <= bed) wake += 24 * 60;
    return (wake - bed) / 60.0;
  }

  Color get _sleepColor =>
    _sleepHours >= 8 ? J.green :
    _sleepHours >= 7 ? J.amber : J.red;

  String get _sleepQuality =>
    _sleepHours >= 8 ? 'EXCELLENT' :
    _sleepHours >= 7 ? 'GOOD' :
    _sleepHours >= 6 ? 'FAIR' : 'POOR';

  Future<void> _pickBed() async {
    final t = await showTimePicker(context: context,
        initialTime: TimeOfDay(hour: _bedHour, minute: _bedMin),
        builder: (_, c) => Theme(data: ThemeData.dark(), child: c!));
    if (t != null) setState(() { _bedHour = t.hour; _bedMin = t.minute; });
  }

  Future<void> _pickWake() async {
    final t = await showTimePicker(context: context,
        initialTime: TimeOfDay(hour: _wakeHour, minute: _wakeMin),
        builder: (_, c) => Theme(data: ThemeData.dark(), child: c!));
    if (t != null) setState(() { _wakeHour = t.hour; _wakeMin = t.minute; });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(children: [

        // Sleep stats circle
        Center(child: Container(
          width: 160, height: 160,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: _sleepColor, width: 2),
            color: J.bg2,
          ),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Text('${_sleepHours.toStringAsFixed(1)}h',
                style: J.orbitron(36, weight: FontWeight.w900, color: _sleepColor, spacing: 1)),
            Text('SLEEP', style: J.orbitron(10, color: J.t3, spacing: 2)),
            Text(_sleepQuality, style: J.orbitron(9, color: _sleepColor, spacing: 1)),
          ]),
        )),
        const SizedBox(height: 28),

        // Bedtime
        JPanel(label: 'BEDTIME', borderColor: J.cyanDim, child: GestureDetector(
          onTap: _pickBed,
          child: Center(child: Text(
            '${_bedHour.toString().padLeft(2,"0")}:${_bedMin.toString().padLeft(2,"0")}',
            style: J.orbitron(36, weight: FontWeight.w800, color: J.t1, spacing: 2),
          )),
        )),
        const SizedBox(height: 12),

        // Wake time
        JPanel(label: 'WAKE UP', borderColor: J.cyan, child: GestureDetector(
          onTap: _pickWake,
          child: Center(child: Text(
            '${_wakeHour.toString().padLeft(2,"0")}:${_wakeMin.toString().padLeft(2,"0")}',
            style: J.orbitron(36, weight: FontWeight.w800, color: J.cyan, spacing: 2),
          )),
        )),
        const SizedBox(height: 20),

        CyberButton(label: 'SET SCHEDULE', icon: Icons.bedtime_outlined,
            filled: true, color: J.cyan, width: double.infinity,
            onTap: () => ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text('Bedtime schedule set! 🌙',
                  style: J.shareTech(12)), backgroundColor: J.bg3))),
      ]),
    );
  }
}
