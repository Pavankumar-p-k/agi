// lib/screens/chat_screen.dart
import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';
import '../services/api_service.dart';
import '../services/supabase_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';
import '../config/api_config.dart';

enum MessageVerification { verified, assumed, uncertain, none }

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with TickerProviderStateMixin {
  final _textCtrl = TextEditingController();
  final _goalCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _messages = <_StreamMessage>[];
  final _api = ApiService();
  final _supabase = SupabaseService();
  final _audioRecorder = AudioRecorder();
  final _audioPlayer = AudioPlayer();
  bool _useRemote = false;

  WebSocketChannel? _wsChannel;
  bool _loading = false;
  bool _loadingHistory = true;
  bool _isRecording = false;
  bool _isPlaying = false;
  String _currentTier = 'LOCAL';
  String _activeModel = 'llama3.1:8b';
  late AnimationController _typingCtrl;
  Timer? _streamingTimer;

  @override
  void initState() {
    super.initState();
    _typingCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600))
      ..repeat(reverse: true);
    _connectWebSocket();
    _loadHistory();
    _supabase.init();
  }

  Future<void> _connectWebSocket() async {
    try {
      _wsChannel = WebSocketChannel.connect(
        Uri.parse('${ApiConfig.wsUrl}/chat_stream'),
      );
      _wsChannel!.stream.listen(_onWsMessage, onError: (e) => debugPrint('[WS] Error: $e'));
    } catch (e) {
      debugPrint('[WS] Connection failed: $e');
    }
  }

  void _onWsMessage(dynamic data) {
    try {
      final msg = jsonDecode(data as String) as Map<String, dynamic>;
      final type = msg['type'] as String?;
      
      if (type == 'stream_token') {
        final token = msg['token'] as String? ?? '';
        final isComplete = msg['complete'] as bool? ?? false;
        
        if (_messages.isNotEmpty && _messages.last.role == 'assistant' && !_messages.last.isComplete) {
          setState(() {
            _messages.last.text += token;
            if (isComplete) {
              _messages.last.isComplete = true;
              _messages.last.verification = _parseVerification(msg['verification'] as String?);
              _currentTier = msg['privacy_tier'] as String? ?? 'LOCAL';
              _activeModel = msg['model'] as String? ?? 'llama3.1:8b';
            }
          });
        }
      } else if (type == 'tier_status') {
        setState(() {
          _currentTier = msg['tier'] as String? ?? 'LOCAL';
        });
      }
    } catch (e) {
      debugPrint('[WS] Parse error: $e');
    }
  }

  MessageVerification _parseVerification(String? v) {
    switch (v?.toLowerCase()) {
      case 'verified': return MessageVerification.verified;
      case 'retrieved': return MessageVerification.verified;
      case 'derived': return MessageVerification.verified;
      case 'assumed': return MessageVerification.assumed;
      case 'uncertain': return MessageVerification.uncertain;
      default: return MessageVerification.none;
    }
  }

  @override
  void dispose() {
    _typingCtrl.dispose();
    _textCtrl.dispose();
    _goalCtrl.dispose();
    _scrollCtrl.dispose();
    _audioRecorder.dispose();
    _audioPlayer.dispose();
    _wsChannel?.sink.close();
    _streamingTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadHistory() async {
    try {
      final history = await _api.getChatHistory();
      setState(() {
        for (final h in history) {
          _messages.add(_StreamMessage(
            role: h.role,
            text: h.message,
            verification: MessageVerification.none,
            isComplete: true,
          ));
        }
        _loadingHistory = false;
      });
      _scrollToBottom();
    } catch (_) {
      setState(() => _loadingHistory = false);
    }
  }

  Future<void> _send() async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty || _loading) return;

    _textCtrl.clear();
    setState(() {
      _messages.add(_StreamMessage(role: 'user', text: text));
      _messages.add(_StreamMessage(role: 'assistant', text: '', isComplete: false));
      _loading = true;
    });
    _scrollToBottom();

    try {
      _wsChannel?.sink.add(jsonEncode({'type': 'chat', 'text': text}));
    } catch (e) {
      try {
        final result = await _api.chat(text);
        setState(() {
          _messages.last.text = result['response'] ?? 'No response';
          _messages.last.isComplete = true;
          _loading = false;
        });
      } catch (_) {
        // Local server unreachable — try remote via Supabase
        final supabaseResp = await _supabase.sendAndWait(text);
        _handleSupabaseResponse(supabaseResp);
      }
    }
    _scrollToBottom();
  }

  Future<void> _sendGoal() async {
    final text = _goalCtrl.text.trim();
    if (text.isEmpty || _loading) return;

    _goalCtrl.clear();
    setState(() {
      _messages.add(_StreamMessage(role: 'user', text: text, intent: 'goal'));
      _messages.add(_StreamMessage(role: 'assistant', text: 'Analyzing project goal...', isComplete: false));
      _loading = true;
      _useRemote = true;
    });
    _scrollToBottom();

    try {
      final resp = await _supabase.sendGoal(text);
      _handleSupabaseResponse(resp);
    } catch (e) {
      setState(() {
        _messages.last.text = 'Failed to connect to JARVIS orchestration.';
        _messages.last.isComplete = true;
        _loading = false;
      });
    }
    _scrollToBottom();
  }

  void _handleSupabaseResponse(SupabaseResponse resp) {
    String displayText = resp.text;
    if (resp.files.isNotEmpty) {
      final names = resp.files.map((f) => f.name).join(', ');
      displayText += '\n\n📎 Received: $names';
    }
    setState(() {
      final last = _messages.last;
      last.text = displayText;
      last.plan = resp.plan;
      last.progress = resp.progress;
      last.isComplete = true;
      _loading = false;
      _useRemote = true;
    });
  }

  Future<void> _toggleRecording() async {
    if (_isRecording) {
      final path = await _audioRecorder.stop();
      setState(() => _isRecording = false);
      if (path != null) {
        final text = await _api.transcribeAudio(path);
        if (text.isNotEmpty) {
          _textCtrl.text = text;
          _send();
        }
      }
    } else {
      if (await _audioRecorder.hasPermission()) {
        await _audioRecorder.start(const RecordConfig(), path: 'temp_mic.wav');
        setState(() => _isRecording = true);
      }
    }
  }

  Future<void> _playLastResponse() async {
    if (_messages.isEmpty) return;
    final lastAi = _messages.lastWhere((m) => m.role == 'assistant' && m.text.isNotEmpty, orElse: () => _StreamMessage(role: 'dummy', text: ''));
    if (lastAi.text.isEmpty) return;
    
    try {
      final audioUrl = '${ApiConfig.baseUrl}/tts';
      await _audioPlayer.play(UrlSource(audioUrl));
      setState(() => _isPlaying = true);
      _audioPlayer.onPlayerComplete.listen((_) {
        setState(() => _isPlaying = false);
      });
    } catch (e) {
      debugPrint('[TTS] Error: $e');
    }
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      // HUD row
      Container(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: JarvisColors.border)),
        ),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Row(children: [
            HudRing(size: 60),
            const SizedBox(width: 12),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(_activeModel.toUpperCase(), style: GoogleFonts.orbitron(
                fontSize: 10, color: JarvisColors.cyan, fontWeight: FontWeight.bold
              )),
              Text('ACTIVE MODEL', style: GoogleFonts.orbitron(
                fontSize: 8, color: JarvisColors.textDim
              )),
            ]),
          ]),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Row(children: [
              if (_useRemote) ...[
                Container(
                  width: 8, height: 8,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    color: JarvisColors.purple,
                  ),
                ),
                const SizedBox(width: 6),
                Text('REMOTE', style: GoogleFonts.orbitron(
                  fontSize: 10, color: JarvisColors.purple,
                )),
              ] else ...[
                Container(
                  width: 8, height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _currentTier == 'LOCAL' 
                      ? JarvisColors.green 
                      : _currentTier == 'HYBRID' 
                        ? JarvisColors.cyan 
                        : JarvisColors.red,
                  ),
                ),
                const SizedBox(width: 6),
                Text(_currentTier, style: GoogleFonts.orbitron(
                  fontSize: 10, color: _currentTier == 'LOCAL' 
                    ? JarvisColors.green 
                    : _currentTier == 'HYBRID' 
                      ? JarvisColors.cyan 
                      : JarvisColors.red,
                )),
              ],
            ]),
            const SizedBox(height: 4),
            Text(_useRemote ? 'CONNECTION' : 'PRIVACY TIER', style: GoogleFonts.orbitron(
              fontSize: 8, color: JarvisColors.textDim
            )),
          ]),
        ]),
      ),

      // Goal Input
      Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: BoxDecoration(
          color: JarvisColors.bgCard.withValues(alpha: 0.5),
          border: const Border(bottom: BorderSide(color: JarvisColors.border)),
        ),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _goalCtrl,
              onSubmitted: (_) => _sendGoal(),
              style: GoogleFonts.shareTech(color: JarvisColors.purple, fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Describe a project... (JARVIS will plan it)',
                hintStyle: GoogleFonts.shareTech(color: JarvisColors.textDim, fontSize: 12),
                isDense: true,
                prefixIcon: const Icon(Icons.auto_awesome, color: JarvisColors.purple, size: 16),
                contentPadding: const EdgeInsets.symmetric(vertical: 8),
              ),
            ),
          ),
          const SizedBox(width: 12),
          GestureDetector(
            onTap: _sendGoal,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: JarvisColors.purple.withValues(alpha: 0.1),
                border: Border.all(color: JarvisColors.purple.withValues(alpha: 0.4)),
              ),
              child: Text('PLAN', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.purple, fontWeight: FontWeight.bold)),
            ),
          ),
        ]),
      ),

      // Messages
      Expanded(
        child: _loadingHistory
          ? const Center(child: CircularProgressIndicator(color: JarvisColors.cyan, strokeWidth: 1.5))
          : _messages.isEmpty
            ? _EmptyChat()
            : ListView.builder(
                controller: _scrollCtrl,
                padding: const EdgeInsets.all(16),
                itemCount: _messages.length + (_loading ? 1 : 0),
                itemBuilder: (ctx, i) {
                  if (i == _messages.length) return _TypingIndicator(ctrl: _typingCtrl);
                  return _MessageBubble(message: _messages[i], key: ValueKey(_messages[i].hashCode));
                },
              ),
      ),

      // Input row
      Container(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
        decoration: const BoxDecoration(
          color: JarvisColors.bgCard,
          border: Border(top: BorderSide(color: JarvisColors.border)),
        ),
        child: Row(children: [
          // Voice button
          GestureDetector(
            onTap: _toggleRecording,
            child: Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _isRecording ? JarvisColors.red.withValues(alpha: 0.2) : JarvisColors.bgPanel,
                border: Border.all(
                  color: _isRecording 
                    ? JarvisColors.red 
                    : JarvisColors.cyan.withValues(alpha: 0.5),
                ),
              ),
              child: Icon(
                _isRecording ? Icons.stop : Icons.mic,
                color: _isRecording ? JarvisColors.red : JarvisColors.cyan,
                size: 20,
              ),
            ),
          ),
          const SizedBox(width: 10),
          
          // Text input
          Expanded(
            child: TextFormField(
              controller: _textCtrl,
              style: GoogleFonts.shareTech(color: JarvisColors.textPrimary, fontSize: 14),
              onFieldSubmitted: (_) => _send(),
              decoration: InputDecoration(
                hintText: 'Enter command or query...',
                hintStyle: GoogleFonts.shareTech(color: JarvisColors.textDim, fontSize: 13),
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              ),
            ),
          ),
          const SizedBox(width: 10),
          
          // Play TTS button
          GestureDetector(
            onTap: _playLastResponse,
            child: Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: JarvisColors.bgPanel,
                border: Border.all(color: JarvisColors.cyan.withValues(alpha: 0.5)),
              ),
              child: Icon(
                _isPlaying ? Icons.stop : Icons.volume_up,
                color: JarvisColors.cyan,
                size: 20,
              ),
            ),
          ),
          const SizedBox(width: 8),
          
          // Send button
          GestureDetector(
            onTap: _send,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: [
                  JarvisColors.blue.withValues(alpha: 0.4),
                  JarvisColors.cyan.withValues(alpha: 0.2),
                ]),
                border: Border.all(color: JarvisColors.cyan.withValues(alpha: 0.5)),
              ),
              child: const Icon(Icons.send, color: JarvisColors.cyan, size: 18),
            ),
          ),
        ]),
      ),
    ]);
  }
}

