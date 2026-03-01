
// lib/models/models.dart
import 'package:flutter/foundation.dart';

// ── Chat Message ──
class ChatMessage {
  final String role;     // user | assistant
  final String message;
  final DateTime timestamp;

  ChatMessage({required this.role, required this.message, DateTime? timestamp})
      : timestamp = timestamp ?? DateTime.now();

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
    role: j['role'],
    message: j['message'],
    timestamp: DateTime.tryParse(j['ts'] ?? '') ?? DateTime.now(),
  );
}

// ── Reminder ──
class Reminder {
  final int id;
  final String title;
  final String? description;
  final DateTime remindAt;
  final String repeat;
  bool isDone;

  Reminder({
    required this.id,
    required this.title,
    this.description,
    required this.remindAt,
    this.repeat = 'none',
    this.isDone = false,
  });

  factory Reminder.fromJson(Map<String, dynamic> j) => Reminder(
    id: j['id'],
    title: j['title'],
    description: j['description'],
    remindAt: DateTime.parse(j['remind_at']),
    repeat: j['repeat'] ?? 'none',
    isDone: j['is_done'] ?? false,
  );
}

// ── Note ──
class Note {
  final int id;
  String title;
  String content;
  String? tags;
  final DateTime updatedAt;

  Note({
    required this.id,
    required this.title,
    required this.content,
    this.tags,
    required this.updatedAt,
  });

  factory Note.fromJson(Map<String, dynamic> j) => Note(
    id: j['id'],
    title: (j['title'] ?? '').toString(),
    content: (j['content'] ?? '').toString(),
    tags: j['tags'],
    updatedAt: DateTime.tryParse(j['updated_at'] ?? '') ?? DateTime.now(),
  );
}

// ── Activity ──
class Activity {
  final String type;
  final String description;
  final DateTime timestamp;

  Activity({required this.type, required this.description, required this.timestamp});

  factory Activity.fromJson(Map<String, dynamic> j) => Activity(
    type: j['type'],
    description: j['description'],
    timestamp: DateTime.tryParse(j['ts'] ?? '') ?? DateTime.now(),
  );
}

// ── Daily Summary ──
class DailySummary {
  final String date;
  final String summary;
  final double productivityScore;
  final Map<String, dynamic>? rawData;

  DailySummary({
    required this.date,
    required this.summary,
    required this.productivityScore,
    this.rawData,
  });

  factory DailySummary.fromJson(Map<String, dynamic> j) => DailySummary(
    date: j['date'] ?? '',
    summary: j['summary'] ?? '',
    productivityScore: (j['productivity_score'] as num?)?.toDouble() ?? 5.0,
    rawData: j['data'],
  );

  List<String> get insights {
    final data = rawData;
    if (data == null) return [];
    return List<String>.from(data['insights'] ?? []);
  }
}

// ── Known Face ──
class KnownFace {
  final int id;
  final String name;
  final String relation;
  final String accessLevel;
  final int imageCount;

  KnownFace({
    required this.id,
    required this.name,
    required this.relation,
    required this.accessLevel,
    required this.imageCount,
  });

  factory KnownFace.fromJson(Map<String, dynamic> j) => KnownFace(
    id: j['id'],
    name: j['name'],
    relation: j['relation'] ?? 'unknown',
    accessLevel: j['access_level'] ?? 'visitor',
    imageCount: j['image_count'] ?? 0,
  );
}

// ── Track ──
class Track {
  final String title;
  final String artist;
  final String path;
  final int duration;

  Track({
    required this.title,
    required this.artist,
    required this.path,
    required this.duration,
  });

  factory Track.fromJson(Map<String, dynamic> j) => Track(
    title: j['title'] ?? 'Unknown',
    artist: j['artist'] ?? 'Unknown',
    path: j['path'] ?? '',
    duration: j['duration'] ?? 0,
  );

  String get durationFormatted {
    final m = duration ~/ 60;
    final s = duration % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }
}

// ── Media Status ──
class MediaStatus {
  final String state;
  final Track? track;
  final int position;
  final int volume;
  final bool shuffle;
  final bool repeat;

  MediaStatus({
    required this.state,
    this.track,
    required this.position,
    required this.volume,
    required this.shuffle,
    required this.repeat,
  });

  factory MediaStatus.fromJson(Map<String, dynamic> j) => MediaStatus(
    state: j['state'] ?? 'stopped',
    track: j['track'] != null ? Track.fromJson(j['track']) : null,
    position: j['position'] ?? 0,
    volume: j['volume'] ?? 80,
    shuffle: j['shuffle'] ?? false,
    repeat: j['repeat'] ?? false,
  );
}

// ── File Entry ──
class FileEntry {
  final String name;
  final bool isDir;
  final int size;
  final DateTime modified;

  FileEntry({
    required this.name,
    required this.isDir,
    required this.size,
    required this.modified,
  });

  factory FileEntry.fromJson(Map<String, dynamic> j) => FileEntry(
    name: j['name'],
    isDir: j['is_dir'],
    size: j['size'] ?? 0,
    modified: DateTime.tryParse(j['modified'] ?? '') ?? DateTime.now(),
  );

  String get sizeFormatted {
    if (size < 1024) return '${size}B';
    if (size < 1024 * 1024) return '${(size / 1024).toStringAsFixed(1)}KB';
    if (size < 1024 * 1024 * 1024) return '${(size / (1024 * 1024)).toStringAsFixed(1)}MB';
    return '${(size / (1024 * 1024 * 1024)).toStringAsFixed(1)}GB';
  }
}
