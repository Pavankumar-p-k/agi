// lib/models/offline_models.dart
// All data models for offline-first JARVIS

class ReminderModel {
  final int?     id;
  final String   title;
  final String   description;
  final DateTime remindAt;
  final String   repeat;      // none|daily|weekly|monthly
  bool           isDone;
  final bool     isAlarm;     // true = fires alarm sound
  final String   alarmSound;

  ReminderModel({
    this.id,
    required this.title,
    this.description = '',
    required this.remindAt,
    this.repeat = 'none',
    this.isDone = false,
    this.isAlarm = false,
    this.alarmSound = 'default',
  });

  Map<String, dynamic> toMap() => {
    if (id != null) 'id': id,
    'title':       title,
    'description': description,
    'remind_at':   remindAt.toIso8601String(),
    'repeat':      repeat,
    'is_done':     isDone ? 1 : 0,
    'is_alarm':    isAlarm ? 1 : 0,
    'alarm_sound': alarmSound,
    'synced':      0,
  };

  static ReminderModel fromMap(Map<String, dynamic> m) => ReminderModel(
    id:          m['id'],
    title:       m['title'],
    description: m['description'] ?? '',
    remindAt:    DateTime.parse(m['remind_at']),
    repeat:      m['repeat'] ?? 'none',
    isDone:      m['is_done'] == 1,
    isAlarm:     m['is_alarm'] == 1,
    alarmSound:  m['alarm_sound'] ?? 'default',
  );
}


class NoteModel {
  final int?     id;
  String         title;
  String         content;
  String         tags;
  bool           pinned;

  NoteModel({
    this.id,
    required this.title,
    this.content = '',
    this.tags    = '',
    this.pinned  = false,
  });

  Map<String, dynamic> toMap() => {
    if (id != null) 'id': id,
    'title':   title,
    'content': content,
    'tags':    tags,
    'pinned':  pinned ? 1 : 0,
    'synced':  0,
  };

  static NoteModel fromMap(Map<String, dynamic> m) => NoteModel(
    id:      m['id'],
    title:   m['title'],
    content: m['content'] ?? '',
    tags:    m['tags'] ?? '',
    pinned:  m['pinned'] == 1,
  );
}
