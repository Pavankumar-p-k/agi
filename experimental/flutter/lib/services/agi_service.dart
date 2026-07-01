// lib/services/agi_service.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

String get _base => '${ApiConfig.baseUrl}/agi';

class AGIService {
  Future<Map<String,dynamic>> getStatus() async {
    final r = await http.get(Uri.parse('$_base/status'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getGoals() async {
    final r = await http.get(Uri.parse('$_base/goals'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getDecisions(int n) async {
    final r = await http.get(Uri.parse('$_base/decisions?n=$n'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getPredictions() async {
    final r = await http.get(Uri.parse('$_base/predictions'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<Map<String,dynamic>> getPatterns() async {
    final r = await http.get(Uri.parse('$_base/patterns'));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<void> createGoal(String description) async {
    await http.post(Uri.parse('$_base/goal'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode({'description': description}));
  }
  Future<Map<String,dynamic>> solve(String problem) async {
    final r = await http.post(Uri.parse('$_base/solve'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode({'problem': problem}));
    return jsonDecode(r.body) as Map<String,dynamic>;
  }
  Future<void> configure({bool? autonomousEnabled, double? confidenceThreshold, bool? dndMode}) async {
    final body = <String,dynamic>{};
    if (autonomousEnabled  != null) body['autonomous_enabled']   = autonomousEnabled;
    if (confidenceThreshold != null) body['confidence_threshold'] = confidenceThreshold;
    if (dndMode != null) body['dnd_mode'] = dndMode;
    await http.post(Uri.parse('$_base/config'),
      headers: {'Content-Type':'application/json'},
      body: jsonEncode(body));
  }
}
