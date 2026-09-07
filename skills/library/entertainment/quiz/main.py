# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
from skills.utils import success_response, error_response

QUESTIONS = [
    {"topic": "science", "difficulty": "easy", "question": "What is the chemical symbol for water?", "choices": ["H2O", "CO2", "NaCl", "O2"], "answer": "H2O"},
    {"topic": "science", "difficulty": "easy", "question": "What planet is known as the Red Planet?", "choices": ["Mars", "Venus", "Jupiter", "Saturn"], "answer": "Mars"},
    {"topic": "science", "difficulty": "easy", "question": "How many bones are in the adult human body?", "choices": ["206", "205", "207", "208"], "answer": "206"},
    {"topic": "science", "difficulty": "easy", "question": "What gas do plants absorb from the atmosphere?", "choices": ["Carbon dioxide", "Oxygen", "Nitrogen", "Hydrogen"], "answer": "Carbon dioxide"},
    {"topic": "science", "difficulty": "easy", "question": "What is the hardest natural substance?", "choices": ["Diamond", "Gold", "Iron", "Platinum"], "answer": "Diamond"},
    {"topic": "science", "difficulty": "medium", "question": "What is the speed of light in vacuum (approx)?", "choices": ["3×10⁸ m/s", "3×10⁶ m/s", "3×10¹⁰ m/s", "3×10⁵ m/s"], "answer": "3×10⁸ m/s"},
    {"topic": "science", "difficulty": "medium", "question": "Which element has the atomic number 79?", "choices": ["Gold", "Silver", "Platinum", "Mercury"], "answer": "Gold"},
    {"topic": "science", "difficulty": "medium", "question": "What is the powerhouse of the cell?", "choices": ["Mitochondria", "Nucleus", "Ribosome", "Golgi apparatus"], "answer": "Mitochondria"},
    {"topic": "science", "difficulty": "medium", "question": "What type of bond shares electrons between atoms?", "choices": ["Covalent", "Ionic", "Metallic", "Hydrogen"], "answer": "Covalent"},
    {"topic": "science", "difficulty": "medium", "question": "Which planet has the most moons?", "choices": ["Saturn", "Jupiter", "Uranus", "Neptune"], "answer": "Saturn"},
    {"topic": "science", "difficulty": "hard", "question": "What is the half-life of Carbon-14?", "choices": ["5730 years", "4500 years", "2500 years", "10000 years"], "answer": "5730 years"},
    {"topic": "science", "difficulty": "hard", "question": "What is the Chandrasekhar limit (in solar masses)?", "choices": ["1.44", "2.5", "3.0", "0.8"], "answer": "1.44"},
    {"topic": "science", "difficulty": "hard", "question": "Which particle is responsible for mediating the electromagnetic force?", "choices": ["Photon", "Gluon", "W boson", "Graviton"], "answer": "Photon"},
    {"topic": "science", "difficulty": "hard", "question": "What is the chemical formula of ozone?", "choices": ["O3", "O2", "O", "CO2"], "answer": "O3"},
    {"topic": "science", "difficulty": "hard", "question": "What enzyme unwinds DNA during replication?", "choices": ["Helicase", "Ligase", "Polymerase", "Primase"], "answer": "Helicase"},
    {"topic": "history", "difficulty": "easy", "question": "In which year did World War II end?", "choices": ["1945", "1944", "1946", "1943"], "answer": "1945"},
    {"topic": "history", "difficulty": "easy", "question": "Who was the first President of the United States?", "choices": ["George Washington", "Thomas Jefferson", "Abraham Lincoln", "John Adams"], "answer": "George Washington"},
    {"topic": "history", "difficulty": "easy", "question": "The ancient city of Rome was built on how many hills?", "choices": ["Seven", "Five", "Three", "Nine"], "answer": "Seven"},
    {"topic": "history", "difficulty": "easy", "question": "What civilization built Machu Picchu?", "choices": ["Inca", "Maya", "Aztec", "Olmec"], "answer": "Inca"},
    {"topic": "history", "difficulty": "easy", "question": "Who discovered America in 1492?", "choices": ["Christopher Columbus", "Vasco da Gama", "Ferdinand Magellan", "Amerigo Vespucci"], "answer": "Christopher Columbus"},
    {"topic": "history", "difficulty": "medium", "question": "What was the name of the first manned spacecraft to land on the Moon?", "choices": ["Apollo 11", "Apollo 13", "Apollo 8", "Apollo 1"], "answer": "Apollo 11"},
    {"topic": "history", "difficulty": "medium", "question": "Which empire was ruled by Genghis Khan?", "choices": ["Mongol Empire", "Roman Empire", "Ottoman Empire", "Persian Empire"], "answer": "Mongol Empire"},
    {"topic": "history", "difficulty": "medium", "question": "The French Revolution began in which year?", "choices": ["1789", "1776", "1799", "1804"], "answer": "1789"},
    {"topic": "history", "difficulty": "medium", "question": "What was the longest war in history?", "choices": ["The Hundred Years' War", "The Vietnam War", "The Cold War", "The Peloponnesian War"], "answer": "The Hundred Years' War"},
    {"topic": "history", "difficulty": "medium", "question": "Who was the last pharaoh of Egypt?", "choices": ["Cleopatra VII", "Nefertiti", "Hatshepsut", "Ramesses II"], "answer": "Cleopatra VII"},
    {"topic": "history", "difficulty": "hard", "question": "The Treaty of Westphalia ended which war?", "choices": ["Thirty Years' War", "Seven Years' War", "Hundred Years' War", "War of the Roses"], "answer": "Thirty Years' War"},
    {"topic": "history", "difficulty": "hard", "question": "Who was the Byzantine emperor during the fall of Constantinople in 1453?", "choices": ["Constantine XI", "Justinian I", "Basil II", "Alexios I"], "answer": "Constantine XI"},
    {"topic": "history", "difficulty": "hard", "question": "What was the name of the Aztec capital?", "choices": ["Tenochtitlan", "Cuzco", "Chichen Itza", "Teotihuacan"], "answer": "Tenochtitlan"},
    {"topic": "history", "difficulty": "hard", "question": "The Punic Wars were fought between Rome and which city?", "choices": ["Carthage", "Athens", "Corinth", "Alexandria"], "answer": "Carthage"},
    {"topic": "history", "difficulty": "hard", "question": "Which document signed in 1215 limited the power of the English king?", "choices": ["Magna Carta", "Bill of Rights", "Petition of Right", "Habeas Corpus"], "answer": "Magna Carta"},
    {"topic": "geography", "difficulty": "easy", "question": "What is the largest continent?", "choices": ["Asia", "Africa", "North America", "Europe"], "answer": "Asia"},
    {"topic": "geography", "difficulty": "easy", "question": "What is the longest river in the world?", "choices": ["Nile", "Amazon", "Mississippi", "Yangtze"], "answer": "Nile"},
    {"topic": "geography", "difficulty": "easy", "question": "Which country has the largest population?", "choices": ["India", "China", "USA", "Indonesia"], "answer": "India"},
    {"topic": "geography", "difficulty": "easy", "question": "What is the capital of Japan?", "choices": ["Tokyo", "Seoul", "Beijing", "Bangkok"], "answer": "Tokyo"},
    {"topic": "geography", "difficulty": "easy", "question": "Which desert is the largest hot desert?", "choices": ["Sahara", "Gobi", "Kalahari", "Arabian"], "answer": "Sahara"},
    {"topic": "geography", "difficulty": "medium", "question": "How many countries are in Africa?", "choices": ["54", "48", "56", "50"], "answer": "54"},
    {"topic": "geography", "difficulty": "medium", "question": "What is the deepest ocean trench?", "choices": ["Mariana Trench", "Tonga Trench", "Philippine Trench", "Java Trench"], "answer": "Mariana Trench"},
    {"topic": "geography", "difficulty": "medium", "question": "Which strait separates Europe from Africa?", "choices": ["Gibraltar", "Bosphorus", "Dardanelles", "Malacca"], "answer": "Gibraltar"},
    {"topic": "geography", "difficulty": "medium", "question": "What is the smallest country in the world?", "choices": ["Vatican City", "Monaco", "San Marino", "Liechtenstein"], "answer": "Vatican City"},
    {"topic": "geography", "difficulty": "medium", "question": "Which mountain is the tallest in the world above sea level?", "choices": ["Mount Everest", "K2", "Kangchenjunga", "Lhotse"], "answer": "Mount Everest"},
    {"topic": "geography", "difficulty": "hard", "question": "What is the only country to border both the Atlantic and Indian Oceans?", "choices": ["South Africa", "Argentina", "Chile", "Australia"], "answer": "South Africa"},
    {"topic": "geography", "difficulty": "hard", "question": "What is the capital of Kyrgyzstan?", "choices": ["Bishkek", "Tashkent", "Astana", "Dushanbe"], "answer": "Bishkek"},
    {"topic": "geography", "difficulty": "hard", "question": "Which lake is the deepest in the world?", "choices": ["Baikal", "Tanganyika", "Caspian Sea", "Superior"], "answer": "Baikal"},
    {"topic": "geography", "difficulty": "hard", "question": "The Gobi Desert spans which two countries?", "choices": ["Mongolia and China", "India and Pakistan", "Kazakhstan and Uzbekistan", "Iran and Turkmenistan"], "answer": "Mongolia and China"},
    {"topic": "geography", "difficulty": "hard", "question": "Which river flows through Baghdad?", "choices": ["Tigris", "Euphrates", "Nile", "Jordan"], "answer": "Tigris"},
    {"topic": "tech", "difficulty": "easy", "question": "What does CPU stand for?", "choices": ["Central Processing Unit", "Computer Personal Unit", "Central Program Utility", "Core Processing Unit"], "answer": "Central Processing Unit"},
    {"topic": "tech", "difficulty": "easy", "question": "Who founded Microsoft?", "choices": ["Bill Gates", "Steve Jobs", "Mark Zuckerberg", "Larry Page"], "answer": "Bill Gates"},
    {"topic": "tech", "difficulty": "easy", "question": "What does HTML stand for?", "choices": ["HyperText Markup Language", "High Tech Modern Language", "Hyper Transfer Markup Language", "Home Tool Markup Language"], "answer": "HyperText Markup Language"},
    {"topic": "tech", "difficulty": "easy", "question": "What is the most popular programming language in 2024?", "choices": ["Python", "JavaScript", "Java", "C++"], "answer": "Python"},
    {"topic": "tech", "difficulty": "easy", "question": "What does 'www' stand for?", "choices": ["World Wide Web", "World Wide Work", "Web Wide World", "World Web Wide"], "answer": "World Wide Web"},
    {"topic": "tech", "difficulty": "medium", "question": "What year was the first iPhone released?", "choices": ["2007", "2008", "2006", "2009"], "answer": "2007"},
    {"topic": "tech", "difficulty": "medium", "question": "What does API stand for?", "choices": ["Application Programming Interface", "Application Process Integration", "Automated Program Interface", "Advanced Platform Integration"], "answer": "Application Programming Interface"},
    {"topic": "tech", "difficulty": "medium", "question": "Which company developed the Android operating system?", "choices": ["Google", "Apple", "Microsoft", "Samsung"], "answer": "Google"},
    {"topic": "tech", "difficulty": "medium", "question": "What type of language is Python?", "choices": ["Interpreted", "Compiled", "Assembly", "Machine"], "answer": "Interpreted"},
    {"topic": "tech", "difficulty": "medium", "question": "What does SQL stand for?", "choices": ["Structured Query Language", "Simple Query Language", "Standard Query Logic", "Sequential Query Language"], "answer": "Structured Query Language"},
    {"topic": "tech", "difficulty": "hard", "question": "What is the time complexity of binary search?", "choices": ["O(log n)", "O(n)", "O(n²)", "O(1)"], "answer": "O(log n)"},
    {"topic": "tech", "difficulty": "hard", "question": "Which protocol is used for secure web browsing?", "choices": ["HTTPS", "HTTP", "FTP", "SSH"], "answer": "HTTPS"},
    {"topic": "tech", "difficulty": "hard", "question": "What does ACID stand for in databases?", "choices": ["Atomicity, Consistency, Isolation, Durability", "Automatic, Consistent, Isolated, Durable", "Atomic, Complete, Isolated, Durable", "Access, Control, Isolation, Data"], "answer": "Atomicity, Consistency, Isolation, Durability"},
    {"topic": "tech", "difficulty": "hard", "question": "What is the maximum value of a 32-bit unsigned integer?", "choices": ["4294967295", "2147483647", "65535", "16777215"], "answer": "4294967295"},
    {"topic": "tech", "difficulty": "hard", "question": "Which sorting algorithm has the best average-case time complexity?", "choices": ["Quicksort", "Bubble sort", "Insertion sort", "Selection sort"], "answer": "Quicksort"},
    {"topic": "general", "difficulty": "easy", "question": "What color are emeralds?", "choices": ["Green", "Red", "Blue", "Yellow"], "answer": "Green"},
    {"topic": "general", "difficulty": "easy", "question": "How many days are in a leap year?", "choices": ["366", "365", "364", "360"], "answer": "366"},
    {"topic": "general", "difficulty": "easy", "question": "What is the opposite of 'hot'?", "choices": ["Cold", "Warm", "Cool", "Icy"], "answer": "Cold"},
    {"topic": "general", "difficulty": "easy", "question": "Which animal is known as the 'King of the Jungle'?", "choices": ["Lion", "Tiger", "Elephant", "Gorilla"], "answer": "Lion"},
    {"topic": "general", "difficulty": "easy", "question": "How many legs does a spider have?", "choices": ["8", "6", "10", "4"], "answer": "8"},
    {"topic": "general", "difficulty": "medium", "question": "What is the most played board game in the world?", "choices": ["Chess", "Monopoly", "Checkers", "Scrabble"], "answer": "Chess"},
    {"topic": "general", "difficulty": "medium", "question": "Which language has the most native speakers?", "choices": ["Mandarin Chinese", "English", "Spanish", "Hindi"], "answer": "Mandarin Chinese"},
    {"topic": "general", "difficulty": "medium", "question": "What is the boiling point of water in Celsius?", "choices": ["100°C", "90°C", "110°C", "80°C"], "answer": "100°C"},
    {"topic": "general", "difficulty": "medium", "question": "How many bones are in the human hand?", "choices": ["27", "26", "28", "25"], "answer": "27"},
    {"topic": "general", "difficulty": "medium", "question": "Which organ pumps blood in the human body?", "choices": ["Heart", "Liver", "Lungs", "Brain"], "answer": "Heart"},
    {"topic": "general", "difficulty": "hard", "question": "What is the rarest blood type?", "choices": ["AB negative", "O negative", "B negative", "A negative"], "answer": "AB negative"},
    {"topic": "general", "difficulty": "hard", "question": "How many languages are estimated to exist in the world?", "choices": ["About 7000", "About 4000", "About 10000", "About 5000"], "answer": "About 7000"},
    {"topic": "general", "difficulty": "hard", "question": "What is the most abundant element in the Earth's crust?", "choices": ["Oxygen", "Silicon", "Aluminum", "Iron"], "answer": "Oxygen"},
    {"topic": "general", "difficulty": "hard", "question": "Which country invented paper?", "choices": ["China", "India", "Egypt", "Greece"], "answer": "China"},
    {"topic": "general", "difficulty": "hard", "question": "What is the tallest breed of dog?", "choices": ["Irish Wolfhound", "Great Dane", "Scottish Deerhound", "Mastiff"], "answer": "Irish Wolfhound"},
    {"topic": "science", "difficulty": "easy", "question": "What force keeps us on the ground?", "choices": ["Gravity", "Friction", "Magnetism", "Inertia"], "answer": "Gravity"},
    {"topic": "science", "difficulty": "easy", "question": "What is the largest organ in the human body?", "choices": ["Skin", "Liver", "Lungs", "Heart"], "answer": "Skin"},
    {"topic": "history", "difficulty": "easy", "question": "In which country were the first Olympic Games held?", "choices": ["Greece", "Italy", "Egypt", "Turkey"], "answer": "Greece"},
    {"topic": "history", "difficulty": "easy", "question": "Who wrote the 'I Have a Dream' speech?", "choices": ["Martin Luther King Jr.", "Malcolm X", "Nelson Mandela", "Mahatma Gandhi"], "answer": "Martin Luther King Jr."},
    {"topic": "geography", "difficulty": "easy", "question": "What is the only country that is also a continent?", "choices": ["Australia", "India", "Russia", "China"], "answer": "Australia"},
    {"topic": "geography", "difficulty": "easy", "question": "Which ocean is the largest?", "choices": ["Pacific", "Atlantic", "Indian", "Arctic"], "answer": "Pacific"},
    {"topic": "tech", "difficulty": "easy", "question": "What does 'PDF' stand for?", "choices": ["Portable Document Format", "Personal Document File", "Printable Document Format", "Public Document File"], "answer": "Portable Document Format"},
    {"topic": "tech", "difficulty": "easy", "question": "What is the main function of a router?", "choices": ["Route data between networks", "Store data", "Provide power", "Display graphics"], "answer": "Route data between networks"},
    {"topic": "general", "difficulty": "easy", "question": "What color is the sky on a clear day?", "choices": ["Blue", "White", "Gray", "Green"], "answer": "Blue"},
    {"topic": "general", "difficulty": "easy", "question": "How many months have 31 days?", "choices": ["7", "6", "5", "8"], "answer": "7"},
    {"topic": "science", "difficulty": "medium", "question": "What is the pH of pure water?", "choices": ["7", "1", "14", "10"], "answer": "7"},
    {"topic": "history", "difficulty": "medium", "question": "What wall divided Berlin?", "choices": ["Berlin Wall", "Great Wall", "Hadrian's Wall", "Western Wall"], "answer": "Berlin Wall"},
    {"topic": "geography", "difficulty": "medium", "question": "Which country has the most time zones?", "choices": ["France", "Russia", "USA", "China"], "answer": "France"},
    {"topic": "tech", "difficulty": "medium", "question": "What does LAN stand for?", "choices": ["Local Area Network", "Large Area Network", "Logical Area Network", "Linear Access Network"], "answer": "Local Area Network"},
    {"topic": "general", "difficulty": "medium", "question": "What is the most popular sport in the world?", "choices": ["Soccer", "Cricket", "Basketball", "Tennis"], "answer": "Soccer"},
    {"topic": "science", "difficulty": "hard", "question": "What is Schrodinger's Cat?", "choices": ["A thought experiment in quantum mechanics", "A real experiment with a cat", "A cat breed", "A physics law"], "answer": "A thought experiment in quantum mechanics"},
    {"topic": "history", "difficulty": "hard", "question": "What was the name of Napoleon's first wife?", "choices": ["Joséphine de Beauharnais", "Marie Antoinette", "Marie Louise", "Catherine de Medici"], "answer": "Joséphine de Beauharnais"},
    {"topic": "tech", "difficulty": "hard", "question": "What is the CAP theorem about?", "choices": ["Consistency, Availability, Partition tolerance", "CPU, Algorithm, Performance", "Code, Access, Protocol", "Caching, API, Processing"], "answer": "Consistency, Availability, Partition tolerance"},
]

async def quiz(params: dict) -> dict:
    topic = params.get("topic", "").lower()
    difficulty = params.get("difficulty", "").lower()
    count = params.get("count", 5)
    if not isinstance(count, int) or count < 1:
        count = 5
    pool = QUESTIONS
    valid_topics = {"science", "history", "geography", "tech", "general"}
    valid_difficulties = {"easy", "medium", "hard"}
    if topic in valid_topics:
        pool = [q for q in pool if q["topic"] == topic]
    if difficulty in valid_difficulties:
        pool = [q for q in pool if q["difficulty"] == difficulty]
    if not pool:
        return error_response("No questions found for the given criteria")
    selected = random.sample(pool, min(count, len(pool)))
    return success_response({"questions": selected, "total": len(selected)})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
