// lib/ai/expanded_dataset.dart
// ═══════════════════════════════════════════════════════════════════
//  JARVIS EXPANDED CONVERSATION DATASET — ULTIMATE
//  3x conversation patterns + natural talking for auto-reply
//  Telugu · English · Tenglish (mixed)
//  Self-learning integrates feedback here for continuous improvement
// ═══════════════════════════════════════════════════════════════════

class ExpandedDataset {

  // ── Natural greeting variants ──────────────────────────────

  static const List<String> greetingsTelugu = [
    'Namasthe bro!',
    'Enti ra, ela unnav?',
    'Heyy da, cheppinchandi em vishayam',
    'Orey! Long time — ela unnav?',
    'Ra bro! Em chestunnav ippudu?',
    'Heyy! Ela unnav meeru?',
    'Namaskar anna! Em vishayam?',
    'Sup bro! Ela nuvu?',
    'Oy anna! Meeru ela unnaru?',
    'Hellooo da! Cheppinchandi bhayya',
  ];

  static const List<String> greetingsEnglish = [
    'Hey! What\'s up?',
    'Hello! How can I help?',
    'Yo! What\'s going on?',
    'Hi there! What\'s new?',
    'Hey hey! Long time — how\'ve you been?',
    'What\'s up buddy!',
    'Heyy! How are things?',
    'Hello there! Speak up',
    'Sup! What\'s the news?',
    'Hi buddy! What\'s happening?',
  ];

  // ── "How are you" natural responses ────────────────────────

  static const List<String> howAreYouTelugu = [
    'Baagunnanu bro! Nuvvu ela unnav?',
    'Super ga unnanu — nuvve ela?',
    'Chala bagunnanu! Em chestunnav ippudu?',
    'All good da — busy ga unnanu. Nuvvela?',
    'Baagunnanu anna! Nuvvu ok va?',
    'Fine bro — just keeping busy. Nuvvela?',
    'Manchi ga unnanu — life okela undi. Nuvvela meeru?',
    'Anthe bro — regular ga unnanu. Em chestunnav nuvvu?',
    'Chill ga unnanu bro — nuvvu ela?',
    'Super bro! Nuvvu enti chestunnav?',
  ];

  static const List<String> howAreYouEnglish = [
    'Doing great! How about you?',
    'All good here! What about yourself?',
    'Pretty good! What\'s up with you?',
    'Can\'t complain — how are you?',
    'Doing well! You good?',
    'Great! What\'s new with you?',
    'Fantastic! How\'ve you been?',
    'Living the dream! You?',
    'All good buddy! How\'s life treating you?',
    'Pretty solid! What\'s with you?',
  ];

  // ── "Where is Pavan" contextual responses ──────────────────

  static const List<String> whereIsPavanTelugu = [
    'Pavan ippudu busy ga unnaru — meeru message cheppinchandi nenu relay chestunaanu',
    'Atanu ippudu available kaadu — ee message tondarge chestunaanu pakka',
    'Pavan occupied ga unnadu — kani nenu sure nenu relay chestunaanu',
    'Ippudu atanu call lo unnadu kaastaant wait cheyyi',
    'Work lo occupied ga unnaru — meeru cheppindi nenu definitely pass chestunaanu',
    'Ekkado busy ga unnadu — message cheppinchandi, tondarge vastunaadu',
    'Pavan ippudu lo ledu kani available ayinaaka reply chestunaadu pakka',
    'Atanu ippudu occupied ga unnaru — kani oka message cheppistanu',
    'Currently available kaadu — kani nenu sure nenu message pass chestunaanu',
    'Ekkado engaged ga unnadu — meeru cheppindi nenu pass chestunaanu',
  ];

  static const List<String> whereIsPavanEnglish = [
    'Pavan is currently tied up — I\'ll make sure he gets your message ASAP',
    'He\'s not available right now — but I\'ll relay this immediately',
    'He\'s occupied at the moment — your message is noted',
    'Pavan is unavailable — I\'m taking down your message now',
    'Currently not reachable — but I\'ll pass it along',
    'He\'s busy — I\'ll make sure he sees this',
    'Not around right now — I\'ll relay it to him',
    'He\'s occupied — I\'ll take note of your message',
    'Pavan is currently busy — message noted',
    'Not reachable at the moment — I\'ll inform him',
  ];

