// lib/ai/offline_ai.dart  — UPDATED v2
// Now powered by LocalModel + conversation_dataset.dart
// 25 intent categories, 880+ trigger phrases, 200+ reply variants
// Telugu + English + Tenglish fully supported

import 'dart:math';
import '../db/local_db.dart';
import '../models/offline_models.dart';
import 'local_model.dart';

class OfflineAI {
  final _rand  = Random();
  final _model = LocalModel();

  static const _identityTriggers = [
    'evaru nuvu','evaru nuvvu','nuvvu evaru','neevaru','nee peru enti',
    'mee peru enti','idi evaru','evari tho matladutunnanu','nuvvu evaru bro',
    'jarvis na nuvvu','nuvvu robot va','nuvvu ai va','nuvvu manishi va',
    'bot na nuvvu','assistant na','who are you','who r u','who is this',
    'whos this','is this pavan','are you pavan','are you a bot','are you ai',
    'are you real','are you human','what are you','introduce yourself',
    'who am i talking to','bro nuvvu evaru','da nuvvu evaru','anna nuvvu evaru',
    'pavan na ikkade','pavan unnada bro','this pavan na','nuvvu ai na bro',
    'bot tho matladutunna na',
  ];

  static const _reminderTriggers = [
    'remind me','set reminder','set alarm','alarm set cheyyi','reminder petto',
    'remind cheyyi','gurtu petto','morning alarm','wake me up','notify me',
    'reminder add cheyyi','alarm petto','reminder set cheyyi','alarm tomorrow',
    'alarm repu','wake cheyyi','reminder fix cheyyi',
  ];

  static const _noteTriggers = [
    'note cheyyi','note down','save this','remember this','write down',
    'note add cheyyi','save note','write note','note petto',
    'ee vishayam save cheyyi','note chesukoo','save chesukoo','note raa',
  ];

  Future<AIResponse> process(String input,
      {String friendType = 'normal', String language = 'mixed'}) async {
    final text = input.toLowerCase().trim();

    if (_matches(text, _identityTriggers))  return _buildIdentityReveal();
    if (_matches(text, _reminderTriggers))  return await _handleReminder(input);
    if (_matches(text, _noteTriggers))      return await _handleNote(input);

    if (text.contains('reminder') &&
        (text.contains('list')||text.contains('show')||
         text.contains('cheppu')||text.contains('anni')||
         text.contains('chudandi')||text.contains('em undi'))) {
      return await _listReminders();
    }

    if (text.contains('note') &&
        (text.contains('list')||text.contains('show')||
         text.contains('anni')||text.contains('cheppu'))) {
      return await _listNotes();
    }

    if (text.contains('time')||text.contains('samayam')||
        text.contains('ippudu entha')||text.contains('ganta entha')) {
      final now = DateTime.now();
      final t = '${now.hour.toString().padLeft(2,"0")}:${now.minute.toString().padLeft(2,"0")}';
      return AIResponse(text: 'Ippudu time $t bro', action: AIAction.none);
    }

    if ((text.contains('date')||text.contains('today')||
         text.contains('roju')||text.contains('ee roju')) &&
        !text.contains('update')) {
      final now  = DateTime.now();
      final days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
      return AIResponse(
        text: 'Intha date ${now.day}/${now.month}/${now.year}, ${days[now.weekday%7]} bro',
        action: AIAction.none,
      );
    }

    // ── Local model handles everything else ──
    final text = await LocalModel.generate(input);
    return AIResponse(
      text:   text ?? 'Sorry, I could not generate a response.',
      action: AIAction.none,
      data:   {'intent': 'unknown', 'confidence': 0.0},
    );
  }

  Future<AIResponse> _buildIdentityReveal() async {
    final ownerName = await localDB.getIdentity('owner_name');
    final revealEn  = await localDB.getIdentity('reveal_response_en');
    final revealTe  = await localDB.getIdentity('reveal_response_te');
    final text      = _rand.nextBool() ? revealTe : revealEn;
    return AIResponse(text: text, action: AIAction.identityReveal,
        data: {'owner': ownerName});
  }

  Future<AIResponse> _handleReminder(String input) async {
    final parsed = _parseDateTime(input);
    final title  = _extractTitle(input);
    if (parsed == null) {
      return AIResponse(
        text: 'Epudu reminder pettali bro? Time cheppu — '
              'like "tomorrow 9am", "30 minutes lo", or "Monday 8am"',
        action: AIAction.askForTime,
      );
    }
    final r = ReminderModel(
      title: title, description: input, remindAt: parsed,
      isAlarm: input.contains('alarm')||input.contains('wake')||input.contains('morning'),
    );
    final id = await localDB.insertReminder(r);
    return AIResponse(
      text: 'Done bro! "$title" ki ${_formatDT(parsed)} ki reminder set chesanu ✓',
      action: AIAction.reminderSet,
      data: {'id': id, 'remind_at': parsed.toIso8601String(), 'title': title},
    );
  }

