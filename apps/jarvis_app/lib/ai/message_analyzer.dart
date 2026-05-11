// lib/ai/message_analyzer.dart
// JARVIS MESSAGE ANALYZER
// ═══════════════════════════════════════════════════════════
// Analyses every incoming WhatsApp/Instagram/SMS message:
//  1. Detects who the sender is (friend type: close/normal/unknown)
//  2. Scores sentiment (positive/negative/neutral)
//  3. Detects urgency (high/medium/low)
//  4. Classifies intent (greeting/question/need help/angry/love/etc)
//  5. Detects Telugu/English/mixed language
//  6. Checks if needs identity reveal
//  7. Generates a Pavan-style reply in same language
//  8. All 100% offline — no server, no internet
// ═══════════════════════════════════════════════════════════

import 'dart:math';
import '../db/local_db.dart';
import 'offline_ai.dart';

// ── Message analysis result ───────────────────────────────────
class MessageAnalysis {
  final String   sender;
  final String   platform;
  final String   originalText;
  final String   language;        // english | telugu | mixed
  final String   intent;          // greeting|question|help|angry|love|casual|urgent|identity
  final String   sentiment;       // positive | negative | neutral
  final String   urgency;         // high | medium | low
  final String   friendType;      // close | normal | unknown
  final double   sentimentScore;  // -1.0 to 1.0
  final bool     needsReply;
  final bool     isIdentityQuestion;
  final String   suggestedReply;
  final String   replyReason;     // why this reply was chosen

  const MessageAnalysis({
    required this.sender,
    required this.platform,
    required this.originalText,
    required this.language,
    required this.intent,
    required this.sentiment,
    required this.urgency,
    required this.friendType,
    required this.sentimentScore,
    required this.needsReply,
    required this.isIdentityQuestion,
    required this.suggestedReply,
    required this.replyReason,
  });

  Map<String, dynamic> toMap() => {
    'sender':              sender,
    'platform':            platform,
    'original_text':       originalText,
    'language':            language,
    'intent':              intent,
    'sentiment':           sentiment,
    'urgency':             urgency,
    'friend_type':         friendType,
    'sentiment_score':     sentimentScore,
    'needs_reply':         needsReply,
    'is_identity_question':isIdentityQuestion,
    'suggested_reply':     suggestedReply,
    'reply_reason':        replyReason,
  };
}


class MessageAnalyzer {
  final _rand = Random();
  final _ai   = OfflineAI();

  // ── Language detection ────────────────────────────────────
  static const _teluguWords = [
    'bro', 'anna', 'nuvvu', 'neenu', 'mee', 'meeru', 'ela',
    'unnav', 'unnaru', 'cheyyi', 'cheppandi', 'thelusule',
    'naaku', 'naku', 'ikkade', 'akkade', 'enti', 'em',
    'evaru', 'emina', 'ledhu', 'ledu', 'undi', 'unaav',
    'vachindhi', 'vachindi', 'pampinchandi', 'chudandi',
    'okey', 'sare', 'sari', 'ayyindi', 'kaadu', 'kadu',
    'antunnav', 'chestunnav', 'pothunna', 'vastanu',
    'manchi', 'baaga', 'bagundi', 'marchipoma', 'gurtu',
    'tho', 'lo', 'ki', 'ni', 'ga', 'ra', 'da', 'va',
  ];

  // ── Identity question detection ───────────────────────────
  static const _identityTriggers = [
    'evaru nuvu', 'evaru nuvvu', 'nuvvu evaru', 'neevaru',
    'mee peru enti', 'nee peru enti', 'idi evaru',
    'who are you', 'who r u', 'who is this', 'whos this',
    'is this pavan', 'pavan na', 'pavan unnada',
    'are you a bot', 'are you ai', 'jarvis na',
    'nuvvu robot va', 'nuvvu ai va', 'evari assistant',
    'introduce yourself', 'who am i talking to',
  ];

  // ── Urgency signals ───────────────────────────────────────
  static const _highUrgency = [
    'emergency', 'urgent', 'asap', 'help me', 'please', 'sos',
    'hospital', 'accident', 'immediately', 'right now',
    'important', 'serious', 'call me now', 'reply fast',
    'fast reply', 'quick', 'abhi', 'ippude', 'velu velu',
    'danger', 'problem', 'issue', 'stuck', 'need you',
  ];

  static const _lowUrgency = [
    'whenever', 'no rush', 'take your time', 'later',
    'sometime', 'free ga', 'time undi ante', 'ok ok',
  ];

