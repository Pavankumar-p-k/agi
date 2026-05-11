// lib/screens/chat_screen.dart
import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';
import '../services/api_service.dart';
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
  final _scrollCtrl = ScrollController();
  final _messages = <_StreamMessage>[];
  final _api = ApiService();
  final _audioRecorder = AudioRecorder();
  final _audioPlayer = AudioPlayer();

  WebSocketChannel? _wsChannel;
  bool _loading = false;
  bool _loadingHistory = true;
  bool _isRecording = false;
  bool _isPlaying = false;
  String _currentTier = 'LOCAL';
  String _activeModel = 'llama3.1:8b';
  String _streamingText = '';
  late AnimationController _typingCtrl;
  Timer? _streamingTimer;
  int _streamingIndex = 0;

  @override
  void initState() {
    super.initState();
    _typingCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600))
      ..repeat(reverse: true);
    _connectWebSocket();
    _loadHistory();
  }

  Future<void> _connectWebSocket() async {
    try {
      _wsChannel = WebSocketChannel.connect(
        Uri.parse('${ApiConfig.wsUrl}/chat_stream'),
      );
      _wsChannel!.stream.listen(_onWsMessage, onError: (e) => print('[WS] Error: $e'));
    } catch (e) {
      print('[WS] Connection failed: $e');
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
      print('[WS] Parse error: $e');
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
            role: h['role'] as String,
            text: h['message'] as String,
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
      final result = await _api.chat(text);
      setState(() {
        _messages.add(_StreamMessage(
          role: 'assistant',
          text: result['response'] ?? 'No response',
          verification: MessageVerification.none,
          isComplete: true,
        ));
        _loading = false;
      });
    }
    _scrollToBottom();
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
      print('[TTS] Error: $e');
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
            ]),
            const SizedBox(height: 4),
            Text('PRIVACY TIER', style: GoogleFonts.orbitron(
              fontSize: 8, color: JarvisColors.textDim
            )),
          ]),
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
                  return _MessageBubble(message: _messages[i]);
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
                color: _isRecording ? JarvisColors.red.withOpacity(0.2) : JarvisColors.bgPanel,
                border: Border.all(
                  color: _isRecording 
                    ? JarvisColors.red 
                    : JarvisColors.cyan.withOpacity(0.5),
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
                border: Border.all(color: JarvisColors.cyan.withOpacity(0.5)),
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
                  JarvisColors.blue.withOpacity(0.4),
                  JarvisColors.cyan.withOpacity(0.2),
                ]),
                border: Border.all(color: JarvisColors.cyan.withOpacity(0.5)),
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
  _StreamMessage({
    required this.role,
    required this.text,
    this.verification = MessageVerification.none,
    this.isComplete = false,
  });
}

class _MessageBubble extends StatefulWidget {
  final _StreamMessage message;
  const _MessageBubble({required this.message});

  @override
  State<_MessageBubble> createState() => _MessageBubbleState();
}

class _MessageBubbleState extends State<_MessageBubble> with SingleTickerProviderStateMixin {
  late AnimationController _c;
  late Animation<double> _fade;
  late Animation<Offset> _slide;

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
  }

  @override
  void dispose() { _c.dispose(); super.dispose(); }

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
                    border: Border.all(color: JarvisColors.cyan.withOpacity(0.4)),
                    color: JarvisColors.cyan.withOpacity(0.08),
                  ),
                  child: Text('J', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.cyan, fontWeight: FontWeight.w900)),
                ),
                const SizedBox(width: 10),
              ],
              Flexible(
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isUser ? JarvisColors.blue.withOpacity(0.15) : JarvisColors.bgPanel,
                    border: Border.all(
                      color: isUser
                        ? JarvisColors.blue.withOpacity(0.4)
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
                    AnimatedOpacity(
                      opacity: widget.message.isComplete ? 1.0 : 0.7,
                      duration: const Duration(milliseconds: 100),
                      child: Text(
                        widget.message.text,
                        style: GoogleFonts.shareTech(
                          fontSize: 14,
                          color: isUser ? JarvisColors.textPrimary.withOpacity(0.9) : JarvisColors.textPrimary,
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
                    border: Border.all(color: JarvisColors.orange.withOpacity(0.4)),
                    color: JarvisColors.orange.withOpacity(0.08),
                  ),
                  child: Text('U', style: GoogleFonts.orbitron(fontSize: 10, color: JarvisColors.orange, fontWeight: FontWeight.w900)),
                ),
              ],
            ],
          ),
        ),
      ),
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
            border: Border.all(color: JarvisColors.cyan.withOpacity(0.4)),
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
                  color: JarvisColors.cyan.withOpacity(0.3 + v * 0.7),
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