class _StreamMessage {
  final String role;
  String text;
  MessageVerification verification;
  bool isComplete;
  String intent;
  Map<String, dynamic>? plan;
  Map<String, dynamic>? progress;

  _StreamMessage({
    required this.role,
    required this.text,
    this.verification = MessageVerification.none,
    this.isComplete = false,
    this.intent = 'chat',
    this.plan,
    this.progress,
  });
}

class _MessageBubble extends StatefulWidget {
  final _StreamMessage message;
  const _MessageBubble({required this.message, super.key});

  @override
  State<_MessageBubble> createState() => _MessageBubbleState();
}

class _MessageBubbleState extends State<_MessageBubble> with SingleTickerProviderStateMixin {
  late AnimationController _c;
  late Animation<double> _fade;
  late Animation<Offset> _slide;
  Timer? _progressTimer;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
    _fade = CurvedAnimation(parent: _c, curve: Curves.easeOut);
    _slide = Tween<Offset>(
      begin: Offset(widget.message.role == 'user' ? 0.1 : -0.1, 0),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _c, curve: Curves.easeOut));
    _c.forward();

    if (widget.message.progress != null && widget.message.progress!['status'] == 'executing') {
      _startProgressPolling();
    }
  }

  void _startProgressPolling() {
    _progressTimer?.cancel();
    _progressTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      final latest = await SupabaseService().getLatestResponse();
      if (latest != null && latest.progress != null) {
        if (mounted) {
          setState(() {
            widget.message.progress = latest.progress;
            widget.message.text = latest.text;
          });
        }
        if (latest.progress!['status'] != 'executing') {
          timer.cancel();
        }
      }
    });
  }

  @override
  void dispose() { 
    _c.dispose(); 
    _progressTimer?.cancel();
    super.dispose(); 
  }

  Color _getTagColor(MessageVerification v) {
    switch (v) {
      case MessageVerification.verified: return JarvisColors.green;
      case MessageVerification.assumed: return JarvisColors.orange;
      case MessageVerification.uncertain: return JarvisColors.red;
      case MessageVerification.none: return JarvisColors.textDim;
    }
  }

  String _getTagText(MessageVerification v) {
    switch (v) {
      case MessageVerification.verified: return '[VERIFIED]';
      case MessageVerification.assumed: return '[ASSUMED]';
      case MessageVerification.uncertain: return '[UNCERTAIN]';
      case MessageVerification.none: return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isUser = widget.message.role == 'user';
    final hasTag = widget.message.verification != MessageVerification.none;
    final hasPlan = widget.message.plan != null;
    final hasProgress = widget.message.progress != null;
    
    return FadeTransition(
      opacity: _fade,
      child: SlideTransition(
        position: _slide,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
            children: [
              if (!isUser) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  decoration: BoxDecoration(
                    border: Border.all(color: JarvisColors.cyan.withValues(alpha: 0.4)),
                    color: JarvisColors.cyan.withValues(alpha: 0.08),
                  ),
                  child: Text('J', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.cyan, fontWeight: FontWeight.w900)),
                ),
                const SizedBox(width: 10),
              ],
              Flexible(
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isUser ? JarvisColors.blue.withValues(alpha: 0.15) : JarvisColors.bgPanel,
                    border: Border.all(
                      color: isUser
                        ? JarvisColors.blue.withValues(alpha: 0.4)
                        : JarvisColors.border,
                    ),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (hasTag && !isUser)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          _getTagText(widget.message.verification),
                          style: GoogleFonts.orbitron(
                            fontSize: 9,
                            color: _getTagColor(widget.message.verification),
                          ),
                        ),
                      ),
                    
                    if (hasPlan) _PlanCard(plan: widget.message.plan!),
                    if (hasProgress) _ProgressIndicator(progress: widget.message.progress!),

                    AnimatedOpacity(
                      opacity: widget.message.isComplete ? 1.0 : 0.7,
                      duration: const Duration(milliseconds: 100),
                      child: Text(
                        widget.message.text,
                        style: GoogleFonts.shareTech(
                          fontSize: 14,
                          color: isUser ? JarvisColors.textPrimary.withValues(alpha: 0.9) : JarvisColors.textPrimary,
                          height: 1.5,
                        ),
                      ),
                    ),
                    const SizedBox(height: 4),
                    if (widget.message.isComplete)
                      Text(
                        'OK',
                        style: GoogleFonts.orbitron(fontSize: 8, letterSpacing: 1, color: JarvisColors.green),
                      ),
                  ]),
                ),
              ),
              if (isUser) ...[
                const SizedBox(width: 10),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  decoration: BoxDecoration(
                    border: Border.all(color: widget.message.intent == 'goal' ? JarvisColors.purple.withValues(alpha: 0.4) : JarvisColors.orange.withValues(alpha: 0.4)),
                    color: (widget.message.intent == 'goal' ? JarvisColors.purple : JarvisColors.orange).withValues(alpha: 0.08),
                  ),
                  child: Text(widget.message.intent == 'goal' ? 'G' : 'U', style: GoogleFonts.orbitron(fontSize: 10, color: widget.message.intent == 'goal' ? JarvisColors.purple : JarvisColors.orange, fontWeight: FontWeight.w900)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  final Map<String, dynamic> plan;
  const _PlanCard({required this.plan});

  IconData _getAgentIcon(String agent) {
    switch (agent.toLowerCase()) {
      case 'codex': return Icons.smart_toy_outlined;
      case 'aider': return Icons.build_outlined;
      case 'gemini': return Icons.science_outlined;
      case 'copilot': return Icons.lightbulb_outline;
      case 'shell': return Icons.terminal_outlined;
      default: return Icons.person_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final steps = plan['steps'] as List? ?? [];
    final goal = plan['goal'] as String? ?? 'New Project';
    final planId = plan['id']?.toString() ?? '';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: JarvisColors.purple.withValues(alpha: 0.05),
        border: Border.all(color: JarvisColors.purple.withValues(alpha: 0.3)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.description_outlined, color: JarvisColors.purple, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(goal, style: GoogleFonts.orbitron(fontSize: 12, color: JarvisColors.purple, fontWeight: FontWeight.bold)),
          ),
        ]),
        const SizedBox(height: 12),
        ...steps.map((s) {
          final sMap = s as Map;
          final agent = sMap['agent']?.toString() ?? 'unknown';
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(_getAgentIcon(agent), color: JarvisColors.textSecondary, size: 14),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  sMap['prompt']?.toString() ?? '',
                  style: GoogleFonts.shareTech(fontSize: 13, color: JarvisColors.textPrimary),
                ),
              ),
            ]),
          );
        }).toList(),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: ElevatedButton(
              onPressed: () => SupabaseService().approvePlan(planId),
              style: ElevatedButton.styleFrom(
                backgroundColor: JarvisColors.green.withValues(alpha: 0.1),
                side: const BorderSide(color: JarvisColors.green),
                padding: const EdgeInsets.symmetric(vertical: 8),
              ),
              child: Text('APPROVE', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.green)),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: ElevatedButton(
              onPressed: () => SupabaseService().rejectPlan(planId),
              style: ElevatedButton.styleFrom(
                backgroundColor: JarvisColors.red.withValues(alpha: 0.1),
                side: const BorderSide(color: JarvisColors.red),
                padding: const EdgeInsets.symmetric(vertical: 8),
              ),
              child: Text('REJECT', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.red)),
            ),
          ),
        ]),
      ]),
    );
  }
}