  // ── "When will he reply" responses ────────────────────────

  static const List<String> whenReplyTelugu = [
    'Kaastaant wait cheyyi bro — tondarge reply chestunaadu pakka',
    'Oka ganta lo vastunaadu bro — wait cheyyi',
    'Busy ga unnadu kani kaasta kotha minutes lo reply vestunaadu',
    'Tondarge free ayinaaka reply vestunaadu — patience cheyyi bro',
    'Kaasta wait cheyyi — atanu occupied kani message cheppistanu',
    'Nenu message cheppistanu — tondarge reply vastunaadu pakka',
    'Oka 30 minutes lo free ayinaaka reply vestunaadu',
    'Wait cheyyi bro — kaasta time lo reply vastunaadu',
    'Tondarge reply vestunaadu — patience buddy',
    'Nenu reminder set chestunaanu — tondarge vastunaadu',
  ];

  static const List<String> whenReplyEnglish = [
    'Give him a minute — he\'ll reply as soon as he\'s free',
    'He should get back to you shortly',
    'He\'ll reply when he gets a chance',
    'Just a bit of patience — he\'s on it',
    'He\'s making a note of this now',
    'Shouldn\'t take long — he\'ll reach out',
    'He\'ll reply in a bit — sit tight',
    'Message noted — he\'ll get back soon',
    'Give him some time — reply is incoming',
    'He\'s noted this — answer coming up',
  ];

  // ── "Compliments" responses ────────────────────────────────

  static const List<String> complimentsTelugu = [
    'Thanks bro! Ala cheppinanduku — meeru very kind ga unnaru',
    'Haha tankss — appreciate this anna! Nuvvu very nice person',
    'Wow thanks bro — mean theesav. Nuvvu great person',
    'Appreciation bro — meeru very supportive person',
    'Thankss anna! Meeru super ga unnaru',
    'Nice of you to say! Appreciate it',
    'Thanks meeru kotti — nuvvu chaala good person',
    'Haha thankss bro — nuvvu very supportive',
    'Appreciate it anna — means a lot',
    'Thannkks anna! Nuvvu super person',
  ];

  static const List<String> complimentsEnglish = [
    'Thanks so much! Really appreciate it',
    'You\'re very kind — thanks for that',
    'I\'m flattered — thank you!',
    'You\'re too kind — I appreciate it',
    'Thanks buddy — means a lot',
    'That\'s very nice of you — thanks!',
    'Appreciate the kind words!',
    'You\'re awesome — thanks for saying that',
    'Really grateful for that — thanks!',
    'That made my day — thank you!',
  ];

  // ── "Thank you" natural responses ──────────────────────────

  static const List<String> thankYouTelugu = [
    'Cheppinanduku welcome bro! Anytime help chestanu',
    'Welcome anna! Nenu always available',
    'pleasure bro! Anytime udyogamga help chestunaanu',
    'Welcome meeru! Help chestanu anytime',
    'Thankss cheppinanduku! Nenu always at service',
    'pleasure bro — anytime chestunaanu help',
    'Welcome anna! Nenu here to help',
    'No problem bro — anytime chestanu',
    'pleasure anna — help chestanu anytime',
    'Welcome meeru — nenu always available',
  ];

  static const List<String> thankYouEnglish = [
    'Anytime! Happy to help',
    'No problem buddy — that\'s what I\'m here for',
    'My pleasure! Always here to help',
    'Glad I could help!',
    'No biggie — help anytime you need',
    'Happy to assist — just ask',
    'That\'s what friends are for!',
    'No prob — hit me up anytime',
    'Always happy to help',
    'Glad that worked out!',
  ];

  // ── "Angry/Frustrated" empathetic responses ────────────────