  // ── Sentiment ─────────────────────────────────────────────
  static const _posWords = [
    'happy', 'love', 'great', 'awesome', 'nice', 'good',
    'thanks', 'thank you', 'haha', 'lol', '😂', '❤', '🥰',
    '😊', '😁', '🔥', '💯', 'best', 'super', 'excellent',
    'baagundi', 'manchi', 'chala', 'anthe bro', 'wow',
    'congrats', 'happy', 'proud', 'glad', 'enjoy',
  ];

  static const _negWords = [
    'sad', 'bad', 'angry', 'hate', 'worst', 'terrible',
    'hurt', 'cry', 'miss', 'alone', 'depressed', 'upset',
    'frustrated', 'annoyed', 'bored', 'tired', 'sick',
    '😢', '😞', '😡', '💔', '😤', 'sorry', 'problem',
    'kavali', 'baadhaga', 'kastam', 'nanu', 'marchipoya',
  ];

  // ── Intent patterns ───────────────────────────────────────
  static const _greetingWords = [
    'hi', 'hello', 'hey', 'hlo', 'sup', 'yo', 'namasthe',
    'namaskar', 'good morning', 'good evening', 'good night',
    'morning', 'evening', 'night bro',
  ];

  static const _questionWords = [
    'what', 'when', 'where', 'why', 'how', 'which', 'who',
    'em', 'emi', 'ela', 'epudu', 'ekkada', 'enduku', 'evaru',
    '?',
  ];

  static const _helpWords = [
    'help', 'please', 'can you', 'could you', 'need you',
    'sahayam', 'help cheyyi', 'help kavali', 'help pampinchu',
  ];

  static const _angryWords = [
    'angry', 'mad', 'hate', 'shut up', 'go away', 'leave me',
    'stupid', 'idiot', 'worst', 'never talk', 'block',
    'kopam', 'virakti', 'veyi', 'povu', 'marchipo',
  ];

  static const _loveWords = [
    'love you', 'miss you', 'i love', 'i miss',
    'love u', 'miss u', '❤', '🥰', '💕', '😘',
    'nenu ninnu', 'nenu nuvvu', 'love chestunan',
  ];

  // ── Close friend signals (conversation history based) ────
  static const _closeFriendSignals = [
    'bro', 'anna', 'da', 'ra', 'yaar', 'dost', 'machan',
    'buddy', 'mate', 'pa', 'ae', 'di',
  ];

  // ═════════════════════════════════════════════════════════
  //  MAIN ANALYZE METHOD
  // ═════════════════════════════════════════════════════════

  Future<MessageAnalysis> analyze({
    required String sender,
    required String platform,
    required String message,
    int conversationCount = 0,  // how many past messages from this sender
  }) async {
    final text   = message.toLowerCase().trim();
    final lang   = _detectLanguage(text);
    final intent = _detectIntent(text);
    final senti  = _detectSentiment(text);
    final urgency= _detectUrgency(text);
    final isId   = _isIdentityQuestion(text);
    final fType  = _detectFriendType(sender, text, conversationCount);
    final score  = _sentimentScore(text);

    // Decide if reply is needed
    final needsReply = _shouldReply(intent, urgency, isId);

    // Generate reply
    final reply = await _generateReply(
      sender:       sender,
      text:         message,
      language:     lang,
      intent:       intent,
      sentiment:    senti,
      urgency:      urgency,
      friendType:   fType,
      isIdentity:   isId,
      score:        score,
    );

    return MessageAnalysis(
      sender:              sender,
      platform:            platform,
      originalText:        message,
      language:            lang,
      intent:              intent,
      sentiment:           senti,
      urgency:             urgency,
      friendType:          fType,
      sentimentScore:      score,
      needsReply:          needsReply,
      isIdentityQuestion:  isId,
      suggestedReply:      reply.text,
      replyReason:         reply.data?['reason'] ?? intent,
    );
  }

  // ═════════════════════════════════════════════════════════
  //  REPLY GENERATOR — Pavan-style, English + Telugu
  // ═════════════════════════════════════════════════════════

