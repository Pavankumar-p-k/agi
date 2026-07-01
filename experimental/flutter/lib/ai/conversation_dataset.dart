class ConvPattern {
  final String intent;
  final List<String> triggers;
  final List<String> replies;

  const ConvPattern({
    required this.intent,
    required this.triggers,
    required this.replies,
  });
}

class ConversationDataset {
  static final List<ConvPattern> patterns = <ConvPattern>[
    const ConvPattern(
      intent: 'greeting',
      triggers: ['hi', 'hello', 'hey', 'hii', 'namaste', 'namasthe', 'yo'],
      replies: [
        'Hey. How can I help?',
        'Hi bro, what do you need?',
        'Hello. Tell me what you want to do.',
      ],
    ),
    const ConvPattern(
      intent: 'how_are_you',
      triggers: ['how are you', 'how r u', 'hru', 'ela unnav', 'bagunnava'],
      replies: [
        'Doing well. How about you?',
        'All good here. What is up?',
        'Baagunnanu bro. Nuvvu ela unnav?',
      ],
    ),
    const ConvPattern(
      intent: 'where_is_pavan',
      triggers: [
        'where is pavan',
        'pavan ekkada',
        'is pavan there',
        'pavan available',
      ],
      replies: [
        'Pavan is unavailable right now. I can relay your message.',
        'Pavan is busy at the moment. Tell me what you want to pass on.',
      ],
    ),
    const ConvPattern(
      intent: 'when_available',
      triggers: [
        'when will he reply',
        'when available',
        'epudu reply',
        'reply epudu',
      ],
      replies: [
        'He should reply once he is free. I have noted your message.',
        'Please give him a little time. I will make sure he sees it.',
      ],
    ),
    const ConvPattern(
      intent: 'compliment',
      triggers: ['good job', 'great', 'awesome', 'super bro', 'helpful'],
      replies: [
        'Thanks. Glad that helped.',
        'Appreciate it. I am here if you need more.',
      ],
    ),
    const ConvPattern(
      intent: 'thank_you',
      triggers: ['thanks', 'thank you', 'thx', 'tq', 'dhanyavadalu'],
      replies: [
        'Anytime.',
        'You are welcome.',
        'No problem bro.',
      ],
    ),
    const ConvPattern(
      intent: 'angry',
      triggers: ['angry', 'shut up', 'kopam', 'frustrated', 'leave me alone'],
      replies: [
        'Understood. I will keep it short.',
        'I hear you. Tell me the one thing you need right now.',
      ],
    ),
    const ConvPattern(
      intent: 'sad',
      triggers: ['sad', 'bad day', 'crying', 'depressed', 'baadha'],
      replies: [
        'I am sorry you are dealing with that.',
        'That sounds rough. If you want, say what happened.',
      ],
    ),
    const ConvPattern(
      intent: 'happy_news',
      triggers: ['good news', 'passed', 'done it', 'success', 'happy'],
      replies: [
        'That is good news.',
        'Nice. Well done.',
        'Super bro, that sounds great.',
      ],
    ),
    const ConvPattern(
      intent: 'asking_for_help',
      triggers: ['help', 'can you help', 'assist', 'support', 'help kavali'],
      replies: [
        'Yes. Tell me the exact task.',
        'I can help. Be specific and I will handle it.',
      ],
    ),
    const ConvPattern(
      intent: 'bored',
      triggers: ['bored', 'boring', 'em cheyali', 'nothing to do'],
      replies: [
        'Try a short walk, music, or a focused 10 minute task.',
        'If you want, I can help you set a reminder or note for something useful.',
      ],
    ),
    const ConvPattern(
      intent: 'good_morning',
      triggers: ['good morning', 'morning', 'subhodayam'],
      replies: [
        'Good morning.',
        'Morning. Ready when you are.',
      ],
    ),
    const ConvPattern(
      intent: 'good_night',
      triggers: ['good night', 'night', 'padukunta', 'sleep now'],
      replies: [
        'Good night.',
        'Sleep well.',
      ],
    ),
    const ConvPattern(
      intent: 'food_talk',
      triggers: ['food', 'what did you eat', 'em tinnav', 'lunch', 'dinner'],
      replies: [
        'Nothing to report there, but I can help you plan something.',
        'Food talk noted. Want me to save a grocery or meal reminder?',
      ],
    ),
    const ConvPattern(
      intent: 'study_work',
      triggers: ['study', 'work', 'busy', 'office', 'exam'],
      replies: [
        'Focus first. I can hold reminders and notes for you.',
        'Understood. Tell me if you want a reminder or quick note saved.',
      ],
    ),
    const ConvPattern(
      intent: 'love_affection',
      triggers: ['love you', 'miss you', 'luv u', 'miss u'],
      replies: [
        'Message received.',
        'Noted.',
      ],
    ),
  ];

  static const Map<String, List<String>> emojiReplies = <String, List<String>>{
    ':)': ['Nice.', 'Good to see that.'],
    ':(': ['I am here if you want to talk.'],
    '😀': ['Good mood noted.'],
    '😂': ['Looks like that was funny.'],
    '❤️': ['Message received.'],
    '👍': ['Understood.'],
    '🙏': ['Anytime.'],
    '🔥': ['That looks strong.'],
  };
}