class _ProgressIndicator extends StatelessWidget {
  final Map<String, dynamic> progress;
  const _ProgressIndicator({required this.progress});

  @override
  Widget build(BuildContext context) {
    final status = progress['status']?.toString() ?? 'pending';
    final current = (progress['current_step'] as num?)?.toInt() ?? 0;
    final total = (progress['total_steps'] as num?)?.toInt() ?? 1;
    final desc = progress['step_description']?.toString() ?? 'Initializing...';
    final percent = (current / total).clamp(0.0, 1.0);

    Widget statusIcon;
    Color statusColor;
    if (status == 'executing') {
      statusIcon = const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: JarvisColors.cyan));
      statusColor = JarvisColors.cyan;
    } else if (status == 'done') {
      statusIcon = const Icon(Icons.check_circle, color: JarvisColors.green, size: 14);
      statusColor = JarvisColors.green;
    } else if (status == 'failed') {
      statusIcon = const Icon(Icons.error, color: JarvisColors.red, size: 14);
      statusColor = JarvisColors.red;
    } else {
      statusIcon = const Icon(Icons.schedule, color: JarvisColors.textDim, size: 14);
      statusColor = JarvisColors.textDim;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: JarvisColors.bgPanel,
        border: Border.all(color: statusColor.withValues(alpha: 0.4)),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text('EXECUTION PROGRESS', style: GoogleFonts.orbitron(fontSize: 9, color: statusColor, letterSpacing: 1)),
          Text('$current / $total', style: GoogleFonts.orbitron(fontSize: 9, color: statusColor)),
        ]),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: percent,
          backgroundColor: JarvisColors.border,
          color: statusColor,
          minHeight: 2,
        ),
        const SizedBox(height: 10),
        Row(children: [
          statusIcon,
          const SizedBox(width: 8),
          Expanded(
            child: Text(desc, style: GoogleFonts.shareTech(fontSize: 12, color: JarvisColors.textPrimary)),
          ),
        ]),
      ]),
    );
  }
}

