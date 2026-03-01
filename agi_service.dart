// lib/services/agi_service.dart
import 'dart:convert';
import 'package:http/http.dart' as http;

const _defaultApiBase = 'http://10.0.2.2:8000';

class AGIService {
  AGIService({String? baseUrl})
      : _baseUrl = (baseUrl ??
                const String.fromEnvironment(
                  'AGI_BASE_URL',
                  defaultValue: _defaultApiBase,
                ))
            .replaceAll(RegExp(r'/$'), '');

  final String _baseUrl;

  String get _agiBase => '$_baseUrl/agi';

  Future<Map<String,dynamic>> getStatus() async {
    final r = await http.get(Uri.parse('$_agiBase/status'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getGoals() async {
    final r = await http.get(Uri.parse('$_agiBase/goals'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getDecisions(int n) async {
    final r = await http.get(Uri.parse('$_agiBase/decisions?n=$n'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getPredictions() async {
    final r = await http.get(Uri.parse('$_agiBase/predictions'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getPatterns() async {
    final r = await http.get(Uri.parse('$_agiBase/patterns'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<void> createGoal(String description) async {
    await http.post(Uri.parse('$_agiBase/goal'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode({'description': description}));
  }
  Future<Map<String,dynamic>> solve(String problem) async {
    final r = await http.post(Uri.parse('$_agiBase/solve'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode({'problem': problem}));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<void> configure({bool? autonomousEnabled, double? confidenceThreshold, bool? dndMode}) async {
    final body = <String,dynamic>{};
    if (autonomousEnabled  != null) body['autonomous_enabled']   = autonomousEnabled;
    if (confidenceThreshold != null) body['confidence_threshold'] = confidenceThreshold;
    if (dndMode != null) body['dnd_mode'] = dndMode;
    await http.post(Uri.parse('$_agiBase/config'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode(body));
  }

  Future<Map<String,dynamic>> configureCallAssistant(Map<String,dynamic> body) async {
    final r = await http.post(Uri.parse('$_agiBase/call/config'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode(body));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }

  Future<Map<String,dynamic>> incomingCall({
    required String callerName,
    String relation = '',
    String phone = '',
    bool allowAutoActions = false,
  }) async {
    final r = await http.post(Uri.parse('$_agiBase/call/incoming'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode({
        'caller_name': callerName,
        'relation': relation,
        'phone': phone,
        'allow_auto_actions': allowAutoActions,
      }));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }

  Future<Map<String,dynamic>> styledReply({
    required String incomingText,
    String intent = 'small_talk',
    String contact = '',
    String platform = 'auto',
    bool autoSend = false,
  }) async {
    final r = await http.post(Uri.parse('$_agiBase/style/reply'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode({
        'incoming_text': incomingText,
        'intent': intent,
        'contact': contact,
        'platform': platform,
        'auto_send': autoSend,
      }));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }

  Future<Map<String,dynamic>> getWorkSummary() async {
    final r = await http.get(Uri.parse('$_agiBase/work/summary'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
}
