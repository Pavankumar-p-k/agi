import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:call_log/call_log.dart';
import 'package:device_calendar/device_calendar.dart' as dc;
import 'package:flutter_contacts/flutter_contacts.dart' as fc;
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:permission_handler/permission_handler.dart';

import '../services/automation_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class AutomationScreen extends StatefulWidget {
  const AutomationScreen({super.key});

  @override
  State<AutomationScreen> createState() => _AutomationScreenState();
}

class _AutomationScreenState extends State<AutomationScreen> {
  final AutomationService _automation = AutomationService();
  final TextEditingController _commandController = TextEditingController();
  final List<_AutomationLog> _logs = [];

  bool _runningCommand = false;
  bool _loadingWorkflows = true;
  List<Map<String, dynamic>> _workflows = [];
  List<Map<String, dynamic>> _stepTypes = [];
  List<Map<String, dynamic>> _triggerTypes = [];
  Map<String, dynamic> _status = <String, dynamic>{};
  Map<String, dynamic> _contactStats = <String, dynamic>{};
  Map<String, dynamic> _mobileDataStats = <String, dynamic>{};
  bool _contactsPermissionGranted = false;
  bool _phonePermissionGranted = false;
  bool _calendarPermissionGranted = false;
  bool _syncingContacts = false;
  bool _syncingMobileData = false;
  int _lastSyncedContacts = 0;

  @override
  void initState() {
    super.initState();
    _loadWorkflowData();
    _loadMobileContactContext();
  }

  @override
  void dispose() {
    _commandController.dispose();
    super.dispose();
  }

