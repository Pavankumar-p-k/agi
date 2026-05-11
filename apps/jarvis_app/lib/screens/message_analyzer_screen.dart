// lib/screens/message_analyzer_screen.dart
// JARVIS MESSAGE ANALYZER SCREEN
// Shows all incoming messages with full AI analysis:
//  • Sentiment score + color
//  • Intent badge
//  • Friend type
//  • Language detected
//  • Suggested reply
//  • Send / Edit / Dismiss controls

import 'package:flutter/material.dart';
import '../ai/message_analyzer.dart';
import '../services/message_inbox_service.dart';
import '../theme/app_theme.dart';
import '../widgets/jarvis_widgets.dart';

class MessageAnalyzerScreen extends StatefulWidget {
  const MessageAnalyzerScreen({super.key});

  @override
  State<MessageAnalyzerScreen> createState() => _MessageAnalyzerScreenState();
}

class _MessageAnalyzerScreenState extends State<MessageAnalyzerScreen>
    with SingleTickerProviderStateMixin {

  String  _filter  = 'all';
  bool    _autoReply = true;

  final _platforms = ['all', 'whatsapp', 'instagram', 'sms', 'telegram'];

  final _platColors = const {
    'whatsapp':  Color(0xFF25D366),
    'instagram': Color(0xFFE1306C),
    'sms':       Color(0xFF4CAF50),
    'telegram':  Color(0xFF0088CC),
    'all':       Color(0xFF00F0FF),
  };

  @override
  void initState() {
    super.initState();
    // Start listening for new messages
    MessageInboxService.start();
    MessageInboxService.autoReplyEnabled = _autoReply;
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [

      // Header
      _buildHeader(),

      // Platform filter
      _buildPlatformFilter(),

      // Message list
      Expanded(
        child: StreamBuilder<InboxMessage>(
          stream: MessageInboxService.stream,
          builder: (_, snap) {
            final msgs = MessageInboxService.getByPlatform(_filter);
            if (msgs.isEmpty) return _buildEmptyState();
            return ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: msgs.length,
              itemBuilder: (_, i) => _buildMessageCard(msgs[i]),
            );
          },
        ),
      ),
    ]);
  }

  // ── Header ────────────────────────────────────────────────

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: const BoxDecoration(
        color: J.bg1,
        border: Border(bottom: BorderSide(color: J.border0)),
      ),
      child: Row(children: [
        const Icon(Icons.analytics_outlined, color: J.cyan, size: 18),
        const SizedBox(width: 10),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('MSG ANALYZER', style: J.orbitron(12, spacing: 2)),
            Text('AI reads + replies to your messages',
                style: J.shareTech(10, color: J.t3)),
          ],
        )),

        // Auto-reply toggle
        Row(children: [
          Text('AUTO REPLY', style: J.orbitron(8, color: J.t3, spacing: 1)),
          const SizedBox(width: 6),
          Switch(
            value: _autoReply,
            onChanged: (v) {
              setState(() => _autoReply = v);
              MessageInboxService.autoReplyEnabled = v;
            },
            activeColor: J.cyan,
            activeTrackColor: J.cyan.withOpacity(0.2),
            inactiveThumbColor: J.t3,
            inactiveTrackColor: J.bg4,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
        ]),
      ]),
    );
  }

  // ── Platform filter chips ─────────────────────────────────

  Widget _buildPlatformFilter() {
    return Container(
      height: 44,
      color: J.bg1,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        children: _platforms.map((p) {
          final selected = _filter == p;
          final color    = _platColors[p] ?? J.cyan;
          return GestureDetector(
            onTap: () => setState(() => _filter = p),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color:  selected ? color.withOpacity(0.12) : J.bg3,
                border: Border.all(
                  color: selected ? color : J.border0,
                  width: selected ? 1.5 : 1,
                ),
              ),
              child: Text(p.toUpperCase(),
                  style: J.orbitron(8,
                      color: selected ? color : J.t3, spacing: 1)),
            ),
          );
        }).toList(),
      ),
    );
  }

  // ── Message card with full analysis ───────────────────────

  Widget _buildMessageCard(InboxMessage msg) {
    final a     = msg.analysis;
    final pCol  = _platColors[msg.platform] ?? J.cyan;
    final sCol  = a.sentiment == 'positive' ? J.green :
                  a.sentiment == 'negative' ? J.red   : J.t2;
    final uCol  = a.urgency == 'high'   ? J.red   :
                  a.urgency == 'medium' ? J.amber  : J.green;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color:  J.bg2,
        border: Border(
          left: BorderSide(color: pCol, width: 3),
          top:  const BorderSide(color: J.border0),
          right:const BorderSide(color: J.border0),
          bottom:const BorderSide(color: J.border0),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          // Sender row
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
            child: Row(children: [
              Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: pCol, width: 1.5),
                    color: pCol.withOpacity(0.1)),
                child: Center(
                  child: Text(
                    msg.sender.isNotEmpty
                        ? msg.sender[0].toUpperCase()
                        : '?',
                    style: J.orbitron(13,
                        weight: FontWeight.w900, color: pCol, spacing: 0),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(msg.sender,
                      style: J.rajdhani(15, weight: FontWeight.w700)),
                  Row(children: [
                    Text(msg.platform.toUpperCase(),
                        style: J.shareTech(9, color: pCol)),
                    const SizedBox(width: 8),
                    Text(_formatTime(msg.timestamp),
                        style: J.shareTech(9, color: J.t3)),
                  ]),
                ],
              )),

              // Urgency badge
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  border: Border.all(color: uCol.withOpacity(0.5)),
                  color: uCol.withOpacity(0.08),
                ),
                child: Text(a.urgency.toUpperCase(),
                    style: J.orbitron(7, color: uCol, spacing: 1)),
              ),
            ]),
          ),

          // Original message
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color:  J.bg3,
                border: Border.all(color: J.border0),
              ),
              child: Text(msg.text,
                  style: J.rajdhani(14, color: J.t1)),
            ),
          ),

          // Analysis row
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Wrap(spacing: 6, runSpacing: 6, children: [
              _Badge(a.language.toUpperCase(), J.cyan),
              _Badge(a.intent.toUpperCase(),
                  a.intent == 'angry' ? J.red :
                  a.intent == 'love'  ? J.orange :
                  a.intent == 'help'  ? J.amber : J.cyanDim),
              _Badge(a.sentiment.toUpperCase(), sCol),
              _Badge(a.friendType.toUpperCase(),
                  a.friendType == 'close' ? J.amber : J.t3),
              _Badge('SCORE ${a.sentimentScore.toStringAsFixed(1)}',
                  sCol),
            ]),
          ),

          // Suggested reply
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.reply, size: 12, color: J.cyan),
                  const SizedBox(width: 6),
                  Text('JARVIS REPLY', style: J.orbitron(9,
                      color: J.cyan, spacing: 1)),
                  const SizedBox(width: 8),
                  Text('(reason: ${a.replyReason})',
                      style: J.shareTech(9, color: J.t3)),
                ]),
                const SizedBox(height: 6),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: J.cyan.withOpacity(0.04),
                    border: Border.all(
                        color: J.cyan.withOpacity(0.25)),
                  ),
                  child: Text(a.suggestedReply,
                      style: J.rajdhani(14, color: J.t1)),
                ),
              ],
            ),
          ),

          // Action buttons
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              Expanded(
                child: CyberButton(
                  label: 'SEND REPLY',
                  icon:  Icons.send_outlined,
                  color: J.green,
                  onTap: () => _sendReply(msg),
                ),
              ),
              const SizedBox(width: 8),
              CyberButton(
                label: 'EDIT',
                icon:  Icons.edit_outlined,
                color: J.amber,
                onTap: () => _editReply(msg),
              ),
              const SizedBox(width: 8),
              CyberButton(
                label: 'SKIP',
                icon:  Icons.close,
                color: J.t3,
                onTap: () {},
              ),
            ]),
          ),
        ],
      ),
    );
  }

  // ── Send reply ────────────────────────────────────────────

  void _sendReply(InboxMessage msg) {
    MessageInboxService.sendManualReply(msg, msg.analysis.suggestedReply);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text('Replied to ${msg.sender}',
          style: J.shareTech(12)),
      backgroundColor: J.bg3,
    ));
  }

  // ── Edit reply before sending ─────────────────────────────

  void _editReply(InboxMessage msg) {
    final ctrl = TextEditingController(text: msg.analysis.suggestedReply);
    showModalBottomSheet(
      context: context,
      backgroundColor: J.bg1,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (_) => Padding(
        padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom),
        child: Container(
          padding: const EdgeInsets.all(20),
          decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: J.border1))),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('EDIT REPLY', style: J.orbitron(12, spacing: 2)),
            const SizedBox(height: 14),
            TextField(
              controller: ctrl,
              style: J.rajdhani(14),
              maxLines: 4,
              autofocus: true,
              decoration: InputDecoration(
                hintText: 'Edit reply...',
                hintStyle: J.shareTech(12, color: J.t4),
              ),
            ),
            const SizedBox(height: 14),
            CyberButton(
              label: 'SEND',
              icon:  Icons.send_outlined,
              color: J.green,
              filled: true,
              width: double.infinity,
              onTap: () {
                Navigator.pop(context);
                MessageInboxService.sendManualReply(msg, ctrl.text.trim());
              },
            ),
          ]),
        ),
      ),
    );
  }

  // ── Empty state ───────────────────────────────────────────

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.inbox_outlined, size: 48, color: J.t4),
          const SizedBox(height: 16),
          Text('NO MESSAGES YET',
              style: J.orbitron(12, color: J.t3, spacing: 2)),
          const SizedBox(height: 8),
          Text('Enable Notification Access in Android Settings\n'
               'to let JARVIS read your messages',
               style: J.rajdhani(13, color: J.t3),
               textAlign: TextAlign.center),
          const SizedBox(height: 20),
          CyberButton(
            label: 'OPEN SETTINGS',
            icon:  Icons.settings_outlined,
            onTap: () {/* open notification settings */},
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime dt) {
    final now  = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours   < 24) return '${diff.inHours}h ago';
    return '${dt.day}/${dt.month}';
  }
}


class _Badge extends StatelessWidget {
  final String label;
  final Color  color;
  const _Badge(this.label, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color:  color.withOpacity(0.08),
        border: Border.all(color: color.withOpacity(0.35)),
      ),
      child: Text(label, style: J.orbitron(7, color: color, spacing: 1)),
    );
  }
}
