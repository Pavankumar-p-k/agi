// lib/screens/chat_screen.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../services/talkback_service.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with TickerProviderStateMixin {
  final _textCtrl    = TextEditingController();
  final _scrollCtrl  = ScrollController();
  final _messages    = <ChatMessage>[];
  final _api         = ApiService();

  bool _loading    = false;
  bool _loadingHistory = true;
  late AnimationController _typingCtrl;
  late TalkBackService _talkback;
  late Future<void> Function(String) _speechHandler;

  @override
  void initState() {
    super.initState();
    _talkback = context.read<TalkBackService>();
    _speechHandler = (text) async {
      if (!mounted) return;
      _textCtrl.text = text;
      await _send();
    };
    _talkback.onUserSpeech = _speechHandler;

    _typingCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 600))
      ..repeat(reverse: true);
    _loadHistory();
  }

  @override
  void dispose() {
    if (_talkback.onUserSpeech == _speechHandler) {
      _talkback.onUserSpeech = null;
    }
    _typingCtrl.dispose();
    _textCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadHistory() async {
    try {
      final history = await _api.getChatHistory();
      setState(() { _messages.addAll(history); _loadingHistory = false; });
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
      _messages.add(ChatMessage(role: 'user', message: text));
      _loading = true;
    });
    _scrollToBottom();

    try {
      final result = await _api.chat(text);
      final response = (result['response'] ?? 'No response').toString();
      setState(() {
        _messages.add(ChatMessage(
          role: 'assistant',
          message: response,
        ));
        _loading = false;
      });
      await _talkback.respondWithSpeech(response);
    } catch (e) {
      setState(() {
        _messages.add(ChatMessage(role: 'assistant', message: 'Connection error. Is the JARVIS server running?'));
        _loading = false;
      });
      await _talkback.respondWithSpeech('Connection error. Is the JARVIS server running?');
    }
    _scrollToBottom();
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
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: JarvisColors.border)),
        ),
        child: Center(child: HudRing(size: 100)),
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
          const SizedBox(width: 8),
          GestureDetector(
            onTap: () {
              if (_talkback.isListening) {
                _talkback.stopListening();
              } else {
                _talkback.startListening();
              }
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _talkback.isListening
                    ? JarvisColors.cyan.withOpacity(0.18)
                    : JarvisColors.bgPanel,
                border: Border.all(
                  color: _talkback.isListening
                      ? JarvisColors.cyan
                      : JarvisColors.border,
                ),
              ),
              child: Icon(
                _talkback.isListening ? Icons.mic : Icons.mic_none_outlined,
                color: _talkback.isListening
                    ? JarvisColors.cyan
                    : JarvisColors.textSecondary,
                size: 18,
              ),
            ),
          ),
          const SizedBox(width: 10),
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

class _MessageBubble extends StatefulWidget {
  final ChatMessage message;
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
    _fade  = CurvedAnimation(parent: _c, curve: Curves.easeOut);
    _slide = Tween<Offset>(
      begin: Offset(widget.message.role == 'user' ? 0.1 : -0.1, 0),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _c, curve: Curves.easeOut));
    _c.forward();
  }

  @override
  void dispose() { _c.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final isUser = widget.message.role == 'user';
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
                    Text(
                      widget.message.message,
                      style: GoogleFonts.shareTech(
                        fontSize: 14,
                        color: isUser ? JarvisColors.textPrimary.withOpacity(0.9) : JarvisColors.textPrimary,
                        height: 1.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${widget.message.timestamp.hour.toString().padLeft(2,'0')}:${widget.message.timestamp.minute.toString().padLeft(2,'0')}',
                      style: GoogleFonts.orbitron(fontSize: 8, letterSpacing: 1, color: JarvisColors.textSecondary),
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
        Text('Type a message or ask anything', style: GoogleFonts.shareTech(
          fontSize: 12, color: JarvisColors.textDim,
        )),
      ]),
    );
  }
}