  Future<AIResponse> _generateReply({
    required String sender,
    required String text,
    required String language,
    required String intent,
    required String sentiment,
    required String urgency,
    required String friendType,
    required bool   isIdentity,
    required double score,
  }) async {
    final isTelugu = language == 'telugu' || language == 'mixed';
    final isClose  = friendType == 'close';

    // 1. Identity reveal — highest priority
    if (isIdentity) {
      final revealEn = await localDB.getIdentity('reveal_response_en');
      final revealTe = await localDB.getIdentity('reveal_response_te');
      return AIResponse(
        text:   isTelugu ? revealTe : revealEn,
        action: AIAction.identityReveal,
        data:   {'reason': 'identity_question'},
      );
    }

    // 2. High urgency — always reply clearly
    if (urgency == 'high') {
      final replies = isTelugu ? [
        "Bro em ayindi? Ippude Pavan ki cheptanu — wait cheyyi",
        "Urgent ga undi — Pavan busy ga unnaadu, nenu message chestunaanu",
        "Sare bro — Pavan ki immediately cheppistanu, hold on",
      ] : [
        "Hey, Pavan is currently unavailable but I'll reach him immediately",
        "Got it — this seems urgent. I'll make sure Pavan sees this right away",
        "Pavan is busy right now — I'm flagging this as urgent for him",
      ];
      return AIResponse(
        text:   _pick(replies),
        action: AIAction.none,
        data:   {'reason': 'high_urgency'},
      );
    }

    // 3. Angry message — de-escalate
    if (intent == 'angry') {
      final replies = isTelugu ? [
        "Sare bro — em ayindi? Calm ga cheppinchandi",
        "Bro kopam teeskokapo — em problem undo cheppu",
        "Ayyo em ayindi bro? Cheppandi telustunaanu",
      ] : [
        "Hey, take it easy — what's going on?",
        "I hear you — want to talk about what happened?",
        "Pavan will get back to you soon — hope you feel better",
      ];
      return AIResponse(
        text:   _pick(replies),
        action: AIAction.none,
        data:   {'reason': 'de_escalate'},
      );
    }

    // 4. Sad / emotional message — warm response
    if (sentiment == 'negative' && score < -0.3) {
      final replies = isTelugu ? [
        "Bro em ayindi? Cheppinchandi — vinataniki ikkade unnanu",
        "Sare bro — kashta padindhi em? Cheppinchandi",
        "Anna baadha padanakapo — Pavan ki cheptanu meeru okay na?",
      ] : [
        "Hey, you okay? Pavan will check in with you soon",
        "I can see something's off — Pavan will reach you shortly",
        "Hope everything's alright — Pavan is busy but I'll let him know",
      ];
      return AIResponse(
        text:   _pick(replies),
        action: AIAction.none,
        data:   {'reason': 'emotional_support'},
      );
    }

    // 5. Love / affectionate — warm reply
    if (intent == 'love') {
      final replies = isTelugu ? [
        "Aww bro 🥰 Pavan ki cheptanu — busy ga unnaadu ippudu",
        "Haha 😊 Pavan ippudu available kaadu — message cheppistanu",
      ] : [
        "Aw, that's sweet 🥰 Pavan will see this — he's a bit busy right now",
        "😊 Noted! I'll make sure Pavan gets this message",
      ];
      return AIResponse(
        text:   _pick(replies),
        action: AIAction.none,
        data:   {'reason': 'affectionate'},
      );
    }

    // 6. Greeting — respond naturally
    if (intent == 'greeting') {
      if (isClose) {
        final replies = isTelugu ? [
          "Heyy bro! Ela unnav? Pavan ippudu busy — wait cheyyi",
          "Ra bro! Ela unnav? Pavan lo undi — cheppista niku",
          "Haha enti bro! Pavan busy ga unnadu — message pampinchadu",
        ] : [
          "Hey hey! Pavan's tied up right now — I'll tell him you said hi",
          "Heyy! He's busy at the moment — I'll let him know",
          "Hey! Pavan is occupied — will pass your message along",
        ];
        return AIResponse(text: _pick(replies), action: AIAction.none,
            data: {'reason': 'greeting_close_friend'});
      } else {
        final replies = isTelugu ? [
          "Namasthe! Pavan ippudu available kaadu — meeru message cheppinchandi",
          "Hello! Pavan busy ga unnadu — nenu JARVIS, message relay chestunaanu",
        ] : [
          "Hello! Pavan isn't available right now — I'm JARVIS, his assistant",
          "Hi there! Pavan is currently busy — can I take a message?",
        ];
        return AIResponse(text: _pick(replies), action: AIAction.none,
            data: {'reason': 'greeting_normal'});
      }
    }

    // 7. Question — acknowledge and defer
    if (intent == 'question') {
      final replies = isTelugu ? [
        "Bro Pavan ippudu busy — question cheppinchav, reply chestunaadu",
        "Sare bro — Pavan ki cheptanu, tondarge reply chestunaadu",
        "Meeru question cheppinchandi — Pavan available ayinaaka cheptanu",
      ] : [
        "Got your question — Pavan will get back to you when he's free",
        "Noted! I'll make sure Pavan answers this for you",
        "Pavan is busy right now — I'll flag your question for him",
      ];
      return AIResponse(text: _pick(replies), action: AIAction.none,
          data: {'reason': 'question_deferred'});
    }

    // 8. Help request
    if (intent == 'help') {
      final replies = isTelugu ? [
        "Bro — Pavan ippudu busy, em help kavalo cheppinchandi nenu relay chestunaanu",
        "Sare bro sahayam kavali — Pavan ki cheppistanu wait cheyyi",
      ] : [
        "Pavan is unavailable right now — I'll make sure he knows you need help",
        "Got it — I'll flag this for Pavan as soon as he's free",
      ];
      return AIResponse(text: _pick(replies), action: AIAction.none,
          data: {'reason': 'help_request'});
    }

    // 9. Default casual reply (close friend style)
    if (isClose) {
      final replies = isTelugu ? [
        "Haha bro — Pavan ippudu lo undi, tondarge chestunaadu 😄",
        "Ra bro — Pavan busy ga undi wait cheyyi",
        "Sare sare — Pavan message chustunaadu, reply vestunaadu",
        "Lol bro — Pavan available ayinaaka cheptanu 😂",
        "Anthe bro — Pavan ni pampistanu message",
      ] : [
        "Haha — Pavan's busy but I'll pass it along",
        "Got it! Pavan will respond when he can",
        "Lol — noted, I'll tell Pavan 😄",
      ];
      return AIResponse(text: _pick(replies), action: AIAction.none,
          data: {'reason': 'casual_close'});
    }

    // 10. Default — generic polite
    final replies = isTelugu ? [
      "Pavan ippudu available kaadu — message cheppinchanu, tondarge reply chestunaadu",
      "Meeru message received — Pavan ki cheppistanu",
    ] : [
      "Pavan is currently unavailable — I'll make sure he gets your message",
      "Message received! Pavan will get back to you shortly",
    ];
    return AIResponse(text: _pick(replies), action: AIAction.none,
        data: {'reason': 'default'});
  }