  Future<void> _loadWorkflowData() async {
    setState(() => _loadingWorkflows = true);
    try {
      final results = await Future.wait<List<Map<String, dynamic>>>([
        _automation.getStepTypes(),
        _automation.getTriggerTypes(),
        _automation.listWorkflows(),
      ]);
      final status = await _automation.getAutomationStatus();
      if (!mounted) return;
      setState(() {
        _stepTypes = results[0];
        _triggerTypes = results[1];
        _workflows = results[2];
        _status = status;
        _loadingWorkflows = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadingWorkflows = false);
      _showMessage('Failed to load workflows: $e', ok: false);
    }
  }

  Future<void> _refreshWorkflows() async {
    try {
      final results = await Future.wait<dynamic>([
        _automation.listWorkflows(),
        _automation.getAutomationStatus(),
      ]);
      if (!mounted) return;
      setState(() {
        _workflows = results[0] as List<Map<String, dynamic>>;
        _status = results[1] as Map<String, dynamic>;
      });
    } catch (e) {
      _showMessage('Failed to refresh workflows: $e', ok: false);
    }
  }

  void _showMessage(String msg, {bool ok = true}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: ok ? JarvisColors.green : JarvisColors.red,
      ),
    );
  }

  bool get _isMobilePlatform {
    if (kIsWeb) return false;
    return defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS;
  }

  Future<void> _loadMobileContactContext() async {
    if (!_isMobilePlatform) return;
    await Future.wait<dynamic>([
      _refreshContactsPermissionStatus(),
      _refreshContactStats(),
      _refreshMobileDataStats(),
    ]);
  }

  Future<void> _refreshContactsPermissionStatus() async {
    if (!_isMobilePlatform) return;
    final contactsStatus = await Permission.contacts.status;
    final phoneStatus = await Permission.phone.status;
    final calendarStatus = await Permission.calendar.status;
    if (!mounted) return;
    setState(() {
      _contactsPermissionGranted =
          contactsStatus.isGranted || contactsStatus.isLimited;
      _phonePermissionGranted = phoneStatus.isGranted || phoneStatus.isLimited;
      _calendarPermissionGranted =
          calendarStatus.isGranted || calendarStatus.isLimited;
    });
  }

  Future<void> _requestContactsPermission() async {
    if (!_isMobilePlatform) return;
    final status = await Permission.contacts.request();
    if (status.isPermanentlyDenied) {
      await openAppSettings();
    }
    await _refreshContactsPermissionStatus();
    _showMessage(
      _contactsPermissionGranted
          ? 'Contacts permission granted'
          : 'Contacts permission is required for device sync',
      ok: _contactsPermissionGranted,
    );
  }

  Future<void> _requestMobileDataPermissions() async {
    if (!_isMobilePlatform) return;
    await <Permission>[
      Permission.contacts,
      Permission.phone,
      Permission.calendar,
    ].request();
    await _refreshContactsPermissionStatus();
    final ok = _contactsPermissionGranted &&
        _phonePermissionGranted &&
        _calendarPermissionGranted;
    _showMessage(
      ok
          ? 'Mobile data permissions granted'
          : 'Some permissions are still missing',
      ok: ok,
    );
  }

  Future<void> _refreshContactStats() async {
    try {
      final stats = await _automation.getContactStats();
      if (!mounted) return;
      setState(() => _contactStats = stats);
    } catch (_) {
      // Keep UI functional even if backend endpoint is temporarily unavailable.
    }
  }

  Future<void> _refreshMobileDataStats() async {
    try {
      final stats = await _automation.getMobileDataStats();
      if (!mounted) return;
      setState(() => _mobileDataStats = stats);
    } catch (_) {
      // Ignore temporary backend unavailability.
    }
  }

  Future<void> _syncDeviceContacts() async {
    if (!_isMobilePlatform || _syncingContacts) return;
    await _refreshContactsPermissionStatus();
    if (!_contactsPermissionGranted) {
      await _requestContactsPermission();
      if (!_contactsPermissionGranted) return;
    }

    setState(() => _syncingContacts = true);
    try {
      final contacts = await fc.FlutterContacts.getContacts(withProperties: true);
      final payload = <Map<String, dynamic>>[];

      for (final contact in contacts) {
        final name = contact.displayName.trim();
        if (name.isEmpty) continue;
        final phone =
            contact.phones.isNotEmpty ? contact.phones.first.number.trim() : '';
        final email = contact.emails.isNotEmpty
            ? contact.emails.first.address.trim()
            : '';
        payload.add(<String, dynamic>{
          'name': name,
          'phone': phone,
          'whatsapp': phone,
          'email': email,
        });
      }

      if (payload.isEmpty) {
        _showMessage('No contacts found to sync', ok: false);
        return;
      }

      final result = await _automation.bulkUpsertContacts(payload);
      final summary = Map<String, dynamic>.from(
        (result['summary'] as Map?) ?? const <String, dynamic>{},
      );
      if (mounted) {
        setState(() => _lastSyncedContacts = payload.length);
      }
      await _refreshContactStats();
      _showMessage(
        'Synced ${summary['received'] ?? payload.length} contacts'
        ' (created ${summary['created'] ?? 0}, updated ${summary['updated'] ?? 0})',
      );
    } catch (e) {
      _showMessage('Device contact sync failed: $e', ok: false);
    } finally {
      if (mounted) {
        setState(() => _syncingContacts = false);
      }
    }
  }

  Future<List<Map<String, dynamic>>> _readCallLogs() async {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return const <Map<String, dynamic>>[];
    }
    final entries = await CallLog.get();
    final out = <Map<String, dynamic>>[];
    for (final e in entries) {
      if (out.length >= 1000) break;
      out.add(<String, dynamic>{
        'number': e.number ?? '',
        'name': e.name ?? '',
        'type': e.callType?.toString() ?? '',
        'duration_seconds': e.duration ?? 0,
        'timestamp': e.timestamp ?? 0,
      });
    }
    return out;
  }

  Future<List<Map<String, dynamic>>> _readCalendarEvents() async {
    final plugin = dc.DeviceCalendarPlugin();
    final hasPerm = await plugin.hasPermissions();
    if ((hasPerm.data ?? false) != true) {
      final req = await plugin.requestPermissions();
      if ((req.data ?? false) != true) {
        return const <Map<String, dynamic>>[];
      }
    }

    final calendarsResult = await plugin.retrieveCalendars();
    final calendars = calendarsResult.data ?? const <dc.Calendar>[];
    final now = DateTime.now();
    final start = now.subtract(const Duration(days: 30));
    final end = now.add(const Duration(days: 90));
    final events = <Map<String, dynamic>>[];

    for (final calendar in calendars) {
      if (events.length >= 1500) break;
      final id = calendar.id;
      if (id == null || id.isEmpty) continue;
      final result = await plugin.retrieveEvents(
        id,
        dc.RetrieveEventsParams(
          startDate: start,
          endDate: end,
        ),
      );
      final items = result.data ?? const <dc.Event>[];
      for (final ev in items) {
        if (events.length >= 1500) break;
        events.add(<String, dynamic>{
          'calendar_id': id,
          'calendar_name': calendar.name ?? '',
          'title': ev.title ?? '',
          'description': ev.description ?? '',
          'location': ev.location ?? '',
          'start': ev.start?.toIso8601String() ?? '',
          'end': ev.end?.toIso8601String() ?? '',
          'all_day': ev.allDay ?? false,
        });
      }
    }
    return events;
  }

  Future<void> _syncMobileDataNow() async {
    if (!_isMobilePlatform || _syncingMobileData) return;
    await _refreshContactsPermissionStatus();
    if (!_contactsPermissionGranted ||
        !_phonePermissionGranted ||
        !_calendarPermissionGranted) {
      await _requestMobileDataPermissions();
      if (!_contactsPermissionGranted ||
          !_phonePermissionGranted ||
          !_calendarPermissionGranted) {
        return;
      }
    }

    setState(() => _syncingMobileData = true);
    try {
      final contacts = await fc.FlutterContacts.getContacts(withProperties: true);
      final contactPayload = <Map<String, dynamic>>[];
      for (final c in contacts) {
        final name = c.displayName.trim();
        if (name.isEmpty) continue;
        final phone = c.phones.isNotEmpty ? c.phones.first.number.trim() : '';
        final email = c.emails.isNotEmpty ? c.emails.first.address.trim() : '';
        contactPayload.add(<String, dynamic>{
          'name': name,
          'phone': phone,
          'whatsapp': phone,
          'email': email,
        });
      }

      // Keep contacts DB in sync for messaging workflows.
      if (contactPayload.isNotEmpty) {
        await _automation.bulkUpsertContacts(contactPayload);
      }

      final callLogs = await _readCallLogs();
      final events = await _readCalendarEvents();
      final dataRes = await _automation.syncMobileData(<String, dynamic>{
        'device_id': 'mobile-app',
        'contacts': contactPayload,
        'call_logs': callLogs,
        'calendar_events': events,
      });
      final summary = Map<String, dynamic>.from(
        (dataRes['summary'] as Map?) ?? const <String, dynamic>{},
      );
      await _refreshContactStats();
      await _refreshMobileDataStats();
      _showMessage(
        'Mobile sync complete: contacts ${summary['contacts'] ?? contactPayload.length}, '
        'calls ${summary['call_logs'] ?? callLogs.length}, '
        'events ${summary['calendar_events'] ?? events.length}',
      );
    } catch (e) {
      _showMessage('Mobile data sync failed: $e', ok: false);
    } finally {
      if (mounted) setState(() => _syncingMobileData = false);
    }
  }

  Future<void> _runCommand() async {
    final text = _commandController.text.trim();
    if (text.isEmpty || _runningCommand) return;

    setState(() {
      _runningCommand = true;
      _logs.insert(0,
          _AutomationLog(request: text, response: 'Running...', success: true));
      _commandController.clear();
    });

    try {
      final result = await _automation.command(text);
      final success = result['success'] == true;
      final speech =
          (result['speech'] ?? result['action'] ?? 'Done').toString();
      if (!mounted) return;
      setState(() {
        _logs[0] =
            _AutomationLog(request: text, response: speech, success: success);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _logs[0] = _AutomationLog(
            request: text, response: 'Error: $e', success: false);
      });
    } finally {
      if (mounted) setState(() => _runningCommand = false);
    }
  }

  Future<void> _takeScreenshot() async {
    if (_runningCommand) return;
    setState(() => _runningCommand = true);
    try {
      final path = await _automation.takeScreenshot();
      if (!mounted) return;
      setState(() {
        _logs.insert(
          0,
          _AutomationLog(
            request: 'Take screenshot',
            response: path.isEmpty ? 'Screenshot failed' : 'Saved: $path',
            success: path.isNotEmpty,
          ),
        );
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _logs.insert(
          0,
          _AutomationLog(
              request: 'Take screenshot',
              response: 'Error: $e',
              success: false),
        );
      });
    } finally {
      if (mounted) setState(() => _runningCommand = false);
    }
  }

  Future<void> _createWorkflow() async {
    final payload = await _showWorkflowDialog();
    if (payload == null) return;
    try {
      await _automation.createWorkflow(payload);
      await _refreshWorkflows();
      _showMessage('Workflow created');
    } catch (e) {
      _showMessage('Create failed: $e', ok: false);
    }
  }

  Future<void> _editWorkflow(Map<String, dynamic> workflow) async {
    final payload = await _showWorkflowDialog(workflow: workflow);
    if (payload == null) return;
    try {
      await _automation.updateWorkflow(workflow['id'].toString(), payload);
      await _refreshWorkflows();
      _showMessage('Workflow updated');
    } catch (e) {
      _showMessage('Update failed: $e', ok: false);
    }
  }

  Future<void> _toggleWorkflow(
      Map<String, dynamic> workflow, bool enabled) async {
    try {
      await _automation
          .updateWorkflow(workflow['id'].toString(), {'enabled': enabled});
      await _refreshWorkflows();
    } catch (e) {
      _showMessage('Toggle failed: $e', ok: false);
    }
  }

  Future<void> _runWorkflow(Map<String, dynamic> workflow) async {
    try {
      final run = await _automation.runWorkflow(workflow['id'].toString());
      _showMessage('Run started: ${run['id']}');
      await Future.delayed(const Duration(milliseconds: 700));
      await _refreshWorkflows();
    } catch (e) {
      _showMessage('Run failed: $e', ok: false);
    }
  }

  Future<void> _cloneWorkflow(Map<String, dynamic> workflow) async {
    try {
      final cloned = await _automation.cloneWorkflow(workflow['id'].toString());
      _showMessage('Cloned: ${cloned['name'] ?? 'workflow'}');
      await _refreshWorkflows();
    } catch (e) {
      _showMessage('Clone failed: $e', ok: false);
    }
  }

  Future<void> _clearAllRuns() async {
    try {
      final response = await _automation.clearWorkflowRuns();
      _showMessage('Removed ${response['removed'] ?? 0} run records');
      await _refreshWorkflows();
    } catch (e) {
      _showMessage('Clear runs failed: $e', ok: false);
    }
  }

  Future<void> _deleteWorkflow(Map<String, dynamic> workflow) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: JarvisColors.bgCard,
        title: const Text('Delete workflow?'),
        content: Text(workflow['name'].toString()),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _automation.deleteWorkflow(workflow['id'].toString());
      await _refreshWorkflows();
      _showMessage('Workflow deleted');
    } catch (e) {
      _showMessage('Delete failed: $e', ok: false);
    }
  }

  void _showRuns(Map<String, dynamic> workflow) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: JarvisColors.bgCard,
      isScrollControlled: true,
      builder: (_) => _WorkflowRunsSheet(
        automation: _automation,
        workflowId: workflow['id'].toString(),
        workflowName: workflow['name'].toString(),
      ),
    );
  }

  String _fmtTime(dynamic value) {
    final raw = value?.toString() ?? '';
    if (raw.isEmpty) return '-';
    try {
      return DateFormat('MMM dd, HH:mm:ss')
          .format(DateTime.parse(raw).toLocal());
    } catch (_) {
      return raw;
    }
  }

  String _triggerText(Map<String, dynamic> workflow) {
    final trigger =
        Map<String, dynamic>.from((workflow['trigger'] as Map?) ?? const {});
    final type = (trigger['type'] ?? 'manual').toString();
    if (type == 'interval') {
      return 'Interval: ${trigger['interval_seconds'] ?? 300}s';
    }
    if (type == 'daily') {
      final time = trigger['daily_time'] ?? '09:00';
      final days = (trigger['weekdays'] as List?) ?? const [];
      return 'Daily: $time UTC (${days.join(',')})';
    }
    if (type == 'once') {
      return 'Once: ${trigger['once_at'] ?? '-'}';
    }
    if (type == 'webhook') {
      final token = (trigger['webhook_token'] ?? '').toString();
      if (token.isEmpty) return 'Webhook';
      final short = token.length > 8 ? token.substring(0, 8) : token;
      return 'Webhook: $short...';
    }
    return 'Manual';
  }

  Future<Map<String, dynamic>?> _showWorkflowDialog(
      {Map<String, dynamic>? workflow}) async {
    final nameCtrl =
        TextEditingController(text: workflow?['name']?.toString() ?? '');
    final descCtrl =
        TextEditingController(text: workflow?['description']?.toString() ?? '');
    final trigger =
        Map<String, dynamic>.from((workflow?['trigger'] as Map?) ?? const {});
    String triggerType = (trigger['type'] ?? 'manual').toString();
    final intervalCtrl = TextEditingController(
        text: (trigger['interval_seconds'] ?? 300).toString());
    final dailyTimeCtrl = TextEditingController(
        text: (trigger['daily_time'] ?? '09:00').toString());
    final weekdaysCtrl = TextEditingController(
        text: ((trigger['weekdays'] as List?) ?? const [0, 1, 2, 3, 4, 5, 6])
            .join(','));
    final onceAtCtrl =
        TextEditingController(text: (trigger['once_at'] ?? '').toString());
    final webhookTokenCtrl = TextEditingController(
        text: (trigger['webhook_token'] ?? '').toString());
    bool enabled = workflow?['enabled'] != false;
    final variablesCtrl = TextEditingController(
      text: const JsonEncoder.withIndent('  ')
          .convert((workflow?['variables'] as Map?) ?? const {}),
    );
    final stepsCtrl = TextEditingController(
      text: const JsonEncoder.withIndent('  ')
          .convert((workflow?['steps'] as List?) ?? [_defaultStep()]),
    );
    final triggerItems = (_triggerTypes.isNotEmpty
            ? _triggerTypes
            : <Map<String, dynamic>>[
                {'type': 'manual'},
                {'type': 'interval'},
                {'type': 'daily'},
                {'type': 'once'},
                {'type': 'webhook'},
              ])
        .map((e) => e['type'].toString())
        .toSet()
        .toList();

    final payload = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialog) => AlertDialog(
          backgroundColor: JarvisColors.bgCard,
          insetPadding: const EdgeInsets.all(16),
          title: Text(
            workflow == null ? 'NEW WORKFLOW' : 'EDIT WORKFLOW',
            style: GoogleFonts.orbitron(
              fontSize: 13,
              letterSpacing: 1.5,
              color: JarvisColors.cyan,
            ),
          ),
          content: SizedBox(
            width: 700,
            child: SingleChildScrollView(
              child: Column(
                children: [
                  TextField(
                    controller: nameCtrl,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration:
                        const InputDecoration(hintText: 'Workflow name'),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: descCtrl,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(hintText: 'Description'),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: triggerType,
                          dropdownColor: JarvisColors.bgCard,
                          items: triggerItems
                              .map((t) =>
                                  DropdownMenuItem(value: t, child: Text(t)))
                              .toList(),
                          onChanged: (v) {
                            if (v == null) return;
                            setDialog(() => triggerType = v);
                          },
                        ),
                      ),
                      const SizedBox(width: 10),
                      if (triggerType == 'interval')
                        Expanded(
                          child: TextField(
                            controller: intervalCtrl,
                            keyboardType: TextInputType.number,
                            style: GoogleFonts.shareTech(
                                color: JarvisColors.textPrimary),
                            decoration: const InputDecoration(
                                hintText: 'Interval seconds'),
                          ),
                        )
                      else
                        Expanded(
                          child: Row(
                            children: [
                              Switch(
                                value: enabled,
                                onChanged: (v) => setDialog(() => enabled = v),
                              ),
                              Text(
                                'Enabled',
                                style: GoogleFonts.shareTech(
                                    color: JarvisColors.textSecondary),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                  if (triggerType == 'daily')
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: dailyTimeCtrl,
                              style: GoogleFonts.shareTech(
                                  color: JarvisColors.textPrimary),
                              decoration: const InputDecoration(
                                  hintText: 'Daily time HH:MM (UTC)'),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: TextField(
                              controller: weekdaysCtrl,
                              style: GoogleFonts.shareTech(
                                  color: JarvisColors.textPrimary),
                              decoration: const InputDecoration(
                                  hintText: 'Weekdays: 0,1,2,3,4,5,6'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (triggerType == 'once')
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: TextField(
                        controller: onceAtCtrl,
                        style: GoogleFonts.shareTech(
                            color: JarvisColors.textPrimary),
                        decoration: const InputDecoration(
                            hintText: 'Once at ISO datetime (UTC)'),
                      ),
                    ),
                  if (triggerType == 'webhook')
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: TextField(
                        controller: webhookTokenCtrl,
                        style: GoogleFonts.shareTech(
                            color: JarvisColors.textPrimary),
                        decoration: const InputDecoration(
                            hintText:
                                'Webhook token (leave empty to auto-generate)'),
                      ),
                    ),
                  if (triggerType == 'interval')
                    Row(
                      children: [
                        Switch(
                          value: enabled,
                          onChanged: (v) => setDialog(() => enabled = v),
                        ),
                        Text(
                          'Enabled',
                          style: GoogleFonts.shareTech(
                              color: JarvisColors.textSecondary),
                        ),
                      ],
                    ),
                  if (triggerType == 'daily' ||
                      triggerType == 'once' ||
                      triggerType == 'webhook')
                    Row(
                      children: [
                        Switch(
                          value: enabled,
                          onChanged: (v) => setDialog(() => enabled = v),
                        ),
                        Text(
                          'Enabled',
                          style: GoogleFonts.shareTech(
                              color: JarvisColors.textSecondary),
                        ),
                      ],
                    ),
                  const SizedBox(height: 10),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Variables JSON (object)',
                      style: GoogleFonts.orbitron(
                        fontSize: 10,
                        letterSpacing: 1.2,
                        color: JarvisColors.cyan,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: variablesCtrl,
                    maxLines: 4,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(
                        hintText: '{"name":"Pavan","city":"Bangalore"}'),
                  ),
                  const SizedBox(height: 10),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Steps JSON (list)',
                      style: GoogleFonts.orbitron(
                        fontSize: 10,
                        letterSpacing: 1.2,
                        color: JarvisColors.cyan,
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: stepsCtrl,
                    maxLines: 12,
                    style:
                        GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                    decoration: const InputDecoration(
                        hintText:
                            '[{"type":"command","params":{"text":"help automation"}}]'),
                  ),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Step types: ${_stepTypes.map((e) => e['type']).join(', ')}',
                      style: GoogleFonts.shareTech(
                          fontSize: 11, color: JarvisColors.textSecondary),
                    ),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel')),
            TextButton(
              onPressed: () {
                if (nameCtrl.text.trim().isEmpty) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('Name is required')),
                  );
                  return;
                }
                dynamic parsed;
                try {
                  parsed = jsonDecode(stepsCtrl.text.trim());
                } catch (_) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('Steps JSON is invalid')),
                  );
                  return;
                }
                if (parsed is! List) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('Steps must be a JSON list')),
                  );
                  return;
                }
                dynamic varsParsed;
                try {
                  varsParsed = jsonDecode(variablesCtrl.text.trim().isEmpty
                      ? '{}'
                      : variablesCtrl.text.trim());
                } catch (_) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('Variables JSON is invalid')),
                  );
                  return;
                }
                if (varsParsed is! Map) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(
                        content: Text('Variables must be a JSON object')),
                  );
                  return;
                }
                final triggerPayload = <String, dynamic>{'type': triggerType};
                if (triggerType == 'interval') {
                  triggerPayload['interval_seconds'] =
                      (int.tryParse(intervalCtrl.text.trim()) ?? 300)
                          .clamp(10, 86400);
                } else if (triggerType == 'daily') {
                  triggerPayload['daily_time'] = dailyTimeCtrl.text.trim();
                  final dayValues = weekdaysCtrl.text
                      .split(',')
                      .map((e) => int.tryParse(e.trim()))
                      .whereType<int>()
                      .toList();
                  triggerPayload['weekdays'] = dayValues;
                } else if (triggerType == 'once') {
                  triggerPayload['once_at'] = onceAtCtrl.text.trim();
                } else if (triggerType == 'webhook') {
                  if (webhookTokenCtrl.text.trim().isNotEmpty) {
                    triggerPayload['webhook_token'] =
                        webhookTokenCtrl.text.trim();
                  }
                }
                Navigator.pop(ctx, {
                  'name': nameCtrl.text.trim(),
                  'description': descCtrl.text.trim(),
                  'enabled': enabled,
                  'trigger': triggerPayload,
                  'variables': Map<String, dynamic>.from(varsParsed),
                  'steps': parsed,
                });
              },
              child: Text(workflow == null ? 'Create' : 'Save'),
            ),
          ],
        ),
      ),
    );

    nameCtrl.dispose();
    descCtrl.dispose();
    intervalCtrl.dispose();
    dailyTimeCtrl.dispose();
    weekdaysCtrl.dispose();
    onceAtCtrl.dispose();
    webhookTokenCtrl.dispose();
    variablesCtrl.dispose();
    stepsCtrl.dispose();
    return payload;
  }

  Map<String, dynamic> _defaultStep() {
    return {
      'name': 'Sample command',
      'type': 'command',
      'params': {'text': 'help automation'},
      'continue_on_error': false,
      'delay_seconds': 0,
    };
  }

  Widget _buildCommandTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          JPanel(
            label: 'COMMAND',
            child: Column(
              children: [
                TextField(
                  controller: _commandController,
                  onSubmitted: (_) => _runCommand(),
                  style: GoogleFonts.shareTech(color: JarvisColors.textPrimary),
                  decoration: const InputDecoration(
                    hintText:
                        'Example: open whatsapp / send instagram to rahul saying hi',
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: JButton(
                        label: _runningCommand ? 'RUNNING...' : 'RUN COMMAND',
                        icon: Icons.play_arrow,
                        onTap: _runningCommand ? null : _runCommand,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: JButton(
                        label: 'SCREENSHOT',
                        icon: Icons.screenshot_monitor_outlined,
                        onTap: _runningCommand ? null : _takeScreenshot,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: JPanel(
              label: 'HISTORY',
              child: _logs.isEmpty
                  ? Center(
                      child: Text(
                        'No automation commands yet',
                        style: GoogleFonts.shareTech(
                          color: JarvisColors.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                    )
                  : ListView.separated(
                      itemCount: _logs.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 8),
                      itemBuilder: (_, i) {
                        final log = _logs[i];
                        final color =
                            log.success ? JarvisColors.green : JarvisColors.red;
                        return Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: JarvisColors.bgPanel,
                            border: Border.all(
                                color: color.withValues(alpha: 0.35)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                log.request,
                                style: GoogleFonts.orbitron(
                                  fontSize: 10,
                                  letterSpacing: 1,
                                  color: JarvisColors.textPrimary,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                log.response,
                                style: GoogleFonts.shareTech(
                                    fontSize: 12, color: color),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWorkflowsTab() {
    if (_loadingWorkflows) {
      return const Center(
        child: CircularProgressIndicator(
            color: JarvisColors.cyan, strokeWidth: 1.5),
      );
    }
    return RefreshIndicator(
      color: JarvisColors.cyan,
      onRefresh: () async {
        await _refreshWorkflows();
        await _refreshContactsPermissionStatus();
        await _refreshContactStats();
        await _refreshMobileDataStats();
      },
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          JPanel(
            label: 'WORKFLOW BUILDER',
            child: Column(
              children: [
                Text(
                  'Create persistent automation flows with triggers and steps.',
                  style: GoogleFonts.shareTech(
                      fontSize: 12, color: JarvisColors.textSecondary),
                ),
                const SizedBox(height: 8),
                Text(
                  'Engine: ${(_status['engine_running'] == true) ? 'RUNNING' : 'STOPPED'}'
                  ' • Active Runs: ${_status['active_run_count'] ?? 0}'
                  ' • Enabled: ${_status['enabled_workflow_count'] ?? 0}',
                  style: GoogleFonts.shareTech(
                      fontSize: 12, color: JarvisColors.textPrimary),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: JButton(
                        label: 'NEW WORKFLOW',
                        icon: Icons.add_circle_outline,
                        onTap: _createWorkflow,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: JButton(
                        label: 'REFRESH',
                        icon: Icons.refresh_outlined,
                        outlined: true,
                        onTap: _refreshWorkflows,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: JButton(
                    label: 'CLEAR RUN HISTORY',
                    icon: Icons.delete_sweep_outlined,
                    color: JarvisColors.orange,
                    onTap: _clearAllRuns,
                  ),
                ),
              ],
            ),
          ),
          if (_isMobilePlatform) ...[
            const SizedBox(height: 14),
            JPanel(
              label: 'MOBILE DATA SYNC',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Use mobile permissions to sync contacts, call logs, and calendar events for automation.',
                    style: GoogleFonts.shareTech(
                      fontSize: 12,
                      color: JarvisColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 8),
                  _mobileStatRow(
                    'Contacts Permission',
                    _contactsPermissionGranted ? 'GRANTED' : 'NOT GRANTED',
                    _contactsPermissionGranted,
                  ),
                  _mobileStatRow(
                    'Phone Permission',
                    _phonePermissionGranted ? 'GRANTED' : 'NOT GRANTED',
                    _phonePermissionGranted,
                  ),
                  _mobileStatRow(
                    'Calendar Permission',
                    _calendarPermissionGranted ? 'GRANTED' : 'NOT GRANTED',
                    _calendarPermissionGranted,
                  ),
                  _mobileStatRow(
                    'Backend Contacts',
                    '${_contactStats['total'] ?? 0}',
                    true,
                  ),
                  _mobileStatRow(
                    'With WhatsApp',
                    '${_contactStats['with_whatsapp'] ?? 0}',
                    true,
                  ),
                  _mobileStatRow(
                    'With Instagram',
                    '${_contactStats['with_instagram'] ?? 0}',
                    true,
                  ),
                  if (_lastSyncedContacts > 0)
                    _mobileStatRow(
                      'Last Synced',
                      '$_lastSyncedContacts contacts',
                      true,
                    ),
                  _mobileStatRow(
                    'Synced Call Logs',
                    '${_mobileDataStats['call_logs'] ?? 0}',
                    true,
                  ),
                  _mobileStatRow(
                    'Synced Calendar Events',
                    '${_mobileDataStats['calendar_events'] ?? 0}',
                    true,
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: JButton(
                          label: 'GRANT ALL PERMISSIONS',
                          icon: Icons.perm_contact_calendar_outlined,
                          outlined: true,
                          onTap: _requestMobileDataPermissions,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: JButton(
                          label: _syncingMobileData
                              ? 'SYNCING...'
                              : 'SYNC MOBILE DATA',
                          icon: Icons.sync_outlined,
                          onTap: _syncingMobileData ? null : _syncMobileDataNow,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: JButton(
                      label: _syncingContacts
                          ? 'SYNCING CONTACTS...'
                          : 'SYNC CONTACTS ONLY',
                      icon: Icons.contacts_outlined,
                      outlined: true,
                      onTap: _syncingContacts ? null : _syncDeviceContacts,
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),
          if (_workflows.isEmpty)
            JPanel(
              label: 'EMPTY',
              child: Text(
                'No workflows yet. Create one.',
                style: GoogleFonts.shareTech(
                    color: JarvisColors.textSecondary, fontSize: 13),
              ),
            ),
          ..._workflows.map((wf) {
            final enabled = wf['enabled'] == true;
            final steps = (wf['steps'] as List?)?.length ?? 0;
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: JPanel(
                label: wf['name']?.toString() ?? 'WORKFLOW',
                borderColor:
                    enabled ? JarvisColors.cyan.withValues(alpha: 0.45) : null,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if ((wf['description'] ?? '').toString().trim().isNotEmpty)
                      Text(
                        wf['description'].toString(),
                        style: GoogleFonts.shareTech(
                            color: JarvisColors.textPrimary, fontSize: 12),
                      ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Text(
                          enabled ? 'ENABLED' : 'DISABLED',
                          style: GoogleFonts.orbitron(
                            fontSize: 9,
                            color: enabled
                                ? JarvisColors.green
                                : JarvisColors.textSecondary,
                          ),
                        ),
                        const Spacer(),
                        Switch(
                          value: enabled,
                          onChanged: (v) => _toggleWorkflow(wf, v),
                        ),
                      ],
                    ),
                    Text(
                      'Trigger: ${_triggerText(wf)}',
                      style: GoogleFonts.shareTech(
                          fontSize: 12, color: JarvisColors.textSecondary),
                    ),
                    Text(
                      'Steps: $steps',
                      style: GoogleFonts.shareTech(
                          fontSize: 12, color: JarvisColors.textSecondary),
                    ),
                    Text(
                      'Last run: ${_fmtTime(wf['last_run_at'])}',
                      style: GoogleFonts.shareTech(
                          fontSize: 12, color: JarvisColors.textSecondary),
                    ),
                    Text(
                      'Next run: ${_fmtTime(wf['next_run_at'])}',
                      style: GoogleFonts.shareTech(
                          fontSize: 12, color: JarvisColors.textSecondary),
                    ),
                    Text(
                      'Success: ${wf['success_runs'] ?? 0} • Failed: ${wf['failed_runs'] ?? 0}',
                      style: GoogleFonts.shareTech(
                          fontSize: 12, color: JarvisColors.textSecondary),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        SizedBox(
                          width: 110,
                          child: JButton(
                              label: 'RUN',
                              icon: Icons.play_arrow,
                              onTap: () => _runWorkflow(wf)),
                        ),
                        SizedBox(
                          width: 110,
                          child: JButton(
                              label: 'EDIT',
                              icon: Icons.edit_outlined,
                              outlined: true,
                              onTap: () => _editWorkflow(wf)),
                        ),
                        SizedBox(
                          width: 110,
                          child: JButton(
                              label: 'CLONE',
                              icon: Icons.copy_outlined,
                              outlined: true,
                              onTap: () => _cloneWorkflow(wf)),
                        ),
                        SizedBox(
                          width: 110,
                          child: JButton(
                              label: 'RUNS',
                              icon: Icons.history,
                              outlined: true,
                              onTap: () => _showRuns(wf)),
                        ),
                        SizedBox(
                          width: 110,
                          child: JButton(
                            label: 'DELETE',
                            icon: Icons.delete_outline,
                            color: JarvisColors.red,
                            onTap: () => _deleteWorkflow(wf),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _mobileStatRow(String label, String value, bool ok) {
    final color = ok ? JarvisColors.green : JarvisColors.red;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Icon(
            ok ? Icons.check_circle_outline : Icons.cancel_outlined,
            size: 14,
            color: color,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '$label: $value',
              style: GoogleFonts.shareTech(
                fontSize: 12,
                color: JarvisColors.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('AUTOMATION'),
          bottom: TabBar(
            indicatorColor: JarvisColors.cyan,
            labelColor: JarvisColors.cyan,
            unselectedLabelColor: JarvisColors.textSecondary,
            labelStyle: GoogleFonts.orbitron(fontSize: 10, letterSpacing: 1.2),
            tabs: const [
              Tab(text: 'COMMAND'),
              Tab(text: 'WORKFLOWS'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _buildCommandTab(),
            _buildWorkflowsTab(),
          ],
        ),
      ),
    );
  }
}

class _WorkflowRunsSheet extends StatefulWidget {
  final AutomationService automation;
  final String workflowId;
  final String workflowName;

  const _WorkflowRunsSheet({
    required this.automation,
    required this.workflowId,
    required this.workflowName,
  });

  @override
  State<_WorkflowRunsSheet> createState() => _WorkflowRunsSheetState();
}

class _WorkflowRunsSheetState extends State<_WorkflowRunsSheet> {
  bool _loading = true;
  String _error = '';
  List<Map<String, dynamic>> _runs = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final runs = await widget.automation
          .listWorkflowRuns(widget.workflowId, limit: 30);
      if (!mounted) return;
      setState(() {
        _runs = runs;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _cancelRun(String runId) async {
    try {
      final response = await widget.automation.cancelWorkflowRun(runId);
      if (!mounted) return;
      final ok = response['success'] == true;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok ? 'Run cancel requested' : 'Cancel failed'),
          backgroundColor: ok ? JarvisColors.green : JarvisColors.red,
        ),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Cancel error: $e'),
          backgroundColor: JarvisColors.red,
        ),
      );
    }
  }

  String _fmt(dynamic value) {
    final raw = value?.toString() ?? '';
    if (raw.isEmpty) return '-';
    try {
      return DateFormat('MMM dd, HH:mm:ss')
          .format(DateTime.parse(raw).toLocal());
    } catch (_) {
      return raw;
    }
  }

  Color _statusColor(String s) {
    if (s == 'success') return JarvisColors.green;
    if (s == 'running') return JarvisColors.cyan;
    if (s == 'failed' || s == 'cancelled') return JarvisColors.red;
    return JarvisColors.textSecondary;
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'RUNS • ${widget.workflowName.toUpperCase()}',
                    style: GoogleFonts.orbitron(
                      fontSize: 11,
                      letterSpacing: 1.5,
                      color: JarvisColors.cyan,
                    ),
                  ),
                ),
                IconButton(
                    onPressed: _load, icon: const Icon(Icons.refresh_outlined)),
              ],
            ),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(16),
                child: CircularProgressIndicator(
                    color: JarvisColors.cyan, strokeWidth: 1.5),
              )
            else if (_error.isNotEmpty)
              Padding(
                padding: const EdgeInsets.all(10),
                child: Text(_error,
                    style: GoogleFonts.shareTech(color: JarvisColors.red)),
              )
            else if (_runs.isEmpty)
              Padding(
                padding: const EdgeInsets.all(10),
                child: Text('No runs yet',
                    style: GoogleFonts.shareTech(
                        color: JarvisColors.textSecondary)),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: _runs.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (_, i) {
                    final run = _runs[i];
                    final status = (run['status'] ?? 'unknown').toString();
                    final color = _statusColor(status);
                    final stepCount = (run['steps'] as List?)?.length ?? 0;
                    final runId = (run['id'] ?? '').toString();
                    return Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: JarvisColors.bgPanel,
                        border: Border.all(color: color.withValues(alpha: 0.4)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Text(
                                status.toUpperCase(),
                                style: GoogleFonts.orbitron(
                                    fontSize: 9, color: color),
                              ),
                              const Spacer(),
                              Text(
                                _fmt(run['started_at']),
                                style: GoogleFonts.shareTech(
                                  fontSize: 11,
                                  color: JarvisColors.textSecondary,
                                ),
                              ),
                              if (status == 'running') ...[
                                const SizedBox(width: 8),
                                SizedBox(
                                  height: 24,
                                  child: TextButton(
                                    onPressed: runId.isEmpty
                                        ? null
                                        : () => _cancelRun(runId),
                                    style: TextButton.styleFrom(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 8, vertical: 0),
                                      foregroundColor: JarvisColors.red,
                                    ),
                                    child: const Text('CANCEL'),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Steps: $stepCount • Success: ${run['success_count'] ?? 0} • Failed: ${run['failure_count'] ?? 0}',
                            style: GoogleFonts.shareTech(
                              fontSize: 12,
                              color: JarvisColors.textPrimary,
                            ),
                          ),
                          if ((run['error'] ?? '').toString().trim().isNotEmpty)
                            Text(
                              'Error: ${run['error']}',
                              style: GoogleFonts.shareTech(
                                  fontSize: 11, color: JarvisColors.red),
                            ),
                        ],
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _AutomationLog {
  final String request;
  final String response;
  final bool success;

  _AutomationLog({
    required this.request,
    required this.response,
    required this.success,
  });
}