  Future<AIResponse> _handleNote(String input) async {
    var content = input;
    for (final t in _noteTriggers) content = content.replaceAll(t,'').trim();
    content = content.replaceAll(RegExp(r'^[:—\-\s]+'),'').trim();
    if (content.isEmpty) return AIResponse(text:'Em note cheyali bro? Cheppu save chestanu', action:AIAction.askForContent);
    final n  = NoteModel(title: content.length>40?'${content.substring(0,40)}...':content, content: content);
    final id = await localDB.insertNote(n);
    return AIResponse(text:'Noted bro ✓ Save chesanu', action:AIAction.noteSaved, data:{'id':id,'content':content});
  }

  Future<AIResponse> _listReminders() async {
    final list = await localDB.getReminders(onlyPending: true);
    if (list.isEmpty) return AIResponse(text:'Ippudu pending reminders emi ledu bro', action:AIAction.listReminders, data:{'reminders':[]});
    final lines = list.take(5).map((r)=>'• ${r.title} — ${_formatDT(r.remindAt)}').join('\n');
    return AIResponse(text:'Upcoming reminders:\n$lines', action:AIAction.listReminders, data:{'reminders':list.map((r)=>r.toMap()).toList()});
  }

  Future<AIResponse> _listNotes() async {
    final list = await localDB.getNotes();
    if (list.isEmpty) return AIResponse(text:'Emi notes ledu ippudu bro', action:AIAction.listNotes, data:{'notes':[]});
    final lines = list.take(5).map((n)=>'• ${n.title}').join('\n');
    return AIResponse(text:'Mee notes:\n$lines', action:AIAction.listNotes, data:{'notes':list.map((n)=>n.toMap()).toList()});
  }

  DateTime? _parseDateTime(String input) {
    final text = input.toLowerCase();
    final now  = DateTime.now();
    final minM = RegExp(r'(\d+)\s*(?:min|minutes|mins|nimishalu)').firstMatch(text);
    if (minM != null) return now.add(Duration(minutes: int.parse(minM.group(1)!)));
    final hrM = RegExp(r'(\d+)\s*(?:hour|hours|hr|hrs|gantalu)').firstMatch(text);
    if (hrM != null) return now.add(Duration(hours: int.parse(hrM.group(1)!)));
    final timeM = RegExp(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?').firstMatch(text);
    if (timeM != null) {
      int hour = int.parse(timeM.group(1)!);
      int minute = int.tryParse(timeM.group(2) ?? '0') ?? 0;
      final ampm = timeM.group(3);
      if (ampm == 'pm' && hour < 12) hour += 12;
      if (ampm == 'am' && hour == 12) hour = 0;
      var dt = DateTime(now.year, now.month, now.day, hour, minute);
      if (dt.isBefore(now)) dt = dt.add(const Duration(days: 1));
      if (text.contains('tomorrow') || text.contains('repu')) dt = dt.add(const Duration(days: 1));
      return dt;
    }
    if (text.contains('tomorrow morning')||text.contains('repu morning')) return DateTime(now.year,now.month,now.day+1,8,0);
    if (text.contains('tonight')||text.contains('night')) return DateTime(now.year,now.month,now.day,22,0);
    final dayMap = {'monday':1,'tuesday':2,'wednesday':3,'thursday':4,'friday':5,'saturday':6,'sunday':7};
    for (final e in dayMap.entries) {
      if (text.contains(e.key)) { int diff=e.value-now.weekday; if(diff<=0)diff+=7; return DateTime(now.year,now.month,now.day+diff,9,0); }
    }
    return null;
  }

  String _extractTitle(String input) {
    var t = input.toLowerCase();
    for (final trigger in _reminderTriggers) t = t.replaceAll(trigger,'');
    t = t.replaceAll(RegExp(r'at \d{1,2}(:\d{2})?\s*(am|pm)?'),'');
    t = t.replaceAll(RegExp(r'in \d+ (min|hour|hr)s?'),'');
    t = t.replaceAll(RegExp(r'tomorrow|tonight|morning'),'');
    t = t.replaceAll(RegExp(r'\s+'),' ').trim();
    return t.isNotEmpty ? t : 'Reminder';
  }

  String _formatDT(DateTime dt) {
    final now = DateTime.now(); final diff = dt.difference(now);
    if (diff.inMinutes < 60) return '${diff.inMinutes} minutes lo';
    if (diff.inHours   < 24) return 'today ${dt.hour}:${dt.minute.toString().padLeft(2,"0")}';
    return '${dt.day}/${dt.month} ${dt.hour.toString().padLeft(2,"0")}:${dt.minute.toString().padLeft(2,"0")}';
  }

  bool _matches(String text, List<String> triggers) => triggers.any((t) => text.contains(t));
  T _pick<T>(List<T> list) => list[_rand.nextInt(list.length)];
}

enum AIAction { none, identityReveal, reminderSet, noteSaved, listReminders, listNotes, askForTime, askForContent, callHandled }

class AIResponse {
  final String text;
  final AIAction action;
  final Map<String, dynamic>? data;
  const AIResponse({required this.text, this.action = AIAction.none, this.data});
}