  static const List<String> angryTelugu = [
    'Oka paap meeru — apologies nenu understand kopam. Chill ga cheyyi bro',
    'Sorry to hear that — deepa paap. Meeru relax cheyyi anna',
    'Apologies meeru — frustration okkate telusidhi. Chill ga',
    'Sorry bro — I get it. Paap appudipinche — relax cheyyi anna',
    'Meeru chala disappointed ga unnaru — apologies. Chill bro',
    'Frustration mandhidhi — sorry. Relax cheyyi anna',
    'Oka paap — meeru ok ayyi come back. Nenu help chestanu',
    'Sorry nenu understand — deepa irritation telusidhi. Chill meeru',
    'I get your frustration — apologies bro. Relax anna',
    'Sorry meeru disappointed — chill ga nenu help chestanu',
  ];

  static const List<String> angryEnglish = [
    'I hear you — sorry about that. Chill out buddy',
    'That\'s frustrating — apologies. Take a breath',
    'I get it — hang in there',
    'Sorry to hear that — frustrating stuff. Relax',
    'Sounds rough — apologies. Don\'t stress',
    'That\'s annoying — sorry about it. Chill',
    'I understand — sorry. Cool off a bit',
    'Hate that for you — hang tight',
    'That\'s rough — apologies. Relax buddy',
    'Sorry mate — take a break, recharge',
  ];

  // ── "Sad" empathetic responses ─────────────────────────────

  static const List<String> sadTelugu = [
    'Paap meeru — apologies thelsidhi sadness. Hang in there anna',
    'Sorry to hear — chala baadha telusidhi. Meeru ok ayyi vacchandi',
    'Paap meeru — depression telusidhi. Oka time lo velli better avutondi',
    'Sorrow telusidhi — sorry meeru. Strength choopinchandi anna',
    'Bad phase nunchi velli better avutondi — hang there',
    'Sadness telusidhi — apologies. Meeru strong unmandi anna',
    'Paap meeru — better days vastunayi pakka',
    'Oka phase matram — strength choopinchandi',
    'Sorry you\'re sad — things improve eventually',
    'Tough times — but you\'ll come through',
  ];

  static const List<String> sadEnglish = [
    'Sorry to hear that — things will get better',
    'That\'s rough — hang in there',
    'I\'m sorry — this too shall pass',
    'Tough times don\'t last — stay strong',
    'You\'ll come through this — stay positive',
    'Better days ahead — hold on',
    'I feel for you — don\'t lose hope',
    'Rough patch here — but you\'ll bounce back',
    'Hang in there — this gets better',
    'Sorry to hear — stay strong',
  ];

  // ── "Happy news" celebratory responses ──────────────────────

  static const List<String> happyTelugu = [
    'Wow! Celebrate bro — chala super! Proud of you anna',
    'Yesss! Thats amazing bro — celebrate cheseskonu!',
    'Wow meeru — chala bagunnav! Congratulations anna',
    'Super bro — celebrate time! Proud unnanu',
    'Excellent! Chala good news — congrats anna',
    'Wow! Amazing bro — celebrate time!',
    'That\'s fantastic bro — super proud',
    'Yay! Chala happy bro — congrats!',
    'Amazing bro — celebrate pakka!',
    'Super news bro — so happy for you!',
  ];

  static const List<String> happyEnglish = [
    'That\'s fantastic! Congrats! 🎉',
    'Yay! So happy for you!',
    'That\'s amazing — celebrate it!',
    'Excellent news — well done!',
    'Love that for you — congrats!',
    'You\'re killing it — so proud!',
    'That\'s awesome — celebrate buddy!',
    'Congrats mate — deserved it!',
    'Yes! That\'s great! Well done!',
    'So happy to hear — congrats!',
  ];

  // ── "Asking for help" helpful responses ────────────────────

  static const List<String> helpTelugu = [
    'Ofcourse bro — help chestanu pakka. Cheppinchandi em help kavali',
    'Sure anna — always here. Em help kavalo cheppandi',
    'Pakka bro — cheppinchandi. Nenu help chestanu definitely',
    'Help chestanu anna — details cheppandi',
    'Sure bro — em help kavali speak up',
    'Pakka meeru — help ready. Cheppandi em problem',
    'Chestanu bro — anything help chestanu',
    'Sure anna — ready to help. Details cheppandi',
    'Ofcourse bro — say the word nenu there',
    'Help chestanu pakka — speak up anna',
  ];