class _TypingIndicator extends StatelessWidget {
  final AnimationController ctrl;
  const _TypingIndicator({required this.ctrl});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          decoration: BoxDecoration(
            border: Border.all(color: JarvisColors.cyan.withValues(alpha: 0.4)),
          ),
          child: Text('J', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.cyan, fontWeight: FontWeight.w900)),
        ),
        const SizedBox(width: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: JarvisColors.bgPanel,
            border: Border.all(color: JarvisColors.border),
          ),
          child: Row(children: List.generate(3, (i) => AnimatedBuilder(
            animation: ctrl,
            builder: (_, __) {
              final delay = i * 0.2;
              final v = (ctrl.value - delay).clamp(0.0, 1.0);
              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width: 5, height: 5,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: JarvisColors.cyan.withValues(alpha: 0.3 + v * 0.7),
                ),
              );
            },
          ))),
        ),
      ]),
    );
  }
}

class _EmptyChat extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        HudRing(size: 80),
        const SizedBox(height: 20),
        Text('AWAITING COMMAND', style: GoogleFonts.orbitron(
          fontSize: 12, letterSpacing: 3, color: JarvisColors.textSecondary,
        )),
        const SizedBox(height: 8),
        Text('Type a message or use voice input', style: GoogleFonts.shareTech(
          fontSize: 12, color: JarvisColors.textDim,
        )),
      ]),
    );
  }
}
