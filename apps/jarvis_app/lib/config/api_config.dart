// lib/config/api_config.dart
class ApiConfig {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const String wsUrl = String.fromEnvironment(
    'WS_URL',
    defaultValue: 'ws://127.0.0.1:8000/ws',
  );

  // Supabase config for remote connectivity
  static const String supabaseUrl = String.fromEnvironment(
    'SUPABASE_URL',
    defaultValue: 'https://qjdepubbvjpqnphanxdp.supabase.co',
  );

  // Google & DroQ API keys (passed via --dart-define at build time)
  static const String googleApiKey = String.fromEnvironment(
    'GOOGLE_API_KEY',
    defaultValue: '',
  );

  static const String droqApiKey = String.fromEnvironment(
    'DROQ_API_KEY',
    defaultValue: '',
  );

  static const String supabaseAnonKey = String.fromEnvironment(
    'SUPABASE_ANON_KEY',
    defaultValue: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFqZGVwdWJidmpwcW5waGFueGRwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg4MjM3NzAsImV4cCI6MjA5NDM5OTc3MH0.aUKz-1gf0OQ6L1ginsgpTJZ_s2aqCTvtzzkkgTXFrOo',
  );

  static const String health = '/health';
  static const String chat = '/api/chat';
  static const String chatHistory = '/api/chat/history';
  static const String sessions = '/api/sessions';

  static const String reminders = '/api/reminders';
  static const String notes = '/api/notes';
  static const String activity = '/api/activity/today';
  static const String summary = '/api/activity/summary';

  static const String messageSend = '/api/message/send';

  static const String facesIdentify = '/api/faces/identify';
  static const String facesRegister = '/api/faces/register';
  static const String facesList = '/api/faces';

  static const String mediaStatus = '/api/media/status';
  static const String mediaPlay = '/api/media/play';
  static const String mediaPause = '/api/media/pause';
  static const String mediaNext = '/api/media/next';
  static const String mediaVolume = '/api/media/volume';
  static const String mediaPlaylist = '/api/media/playlist';
  static const String musicSuggest = '/api/media/suggest';

  static const String files = '/api/files';

  // Features
  static const String features = '/api/features';
  static const String featureReport = '/api/features/report';
  static const String featureCategories = '/api/features/categories';

  // Integrations
  static const String integrations = '/api/integrations';
  static const String integrationsHealth = '/api/integrations/health';

  // Diagnostics
  static const String diagnostics = '/api/diagnostics';
  static const String diagnosticsModels = '/api/diagnostics/models';
  static const String diagnosticsIntegrations = '/api/diagnostics/integrations';
  static const String diagnosticsVoice = '/api/diagnostics/voice';
  static const String diagnosticsEnvironment = '/api/diagnostics/environment';

  // Models
  static const String models = '/api/models';
  static const String modelGroups = '/api/models/groups';
  static const String settings = '/api/settings';

  // Agents
  static const String agents = '/api/v1/agents';

  // Automation
  static const String automationCommand = '/api/automation/command';

  // Voice
  static const String stt = '/stt';
  static const String tts = '/tts';

  // Build System (Phase 4/5)
  static const String buildProjects = '/api/build/projects';
  static const String buildStatus = '/api/build/status';  // + /{project}
  static const String buildInterrupt = '/api/build/interrupt';  // + /{project}
  static const String buildOverride = '/api/build/override';  // + /{project}
  static const String buildCheckpoints = '/api/build/checkpoints';  // + /{project}
  static const String buildDecisions = '/api/build/decisions';  // + /{project}
  static const String buildGovernor = '/api/build/governor/history';  // + /{project}
  static const String buildEnvironment = '/api/build/environment';
  static const String buildIdentity = '/api/build/identity';
}