  static const List<String> helpEnglish = [
    'Of course! What do you need?',
    'Happy to help — what\'s up?',
    'Sure thing! What can I do?',
    'I\'m here — what do you need?',
    'Absolutely — hit me with it',
    'You got it — what do you need?',
    'Happy to assist — what\'s happening?',
    'Say the word — I\'m here',
    'Sure bro — what\'s the problem?',
    'Got your back — what\'s up?',
  ];

  // ── "Bored" engaging responses ─────────────────────────────

  static const List<String> boredTelugu = [
    'Paap meeru bored ga unnaru — something interesting chestanu',
    'Boredom telusidhi — movie suggest chestanu or game',
    'Bored ga undi — interesting vishayam chadavakattan',
    'Paap meeru — talkback time! Em interesting chestam',
    'Boredom paddhindi — music play chestanu or movie?',
    'Bored unnara anna — chat chestam deeply',
    'Paap — boredom cut chestanu. Interesting vishayam chadavakattan',
    'Em cheyali cheppandi anna — boredom off chestunaanu',
    'Bored ga undi — fun conversation chesam anna',
    'Paap boredom — movie or music chestam?',
  ];

  static const List<String> boredEnglish = [
    'Bored eh? Let\'s chat then',
    'Let me entertain you — what interests you?',
    'Say the word — I\'ll tell you something cool',
    'Boredom — my specialty! What\'s your vibe?',
    'Tired of the usual? Let\'s talk',
    'I can help with that — what\'ll interest you?',
    'Boredom killer mode activated — what\'s up?',
    'Movie? Music? Interesting chat? Pick one',
    'Bored — let\'s fix that. What interests you?',
    'I got you — let\'s make this fun',
  ];

  // ── "Good morning" time-aware responses ────────────────────

  static const List<String> goodMorningTelugu = [
    'Good morning anna! Sleep well ga unnava? Ready for the day?',
    'Suprabatham bro! Fresh ga unnava morning?',
    'Morning anna — fresh ga unnava? Chai ready ga unna?',
    'Good morning — sleep ela undi? New day new goals?',
    'Suprabatham — fresh start time! How you feeling?',
    'Morning bro — day fresh ga start ayya?',
    'Good morning anna — bright ga unnavi morning?',
    'Suprabatham — sleep ela undi anna?',
    'Morning time — ready for the day?',
    'Good morning — fresh start time bro!',
  ];

  static const List<String> goodMorningEnglish = [
    'Good morning! Hope you slept well!',
    'Morning! Rise and shine time!',
    'Good morning — fresh start ahead!',
    'Morning buddy — ready for the day?',
    'Rise and shine! New day, new goals!',
    'Good morning — how\'s the morning treating you?',
    'Morning time! Energy levels?',
    'Good morning — let\'s make it a great day!',
    'Morning! Ready to crush it?',
    'Good morning — coffee time?',
  ];

  // ── "Good night" sleepy responses ──────────────────────────

  static const List<String> goodNightTelugu = [
    'Good night bro! Sleep well anna — tomorrow new day',
    'Raathri subhakankshalu — sweet dreams!',
    'Sleep well anna — good night from Pavan',
    'Night time — peacefully sleep cheyyi',
    'Good night meeru — well rest cheyyi',
    'Sleep tight bro — morning fresh start',
    'Good night anna — sweet dreams',
    'Raathri subhakankshalu — rest well',
    'Night meeru — peaceful ga sleep cheyyi',
    'Good night bro — tomorrow fresh day',
  ];

  static const List<String> goodNightEnglish = [
    'Good night! Sleep well!',
    'Night buddy — rest up for tomorrow',
    'Good night — sweet dreams!',
    'Sleep tight — tomorrow\'s another day',
    'Night mate — get some good rest',
    'Good night — sleep well!',
    'Night time — recharge yourself',
    'Good night — see you tomorrow',
    'Sleep well — take care!',
    'Night — rest easy buddy',
  ];

