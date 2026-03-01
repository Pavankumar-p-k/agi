import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../config/api_config.dart';

class AutomationService {
  late final Dio _dio;

  AutomationService() {
    _dio = Dio(
      BaseOptions(
        baseUrl: ApiConfig.baseUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 30),
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await FirebaseAuth.instance.currentUser?.getIdToken();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  Future<Map<String, dynamic>> command(String text) async {
    final response = await _dio.post(
      '/api/automation/command',
      data: {'command': text},
    );
    return Map<String, dynamic>.from(response.data as Map);
  }

  Future<String> takeScreenshot() async {
    final response = await _dio.post('/api/automation/system/screenshot');
    final data = Map<String, dynamic>.from(response.data as Map);
    return (data['path'] ?? '') as String;
  }

  Future<List<Map<String, dynamic>>> getStepTypes() async {
    final response = await _dio.get('/api/automation/workflows/step-types');
    final data = Map<String, dynamic>.from(response.data as Map);
    final items = (data['step_types'] as List?) ?? const [];
    return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> getTriggerTypes() async {
    final response = await _dio.get('/api/automation/workflows/trigger-types');
    final data = Map<String, dynamic>.from(response.data as Map);
    final items = (data['trigger_types'] as List?) ?? const [];
    return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> getAutomationStatus() async {
    final response = await _dio.get('/api/automation/status');
    final data = Map<String, dynamic>.from(response.data as Map);
    final status = data['status'];
    if (status is Map) {
      return Map<String, dynamic>.from(status);
    }
    return <String, dynamic>{};
  }

  Future<List<Map<String, dynamic>>> listWorkflows() async {
    final response = await _dio.get('/api/automation/workflows');
    final data = Map<String, dynamic>.from(response.data as Map);
    final items = (data['workflows'] as List?) ?? const [];
    return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> createWorkflow(
      Map<String, dynamic> payload) async {
    final response =
        await _dio.post('/api/automation/workflows', data: payload);
    final data = Map<String, dynamic>.from(response.data as Map);
    return Map<String, dynamic>.from(data['workflow'] as Map);
  }

  Future<Map<String, dynamic>> updateWorkflow(
      String workflowId, Map<String, dynamic> payload) async {
    final response =
        await _dio.put('/api/automation/workflows/$workflowId', data: payload);
    final data = Map<String, dynamic>.from(response.data as Map);
    return Map<String, dynamic>.from(data['workflow'] as Map);
  }

  Future<void> deleteWorkflow(String workflowId) async {
    await _dio.delete('/api/automation/workflows/$workflowId');
  }

  Future<Map<String, dynamic>> runWorkflow(
    String workflowId, {
    String triggeredBy = 'manual_ui',
    Map<String, dynamic>? inputPayload,
  }) async {
    final body = <String, dynamic>{'triggered_by': triggeredBy};
    if (inputPayload != null) {
      body['input_payload'] = inputPayload;
    }
    final response = await _dio.post(
      '/api/automation/workflows/$workflowId/run',
      data: body,
    );
    final data = Map<String, dynamic>.from(response.data as Map);
    return Map<String, dynamic>.from(data['run'] as Map);
  }

  Future<Map<String, dynamic>> cloneWorkflow(String workflowId) async {
    final response =
        await _dio.post('/api/automation/workflows/$workflowId/clone');
    final data = Map<String, dynamic>.from(response.data as Map);
    return Map<String, dynamic>.from(data['workflow'] as Map);
  }

  Future<List<Map<String, dynamic>>> listWorkflowRuns(
    String workflowId, {
    int limit = 20,
  }) async {
    final response = await _dio.get(
      '/api/automation/workflows/$workflowId/runs',
      queryParameters: {'limit': limit},
    );
    final data = Map<String, dynamic>.from(response.data as Map);
    final items = (data['runs'] as List?) ?? const [];
    return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> listAllWorkflowRuns(
      {int limit = 20}) async {
    final response = await _dio.get(
      '/api/automation/workflow-runs',
      queryParameters: {'limit': limit},
    );
    final data = Map<String, dynamic>.from(response.data as Map);
    final items = (data['runs'] as List?) ?? const [];
    return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> cancelWorkflowRun(String runId) async {
    final response =
        await _dio.post('/api/automation/workflow-runs/$runId/cancel');
    return Map<String, dynamic>.from(response.data as Map);
  }

  Future<Map<String, dynamic>> clearWorkflowRuns({String? workflowId}) async {
    final response = await _dio.delete(
      '/api/automation/workflow-runs',
      queryParameters: {
        if (workflowId != null && workflowId.trim().isNotEmpty)
          'workflow_id': workflowId
      },
    );
    return Map<String, dynamic>.from(response.data as Map);
  }

  Future<Map<String, dynamic>> triggerWebhookWorkflow(
    String token, {
    Map<String, dynamic>? payload,
  }) async {
    final response = await _dio.post(
      '/api/automation/workflows/webhook/$token',
      data: payload ?? <String, dynamic>{},
    );
    return Map<String, dynamic>.from(response.data as Map);
  }

  Future<List<Map<String, dynamic>>> listContacts() async {
    final response = await _dio.get('/api/automation/contacts');
    final raw = response.data;
    if (raw is List) {
      return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }
    if (raw is Map) {
      final data = Map<String, dynamic>.from(raw);
      final items = (data['contacts'] as List?) ?? (data['value'] as List?) ?? const [];
      return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }
    return const <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> getContactStats() async {
    final response = await _dio.get('/api/automation/contacts/stats');
    final data = Map<String, dynamic>.from(response.data as Map);
    final stats = data['stats'];
    if (stats is Map) {
      return Map<String, dynamic>.from(stats);
    }
    return <String, dynamic>{};
  }

  Future<Map<String, dynamic>> bulkUpsertContacts(
    List<Map<String, dynamic>> contacts,
  ) async {
    final response = await _dio.post(
      '/api/automation/contacts/bulk',
      data: <String, dynamic>{'contacts': contacts},
    );
    return Map<String, dynamic>.from(response.data as Map);
  }

  Future<Map<String, dynamic>> syncMobileData(
    Map<String, dynamic> payload,
  ) async {
    final response = await _dio.post(
      '/api/automation/mobile-data/sync',
      data: payload,
    );
    return Map<String, dynamic>.from(response.data as Map);
  }

  Future<Map<String, dynamic>> getMobileDataStats() async {
    final response = await _dio.get('/api/automation/mobile-data/stats');
    final data = Map<String, dynamic>.from(response.data as Map);
    final stats = data['stats'];
    if (stats is Map) {
      return Map<String, dynamic>.from(stats);
    }
    return <String, dynamic>{};
  }
}