  // ═════════════════════════════════════════════════════════
  //  DETECTION HELPERS
  // ═════════════════════════════════════════════════════════

  String _detectLanguage(String text) {
    int teluguCount = 0;
    for (final word in _teluguWords) {
      if (text.contains(word)) teluguCount++;
    }
    // Also check for Telugu unicode characters
    final hasTeluguScript = RegExp(r'[\u0C00-\u0C7F]').hasMatch(text);
    if (hasTeluguScript) return 'telugu';
    if (teluguCount >= 3) return 'telugu';
    if (teluguCount >= 1) return 'mixed';
    return 'english';
  }

  bool _isIdentityQuestion(String text) {
    return _identityTriggers.any((t) => text.contains(t));
  }

  String _detectIntent(String text) {
    if (_angryWords.any((w) => text.contains(w)))    return 'angry';
    if (_loveWords.any((w) => text.contains(w)))     return 'love';
    if (_helpWords.any((w) => text.contains(w)))     return 'help';
    if (_greetingWords.any((w) => text.contains(w))) return 'greeting';
    if (_questionWords.any((w) => text.contains(w))) return 'question';
    return 'casual';
  }

  String _detectSentiment(String text) {
    int pos = _posWords.where((w) => text.contains(w)).length;
    int neg = _negWords.where((w) => text.contains(w)).length;
    if (pos > neg + 1) return 'positive';
    if (neg > pos + 1) return 'negative';
    return 'neutral';
  }

  double _sentimentScore(String text) {
    double score = 0;
    for (final w in _posWords) if (text.contains(w)) score += 0.2;
    for (final w in _negWords) if (text.contains(w)) score -= 0.2;
    return score.clamp(-1.0, 1.0);
  }

  String _detectUrgency(String text) {
    if (_highUrgency.any((w) => text.contains(w)))  return 'high';
    if (_lowUrgency.any((w) => text.contains(w)))   return 'low';
    if (text.contains('?') && text.length < 30)     return 'medium';
    return 'low';
  }

  String _detectFriendType(String sender, String text,
      int conversationCount) {
    // If they use casual Telugu address words → close friend
    final usesCloseTalk = _closeFriendSignals.any((w) => text.contains(w));
    if (usesCloseTalk || conversationCount > 20) return 'close';
    if (conversationCount > 5) return 'normal';
    return 'unknown';
  }

  bool _shouldReply(String intent, String urgency, bool isIdentity) {
    if (isIdentity)         return true;
    if (urgency == 'high')  return true;
    if (intent == 'angry')  return true;
    if (intent == 'help')   return true;
    if (intent == 'greeting') return true;
    return true; // reply to everything by default
  }

  T _pick<T>(List<T> list) => list[_rand.nextInt(list.length)];
}
