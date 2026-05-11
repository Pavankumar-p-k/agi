// lib/ai/social_prompt_builder.dart

import 'package:jarvis_app/db/local_db.dart';
import 'package:jarvis_app/services/feature_settings.dart';
import 'package:jarvis_app/services/message_inbox_service.dart';

enum ReplyTone { casual, friendly, formal, brief }

class SocialPromptBuilder {
  static const int _historyLimit = 6;

  /// Full build — loads history from DB automatically.
  static Future<String> buildFromDb(InboxMessage message) async {
    final rows = await LocalDB.getRecentMessages(
      sender: message.sender,
      platform: message.platform,
      limit: _historyLimit,
    );

    final history = rows.map((r) {
      final isMine = (r['reply_sent'] as int? ?? 0) == 1;
      final text   = r['text'] as String? ?? '';
      return '  ${isMine ? 'Me' : 'Them'}: $text';
    }).join('\n');

    return _compose(
      message:  message,
      history:  history,
      userName: FeatureSettings.getUserName(),
      tone:     _toneFromString(FeatureSettings.getReplyTone()),
    );
  }

  static String _compose({
    required InboxMessage message,
    required String history,
    required String userName,
    required ReplyTone tone,
  }) {
    final platform  = _platformLabel(message.platform);
    final toneGuide = _toneGuide(tone);
    final timeHint  = _timeHint();

    return '''You are replying on behalf of $userName on $platform.

PERSONA
- Write exactly as $userName would — short, natural, human.
- $toneGuide
- Maximum 1–2 sentences. Never more than 2.
- Never start with "Hi", "Hello", "Hey there" unless they greeted first.
- No sign-offs ("Best", "Thanks", "Regards").
- No filler ("Of course!", "Absolutely!", "Great question!").
- Mirror their energy: if they used emoji, you can use 1 max. If they were brief, be brief.
- Never repeat their question back to them.
- Never say you are an AI or assistant.
- Reply in the same language they wrote in.

CONTEXT
$timeHint

${history.isNotEmpty ? 'RECENT CONVERSATION\n$history\n' : ''}MESSAGE TO REPLY TO
${message.sender}: ${message.text}

$userName's reply (reply text only, nothing else):''';
  }

  static String _platformLabel(String p) {
    switch (p.toLowerCase()) {
      case 'whatsapp':  return 'WhatsApp';
      case 'instagram': return 'Instagram DM';
      case 'telegram':  return 'Telegram';
      case 'discord':   return 'Discord';
      case 'linkedin':  return 'LinkedIn';
      case 'snapchat':  return 'Snapchat';
      case 'sms':       return 'SMS';
      default:          return 'messaging';
    }
  }

  static String _toneGuide(ReplyTone t) {
    switch (t) {
      case ReplyTone.casual:
        return 'Tone: very casual, relaxed. Contractions always. Think texting a close friend.';
      case ReplyTone.friendly:
        return 'Tone: warm and friendly but not too casual. Like texting a colleague you like.';
      case ReplyTone.formal:
        return 'Tone: polite and professional. Full sentences, correct grammar, no slang.';
      case ReplyTone.brief:
        return 'Tone: extremely brief. 1–5 words is fine. Single emoji is fine.';
    }
  }

  static String _timeHint() {
    final h = DateTime.now().hour;
    if (h >= 23 || h < 6)  return '- It\'s late at night — keep it short.';
    if (h >= 6  && h < 12) return '- It\'s morning.';
    if (h >= 12 && h < 17) return '- It\'s afternoon.';
    return '- It\'s evening.';
  }

  static ReplyTone _toneFromString(String s) {
    switch (s) {
      case 'friendly': return ReplyTone.friendly;
      case 'formal':   return ReplyTone.formal;
      case 'brief':    return ReplyTone.brief;
      default:         return ReplyTone.casual;
    }
  }
}
