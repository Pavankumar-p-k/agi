// lib/models/models.dart
import '../ai/message_analyzer.dart';

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
    title: j['title'],
    content: j['content'],
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

// ── Inbox Message ─────────────────────────────────────────────
class InboxMessage {
  final String sender;
  final String platform;
  final String cacheKey;
  final String text;
  final MessageAnalysis analysis;
  final DateTime timestamp;
  final String? customReply;

  InboxMessage({
    required this.sender,
    required this.platform,
    required this.cacheKey,
    required this.text,
    required this.analysis,
    required this.timestamp,
    this.customReply,
  });

  String get replyText => customReply ?? analysis.suggestedReply;
}

// ── Build System (Phase 4/5) ──────────────────────────────────

class BuildProject {
  final String name;
  final String status;
  final String goal;
  final int retries;
  final int issues;
  final String createdAt;

  BuildProject({
    required this.name,
    required this.status,
    required this.goal,
    required this.retries,
    required this.issues,
    required this.createdAt,
  });

  factory BuildProject.fromJson(Map<String, dynamic> j) => BuildProject(
    name: j['name'] ?? '',
    status: j['status'] ?? 'unknown',
    goal: j['goal'] ?? '',
    retries: j['retries'] ?? 0,
    issues: j['issues'] ?? 0,
    createdAt: j['created_at'] ?? '',
  );
}

class BuildDetail {
  final String name;
  final String status;
  final String goal;
  final int retries;
  final int maxRetries;
  final List<String> issues;
  final QualityScoreData? qualityScore;
  final Map<String, dynamic>? partialProgress;
  final List<Map<String, dynamic>> events;
  final List<Map<String, dynamic>> agentLog;

  BuildDetail({
    required this.name,
    required this.status,
    required this.goal,
    required this.retries,
    required this.maxRetries,
    required this.issues,
    this.qualityScore,
    this.partialProgress,
    required this.events,
    required this.agentLog,
  });

  factory BuildDetail.fromJson(Map<String, dynamic> j) => BuildDetail(
    name: j['name'] ?? '',
    status: j['status'] ?? 'unknown',
    goal: j['goal'] ?? '',
    retries: j['retries'] ?? 0,
    maxRetries: j['max_retries'] ?? 5,
    issues: List<String>.from(j['issues'] ?? []),
    qualityScore: j['quality_score'] != null
        ? QualityScoreData.fromJson(j['quality_score'])
        : null,
    partialProgress: j['partial_progress'] as Map<String, dynamic>?,
    events: List<Map<String, dynamic>>.from(j['events'] ?? []),
    agentLog: List<Map<String, dynamic>>.from(j['agent_log'] ?? []),
  );
}

class QualityScoreData {
  final double designConsistency;
  final double responsiveness;
  final double contentQuality;
  final double navigationQuality;
  final double codeQuality;
  final double total;
  final double average;

  QualityScoreData({
    required this.designConsistency,
    required this.responsiveness,
    required this.contentQuality,
    required this.navigationQuality,
    required this.codeQuality,
    required this.total,
    required this.average,
  });

  factory QualityScoreData.fromJson(Map<String, dynamic> j) => QualityScoreData(
    designConsistency: (j['design_consistency'] as num?)?.toDouble() ?? 0,
    responsiveness: (j['responsiveness'] as num?)?.toDouble() ?? 0,
    contentQuality: (j['content_quality'] as num?)?.toDouble() ?? 0,
    navigationQuality: (j['navigation_quality'] as num?)?.toDouble() ?? 0,
    codeQuality: (j['code_quality'] as num?)?.toDouble() ?? 0,
    total: (j['total'] as num?)?.toDouble() ?? 0,
    average: (j['average'] as num?)?.toDouble() ?? 0,
  );
}

class GovernorDecision {
  final String action;
  final String reason;
  final double confidence;
  final String details;

  GovernorDecision({
    required this.action,
    required this.reason,
    required this.confidence,
    required this.details,
  });

  factory GovernorDecision.fromJson(Map<String, dynamic> j) => GovernorDecision(
    action: j['action'] ?? '',
    reason: j['reason'] ?? '',
    confidence: (j['confidence'] as num?)?.toDouble() ?? 0,
    details: j['details'] ?? '',
  );
}

