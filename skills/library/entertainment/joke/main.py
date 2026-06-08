import random
from skills.utils import success_response, error_response

JOKES = [
    {"category": "programming", "joke": "Why do programmers prefer dark mode? Because light attracts bugs."},
    {"category": "programming", "joke": "What do you call a programmer from Finland? Nerdic."},
    {"category": "programming", "joke": "There are only 10 kinds of people in the world: those who understand binary and those who don't."},
    {"category": "programming", "joke": "Why did the Java developer wear glasses? Because he couldn't C#."},
    {"category": "programming", "joke": "A SQL query walks into a bar, walks up to two tables and asks: 'Can I join you?'"},
    {"category": "programming", "joke": "Why did the programmer go broke? He used up all his cache."},
    {"category": "programming", "joke": "How many programmers does it take to change a light bulb? None, that's a hardware problem."},
    {"category": "programming", "joke": "What's a programmer's favorite hangout place? The Foo Bar."},
    {"category": "programming", "joke": "Why do Python programmers prefer snakes? Because they hate spiders (except web scraping)."},
    {"category": "programming", "joke": "I would tell you a UDP joke, but you might not get it."},
    {"category": "programming", "joke": "A programmer's wife sent him to the store: 'Get a loaf of bread, and if they have eggs, get 12.' He came back with 12 loaves of bread."},
    {"category": "programming", "joke": "Why was the JavaScript developer sad? Because he didn't know how to 'null' his feelings."},
    {"category": "programming", "joke": "What did the router say to the doctor? 'I need a bandwidth-aid.'"},
    {"category": "programming", "joke": "A programmer is a machine that turns caffeine into code."},
    {"category": "programming", "joke": "Why did the developer go to therapy? He had too many unresolved dependencies."},
    {"category": "dad", "joke": "I'm reading a book on anti-gravity. It's impossible to put down."},
    {"category": "dad", "joke": "Why don't eggs tell jokes? They'd crack each other up."},
    {"category": "dad", "joke": "What do you call a fish with no eyes? A fsh."},
    {"category": "dad", "joke": "I used to play piano by ear, but now I use my hands."},
    {"category": "dad", "joke": "Why did the scarecrow win an award? He was outstanding in his field."},
    {"category": "dad", "joke": "What's brown and sticky? A stick."},
    {"category": "dad", "joke": "I'm on a seafood diet. I see food and I eat it."},
    {"category": "dad", "joke": "Why can't you give Elsa a balloon? Because she will let it go."},
    {"category": "dad", "joke": "How does a penguin build its house? Igloos it together."},
    {"category": "dad", "joke": "What do you call fake spaghetti? An impasta."},
    {"category": "dad", "joke": "Why did the math book look so sad? Because it had too many problems."},
    {"category": "dad", "joke": "What do you call a bear with no teeth? A gummy bear."},
    {"category": "dad", "joke": "I only know 25 letters of the alphabet. I don't know y."},
    {"category": "dad", "joke": "How do you make holy water? You boil the hell out of it."},
    {"category": "dad", "joke": "What did the zero say to the eight? Nice belt."},
    {"category": "pun", "joke": "I used to be a baker, but I couldn't make enough dough."},
    {"category": "pun", "joke": "I'm reading a book about mazes. I got lost in it."},
    {"category": "pun", "joke": "The past, present, and future walked into a bar. It was tense."},
    {"category": "pun", "joke": "I would tell a chemistry joke, but I wouldn't get a reaction."},
    {"category": "pun", "joke": "I don't trust stairs. They're always up to something."},
    {"category": "pun", "joke": "Time flies like an arrow. Fruit flies like a banana."},
    {"category": "pun", "joke": "I'm friends with all electricians. We have great connections."},
    {"category": "pun", "joke": "When a clock is hungry it goes back four seconds."},
    {"category": "pun", "joke": "A bicycle can't stand on its own because it's two-tired."},
    {"category": "pun", "joke": "I was struggling to figure out how lightning works, then it struck me."},
    {"category": "pun", "joke": "What do you call a factory that sells generally okay products? A satisfactory."},
    {"category": "pun", "joke": "I could tell a joke about clouds, but it has no silver lining."},
    {"category": "general", "joke": "Why don't scientists trust atoms? Because they make up everything."},
    {"category": "general", "joke": "What do you get when you cross a snowman and a vampire? Frostbite."},
    {"category": "general", "joke": "Why did the bicycle fall over? Because it was two-tired."},
    {"category": "general", "joke": "What do you call a can opener that doesn't work? A can't opener."},
    {"category": "general", "joke": "Why don't skeletons fight each other? They don't have the guts."},
    {"category": "general", "joke": "What do you call someone with no body and no nose? Nobody knows."},
    {"category": "general", "joke": "Why did the coffee file a police report? It got mugged."},
    {"category": "general", "joke": "What's orange and sounds like a parrot? A carrot."},
    {"category": "general", "joke": "Why did the golfer bring two pairs of pants? In case he got a hole in one."},
    {"category": "general", "joke": "I told my wife she was drawing her eyebrows too high. She looked surprised."},
    {"category": "general", "joke": "What's the best thing about Switzerland? I don't know, but the flag is a big plus."},
    {"category": "general", "joke": "How do you catch a squirrel? Climb a tree and act like a nut."},
]

async def joke(params: dict) -> dict:
    category = params.get("category", "").lower()
    pool = JOKES
    if category in ("programming", "dad", "pun", "general"):
        pool = [j for j in JOKES if j["category"] == category]
    if not pool:
        return error_response(f"No jokes found for category '{category}'")
    chosen = random.choice(pool)
    return success_response({"category": chosen["category"], "joke": chosen["joke"]})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