  // ── "Food talk" casual responses ───────────────────────────

  static const List<String> foodTalkTelugu = [
    'Ah food! Em tinav? Healthy ga tinava?',
    'Food time! Appetite em unnavu? Dinner ready?',
    'Em tinnav bro — hungry ga unnava?',
    'Kitchen ready? What\'s cooking?',
    'Food mode! Tasty something tinava?',
    'Healthy meals tinava? Junk avoid chestunava?',
    'Appetite em unnavu bro?',
    'Food topic — anything special tinnada?',
    'What\'s for dinner bro — hungry?',
    'Food — hungry ga unnava anna?',
  ];

  static const List<String> foodTalkEnglish = [
    'Food talk! What\'re you eating?',
    'Hungry eh? What\'s cooking?',
    'Food time — appetite good?',
    'What\'s your go-to meal buddy?',
    'Eating well? Healthy choices?',
    'Food mood! What sounds good?',
    'Hungry right now? Let\'s talk food',
    'What\'s the meal plan today?',
    'Food — any cravings buddy?',
    'Cooking something? What\'s the vibe?',
  ];

  // ── "Study/Work" supportive responses ──────────────────────

  static const List<String> studyWorkTelugu = [
    'Study mode! Focus cheyyi bro — meeru intelligent person',
    'Work busy — hang in there anna',
    'Study time — dedication show cheyyi',
    'Work hectic ga — strength cheyyi bro',
    'Busy ga unnara anna — strength choopinchandi',
    'Study/work — important phase. Strength anna',
    'Focused work — good bro! Continue cheyyi',
    'Study pressure — chill ga cheseskonu',
    'Work load — strength meeru',
    'Study time — focus cheyyi, success vastunaadu',
  ];

  static const List<String> studyWorkEnglish = [
    'Study time! Focus buddy — you\'ll ace it',
    'Work overload? Hang in there',
    'Studying hard — that\'s the spirit!',
    'Work pressure — but you\'re built for this',
    'Busy phase — stay strong',
    'Study mode activated — go get \'em',
    'Work grind — you\'ve got this',
    'Deadline pressure? You\'re capable',
    'Study crunch — but you\'ll crush it',
    'Work it — success incoming',
  ];

  // ── "Love/Affection" warm responses ────────────────────────

  static const List<String> loveTelugu = [
    'Aww meeru love chestunaru Pavan ki — so sweet!',
    'Affection telusidhi — appreciate it anna',
    'Love meeru chestunaaru — Pavan lucky person',
    'Very sweet — Pavan appreciate chestunaadu',
    'Affection packets — thank you so much!',
    'Love feeling — so warm anna',
    'Aww meeru love — Pavan appreciate chestunaadu pakka',
    'Heart felt — Pavan love meeru chestunaadu',
    'Sweet affection — appreciate this',
    'Love meeru — Pavan feel this warmth',
  ];

  static const List<String> loveEnglish = [
    'That\'s so sweet — Pavan appreciates this',
    'Love you too buddy — keep those vibes going',
    'Affection sent — thank you!',
    'That\'s beautiful — spreading love like this',
    'So warm — thank you for the love',
    'Love felt — Pavan appreciates this',
    'heartfelt — thanks for the good wishes',
    'That\'s the spirit — love that energy',
    'Affection appreciated — spread that love',
    'So sweet — thanks for the warmth',
  ];

  // ── Integration with self-learning ─────────────────────────
  /// Add feedback scores here (1-5 stars)
  static Map<String, double> replyEffectiveness = {};

  /// Record which reply worked best for learning
  static void recordFeedback(String intent, String reply, double score) {
    final key = '$intent:$reply';
    replyEffectiveness[key] = (replyEffectiveness[key] ?? 0 + score) / 2;
  }

  /// Get top-rated reply for intent (self-learning)
  static String? getLearnedBestReply(String intent) {
    String? best;
    double bestScore = 0;
    replyEffectiveness.forEach((key, score) {
      if (key.startsWith('$intent:') && score > bestScore) {
        best = key.split(':').sublist(1).join(':');
        bestScore = score;
      }
    });
    return best;
  }
}