class EnvironmentSnapshot {
  final double diskFreeGb;
  final double diskTotalGb;
  final double memoryFreeMb;
  final double memoryTotalMb;
  final bool ollamaAvailable;
  final double ollamaLatencyMs;
  final bool networkReachable;
  final List<String> warnings;

  EnvironmentSnapshot({
    required this.diskFreeGb,
    required this.diskTotalGb,
    required this.memoryFreeMb,
    required this.memoryTotalMb,
    required this.ollamaAvailable,
    required this.ollamaLatencyMs,
    required this.networkReachable,
    required this.warnings,
  });

  factory EnvironmentSnapshot.fromJson(Map<String, dynamic> j) => EnvironmentSnapshot(
    diskFreeGb: (j['disk_free_gb'] as num?)?.toDouble() ?? 0,
    diskTotalGb: (j['disk_total_gb'] as num?)?.toDouble() ?? 0,
    memoryFreeMb: (j['memory_free_mb'] as num?)?.toDouble() ?? 0,
    memoryTotalMb: (j['memory_total_mb'] as num?)?.toDouble() ?? 0,
    ollamaAvailable: j['ollama_available'] ?? false,
    ollamaLatencyMs: (j['ollama_latency_ms'] as num?)?.toDouble() ?? 0,
    networkReachable: j['network_reachable'] ?? false,
    warnings: List<String>.from(j['warnings'] ?? []),
  );
}

class SystemIdentity {
  final String name;
  final String version;
  final List<String> capabilities;
  final List<String> limitations;
  final Map<String, dynamic> models;
  final Map<String, dynamic> tools;
  final Map<String, dynamic> buildSystem;
  final List<String> phasesImplemented;

  SystemIdentity({
    required this.name,
    required this.version,
    required this.capabilities,
    required this.limitations,
    required this.models,
    required this.tools,
    required this.buildSystem,
    required this.phasesImplemented,
  });

  factory SystemIdentity.fromJson(Map<String, dynamic> j) => SystemIdentity(
    name: j['name'] ?? 'JARVIS',
    version: j['version'] ?? '?',
    capabilities: List<String>.from(j['capabilities'] ?? []),
    limitations: List<String>.from(j['limitations'] ?? []),
    models: Map<String, dynamic>.from(j['models'] ?? {}),
    tools: Map<String, dynamic>.from(j['tools'] ?? {}),
    buildSystem: Map<String, dynamic>.from(j['build_system'] ?? {}),
    phasesImplemented: List<String>.from(j['phases_implemented'] ?? []),
  );
}

// ── Feature ──
class Feature {
  final String name;
  final String slug;
  final String status;
  final bool enabled;
  final String category;
  final String description;
  final String configKey;
  final List<String> dependencies;
  final String docsPath;

  Feature({
    required this.name,
    required this.slug,
    required this.status,
    required this.enabled,
    required this.category,
    required this.description,
    this.configKey = '',
    this.dependencies = const [],
    this.docsPath = '',
  });

  factory Feature.fromJson(Map<String, dynamic> j) => Feature(
    name: j['name'] ?? '',
    slug: j['slug'] ?? '',
    status: j['status'] ?? 'planned',
    enabled: j['enabled'] ?? false,
    category: j['category'] ?? '',
    description: j['description'] ?? '',
    configKey: j['config_key'] ?? '',
    dependencies: List<String>.from(j['dependencies'] ?? []),
    docsPath: j['docs_path'] ?? '',
  );
}

// ── Integration ──
class Integration {
  final String name;
  final bool connected;
  final Map<String, dynamic> status;

  Integration({
    required this.name,
    required this.connected,
    required this.status,
  });

  factory Integration.fromJson(Map<String, dynamic> j) => Integration(
    name: j['name'] ?? '',
    connected: j['connected'] ?? false,
    status: j['status'] ?? {},
  );

  bool get healthy => status['healthy'] ?? false;
  String? get error => status['error'];
}

// ── Agent ──
class Agent {
  final String name;
  final String description;
  final List<String> modes;
  final String defaultMode;

  Agent({
    required this.name,
    required this.description,
    required this.modes,
    required this.defaultMode,
  });

  factory Agent.fromJson(Map<String, dynamic> j) => Agent(
    name: j['name'] ?? '',
    description: j['description'] ?? '',
    modes: List<String>.from(j['modes'] ?? []),
    defaultMode: j['default_mode'] ?? 'normal',
  );
}
