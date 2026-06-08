import re
from skills.utils import success_response, error_response

FACTS = [
    # Science (20+)
    ("The Earth revolves around the Sun.", "true", "science", ["Heliocentric model (Copernicus, 1543)", "NASA: Earth's orbit"]),
    ("Water boils at 100 degrees Celsius at sea level.", "true", "science", ["Standard atmospheric pressure", "IUPAC definition"]),
    ("Humans have 23 pairs of chromosomes.", "true", "science", ["Human Genome Project", "Genetics textbooks"]),
    ("The speed of light in vacuum is approximately 300,000 km/s.", "true", "science", ["Special relativity (Einstein, 1905)", "NIST reference"]),
    ("DNA is a double helix structure.", "true", "science", ["Watson & Crick (1953)", "Nobel Prize in Physiology/Medicine 1962"]),
    ("The chemical symbol for gold is Au.", "true", "science", ["Periodic table (IUPAC)", "Chemistry textbooks"]),
    ("Photosynthesis converts carbon dioxide into oxygen.", "true", "science", ["Plant physiology research", "Biochemistry textbooks"]),
    ("The human body has 206 bones.", "true", "science", ["Gray's Anatomy", "Medical textbooks"]),
    ("Earth's atmosphere is mostly nitrogen.", "true", "science", ["NASA: Earth's atmosphere composition", "NOAA data"]),
    ("Plate tectonics explains continental drift.", "true", "science", ["Geological Society of America", "Wegener (1912)"]),
    ("The sun is a star.", "true", "science", ["Astronomical classification", "IAU definitions"]),
    ("Electrons are negatively charged particles.", "true", "science", ["Quantum mechanics", "Standard Model of physics"]),
    ("Gravity is one of the four fundamental forces.", "true", "science", ["General relativity (Einstein, 1915)", "Standard Model"]),
    ("The Great Wall of China is visible from space with the naked eye.", "false", "science", ["NASA debunked this myth", "Chinese astronaut Yang Liwei confirmed it is not visible"]),
    ("Humans only use 10% of their brain.", "false", "science", ["Neuroimaging studies show entire brain is active", "Psychology textbooks debunk this myth"]),
    ("The Earth is flat.", "false", "science", ["Conclusive evidence from satellite imagery", "Basic physics and astronomy since ancient Greece"]),
    ("Vaccines cause autism.", "false", "science", ["Wakefield study retracted (2010)", "Multiple large-scale studies show no link"]),
    ("Evolution is just a theory.", "misleading", "science", ["Theory in science means well-substantiated explanation", "Overwhelming evidence from genetics, fossils, and observations"]),
    ("The Earth is approximately 4.5 billion years old.", "true", "science", ["Radiometric dating of meteorites and rocks", "Geological Society of America"]),
    ("Oxygen was discovered by Joseph Priestley.", "true", "science", ["Priestley (1774)", "Royal Society of Chemistry"]),
    ("Light travels faster than sound.", "true", "science", ["Physics of wave propagation", "Speed of light ~300,000 km/s vs sound ~343 m/s"]),
    ("Antibiotics kill viruses.", "false", "science", ["CDC: Antibiotics work against bacteria, not viruses", "WHO guidelines"]),
    ("The Coriolis effect determines the direction water drains.", "misleading", "science", ["Coriolis effect is real but too weak for small-scale drainage", "Bathroom sink direction depends on basin shape"]),
    ("Mars has two moons.", "true", "science", ["NASA: Phobos and Deimos", "Astronomical observations"]),
    ("Conductors allow electricity to flow through them.", "true", "science", ["Physics of electrical conduction", "Standard electronics textbooks"]),
    ("Quantum entanglement allows faster-than-light communication.", "false", "science", ["No-signaling theorem", "Quantum mechanics does not permit FTL communication"]),
    ("CRISPR is a gene-editing technology.", "true", "science", ["Nobel Prize in Chemistry 2020 (Doudna, Charpentier)", "Nature research papers"]),
    ("The moon is gradually moving away from Earth.", "true", "science", ["Lunar laser ranging experiments", "NASA: ~3.8 cm per year"]),
    ("Black holes are completely black and invisible.", "misleading", "science", ["Event Horizon Telescope imaged one in 2019", "Hawking radiation theory suggests they emit particles"]),
    ("Carbon dating can date fossils up to 50,000 years old.", "true", "science", ["Radiocarbon dating methodology", "Libby (1949), Nobel Prize 1960"]),

    # History (20+)
    ("World War II ended in 1945.", "true", "history", ["Historical records", "UN formation 1945"]),
    ("The Berlin Wall fell in 1989.", "true", "history", ["Historical records", "German reunification 1990"]),
    ("Napoleon was defeated at the Battle of Waterloo.", "true", "history", ["Battle of Waterloo (1815)", "Historical records"]),
    ("The French Revolution started in 1789.", "true", "history", ["Storming of the Bastille (July 14, 1789)", "Historical records"]),
    ("Alexander the Great conquered Persia.", "true", "history", ["Battle of Gaugamela (331 BCE)", "Historical records from Arrian, Plutarch"]),
    ("The Roman Empire fell in 476 AD.", "true", "history", ["Fall of Western Roman Empire", "Historical records"]),
    ("The first moon landing was in 1969.", "true", "history", ["Apollo 11 (July 20, 1969)", "NASA records"]),
    ("Cleopatra was Egyptian.", "misleading", "history", ["She was of Greek Macedonian descent (Ptolemaic dynasty)", "She was born in Alexandria, Egypt"]),
    ("The pyramids were built by slaves.", "false", "history", ["Archaeological evidence shows skilled workers built them", "Worker tombs found near pyramids show respect"]),
    ("Christopher Columbus discovered America.", "misleading", "history", ["Vikings reached North America ~1000 AD", "Indigenous peoples were already living there"]),
    ("The Titanic sank on its maiden voyage.", "true", "history", ["RMS Titanic sank April 15, 1912", "Official inquiries and survivor accounts"]),
    ("World War I was triggered by the assassination of Archduke Franz Ferdinand.", "true", "history", ["Assassination on June 28, 1914 in Sarajevo", "Historical records and diplomatic cables"]),
    ("The Cold War was between the US and USSR.", "true", "history", ["1947-1991 period", "Historical records and declassified documents"]),
    ("Joan of Arc was burned at the stake.", "true", "history", ["1431 execution in Rouen, France", "Historical trial records"]),
    ("The Industrial Revolution began in England.", "true", "history", ["1760-1840 period", "Historical economic records"]),
    ("Vikings wore horned helmets.", "false", "history", ["No archaeological evidence", "Myth originated from 19th-century romanticized depictions"]),
    ("The Magna Carta was signed in 1215.", "true", "history", ["Runnymede, England", "Original document preserved in British Library"]),
    ("Marie Antoinette said 'Let them eat cake'.", "false", "history", ["No contemporary evidence she said this", "Phrase attributed to various French royalty earlier"]),
    ("The Library of Alexandria was burned by Julius Caesar.", "misleading", "history", ["Caesar's fire damaged part of it", "Multiple events contributed to its destruction over centuries"]),
    ("The Sistine Chapel ceiling was painted by Michelangelo.", "true", "history", ["1508-1512, Vatican", "Historical records and commission documents"]),
    ("Genghis Khan founded the Mongol Empire.", "true", "history", ["1206 establishment", "The Secret History of the Mongols"]),
    ("The Spanish Inquisition was established in 1478.", "true", "history", ["Papal bull by Sixtus IV", "Historical records of the Spanish monarchy"]),

    # Tech (20+)
    ("The first computer virus was created in 1983.", "true", "tech", ["Fred Cohen coined the term", "Academic research on computer viruses"]),
    ("Linux was created by Linus Torvalds.", "true", "tech", ["Linux kernel first released 1991", "Torvalds' original announcement on comp.os.minix"]),
    ("The World Wide Web was invented by Tim Berners-Lee.", "true", "tech", ["1989 proposal at CERN", "First website info.cern.ch (1990)"]),
    ("Python was created by Guido van Rossum.", "true", "tech", ["First released in 1991", "Python Software Foundation"]),
    ("The first iPhone was released in 2007.", "true", "tech", ["Apple Inc. announcement Jan 2007", "Release June 29, 2007"]),
    ("Google was originally called Backrub.", "true", "tech", ["Stanford University project (1996)", "Original name changed to Google in 1997"]),
    ("The HTML stands for HyperText Markup Language.", "true", "tech", ["W3C specifications", "Tim Berners-Lee's original documentation"]),
    ("Java was originally called Oak.", "true", "tech", ["James Gosling at Sun Microsystems (1991)", "Renamed to Java in 1995"]),
    ("The Apollo guidance computer had less power than a modern calculator.", "true", "tech", ["AGC had ~2 MHz clock, 4 KB RAM", "NASA technical documentation"]),
    ("The Y2K bug caused global computer crashes.", "false", "tech", ["Minimal actual disruption occurred", "Wide preparation prevented major issues"]),
    ("Macs cannot get viruses.", "false", "tech", ["macOS has had malware (e.g., Flashback, Fruitfly)", "No OS is immune to security threats"]),
    ("The cloud is someone else's computer.", "true", "tech", ["Cloud computing uses remote servers", "Data centers worldwide"]),
    ("Moore's Law states that transistor density doubles ~every 2 years.", "true", "tech", ["Gordon Moore's 1965 prediction", "Has held for decades but is slowing"]),
    ("Wi-Fi stands for Wireless Fidelity.", "false", "tech", ["Wi-Fi does not stand for anything", "Brand name coined by Interbrand for Wi-Fi Alliance"]),
    ("The first email was sent by Ray Tomlinson.", "true", "tech", ["1971 over ARPANET", "Tomlinson chose @ symbol"]),
    ("OpenAI was founded in 2015.", "true", "tech", ["Founded December 2015 by Sam Altman, Elon Musk, others", "Original mission statement"]),
    ("The Turing Test was proposed by Alan Turing in 1950.", "true", "tech", ["'Computing Machinery and Intelligence' paper", "Philosophical framework for AI"]),
    ("Blockchain technology was invented for Bitcoin.", "true", "tech", ["Satoshi Nakamoto's 2008 whitepaper", "Original blockchain implementation"]),
    ("TCP/IP was developed by Vint Cerf and Bob Kahn.", "true", "tech", ["1974 paper 'A Protocol for Packet Network Intercommunication'", "Foundation of the internet"]),
    ("Quantum computers will replace classical computers entirely.", "false", "tech", ["Quantum computers are specialized for certain problems", "Classical computers remain better for most tasks"]),

    # General (40+)
    ("The Amazon is the largest rainforest in the world.", "true", "general", ["FAO data", "WWF: Amazon covers ~5.5 million km²"]),
    ("Mount Everest is the tallest mountain on Earth.", "true", "general", ["~8,849 meters above sea level", "Survey of India / Nepali government data"]),
    ("The Pacific Ocean is the largest ocean.", "true", "general", ["NOAA: ~165 million km²", "Covers ~32% of Earth's surface"]),
    ("China has the largest population in the world.", "true", "general", ["UN World Population Prospects 2023", "Chinese government census data"]),
    ("Antarctica is a continent.", "true", "general", ["Geological definition", "Antarctic Treaty (1959)"]),
    ("The Sahara is the largest hot desert.", "true", "general", ["~9.2 million km²", "NASA Earth Observatory"]),
    ("Australia is both a country and a continent.", "true", "general", ["Geographical and political classification", "UN membership and continent definitions"]),
    ("Venus is the hottest planet in the solar system.", "true", "general", ["NASA: average surface temp ~462°C", "Runaway greenhouse effect"]),
    ("The Leaning Tower of Pisa is in Italy.", "true", "general", ["Pisa, Tuscany", "Construction started in 1173"]),
    ("Shakespeare wrote the play 'Hamlet'.", "true", "general", ["First performed ~1600", "First Folio (1623) publication"]),
    ("The Eiffel Tower is in London.", "false", "general", ["Eiffel Tower is in Paris, France", "Built 1887-1889 for World's Fair"]),
    ("Bananas grow on trees.", "false", "general", ["Banana plants are large herbaceous flowering plants", "Technically a berry from a herb, not a tree"]),
    ("The Great Barrier Reef is visible from outer space.", "misleading", "general", ["NASA: barely visible under ideal conditions", "Often falsely claimed as easily visible"]),
    ("Diamonds are made of compressed coal.", "false", "general", ["Diamonds form from carbon under pressure deep in Earth", "Most diamonds are older than land plants (coal source)"]),
    ("There are 7 continents on Earth.", "true", "general", ["Asia, Africa, N. America, S. America, Antarctica, Europe, Australia", "UN geographical classification"]),
    ("The Caspian Sea is the largest lake.", "true", "general", ["~371,000 km², saline", "Geographical classification as endorheic basin"]),
    ("Penguins can fly.", "false", "general", ["Penguins are flightless birds", "Adapted for swimming, not flying"]),
    ("Gold is a good conductor of electricity.", "true", "general", ["Third best conductor after silver and copper", "Used in electronics for corrosion resistance"]),
    ("Chameleons change color to blend in with surroundings.", "misleading", "general", ["Color change is mainly for communication and temperature regulation", "Not primarily for camouflage"]),
    ("A group of lions is called a pride.", "true", "general", ["Animal group terminology", "Zoological classification"]),
    ("Honey never spoils.", "true", "general", ["Archaeologists found 3,000-year-old edible honey in Egyptian tombs", "Low water content and acidic pH prevent spoilage"]),
    ("The human nose can detect over 1 trillion scents.", "true", "general", ["Rockefeller University study (2014)", "Olfactory research"]),
    ("Octopuses have three hearts.", "true", "general", ["Two branchial hearts, one systemic", "Marine biology research"]),
    ("A day on Venus is longer than a year on Venus.", "true", "general", ["Venus day: ~243 Earth days", "Venus year: ~225 Earth days"]),
    ("Lightning never strikes the same place twice.", "false", "general", ["Empire State Building is struck ~100 times per year", "Tall structures are repeatedly struck"]),
    ("Humans have five senses.", "misleading", "general", ["We have at least 9 senses (including balance, temperature, proprioception)", "Scientific consensus on multiple sensory systems"]),
    ("Bats are blind.", "false", "general", ["Bats can see, some species have good vision", "'Blind as a bat' is a misleading idiom"]),
    ("Cracking your knuckles causes arthritis.", "false", "general", ["Studies show no correlation", "Sound comes from gas bubbles in synovial fluid"]),
    ("The national animal of Scotland is the unicorn.", "true", "general", ["Heraldic symbol since 12th century", "Royal Coat of Arms of Scotland"]),
    ("Fortune cookies were invented in China.", "false", "general", ["Invented in California (early 1900s)", "Japanese-American influence, popularized by Chinese restaurants"]),
    ("A chef's hat has 100 pleats.", "true", "general", ["Traditional toque blanche has 100 pleats", "Represents 100 ways to cook eggs"]),
    ("Dragonflies have 6 legs but cannot walk.", "true", "general", ["Legs adapted for catching prey in flight", "Entomological research"]),
    ("Peanuts are not nuts.", "true", "general", ["Peanuts are legumes (beans/peas family)", "Botanical classification differs from culinary"]),
    ("A jiffy is an actual unit of time.", "true", "general", ["1/100th of a second in some contexts", "Also used informally in computing for 1/60th of a second"]),
    ("There are more trees on Earth than stars in the Milky Way.", "true", "general", ["~3 trillion trees vs ~100-400 billion stars", "Nature study (2015) and astronomical estimates"]),
    ("Polar bears have black skin.", "true", "general", ["Skin is black to absorb heat", "Fur is actually translucent, not white"]),
    ("Tomatoes are fruits, not vegetables.", "true", "general", ["Botanically a fruit (contains seeds)", "Culinary classification as vegetable (Supreme Court 1893)"]),
    ("Sharks have been around longer than trees.", "true", "general", ["Sharks ~400 million years, trees ~350 million years", "Fossil records"]),
    ("The shortest war in history lasted 38 minutes.", "true", "general", ["Anglo-Zanzibar War (August 27, 1896)", "Guinness World Records"]),
    ("A cloud weighs around a million tons.", "true", "general", ["Cumulus cloud ~500 tons of water", "Scientific calculation of water density in clouds"]),
]

def score_claim(claim: str, category: str) -> dict:
    claim_lower = re.sub(r'[^\w\s]', '', claim.lower()).strip()
    best_score = 0
    best_match = None

    for fact_text, verdict, fact_cat, sources in FACTS:
        if category != "general" and fact_cat != category:
            continue
        fact_lower = re.sub(r'[^\w\s]', '', fact_text.lower()).strip()

        claim_words = set(claim_lower.split())
        fact_words = set(fact_lower.split())
        intersection = claim_words & fact_words
        union = claim_words | fact_words
        if len(union) == 0:
            continue
        score = len(intersection) / len(union)

        for phrase in ["not ", "never ", "cannot ", "don't ", "doesn't ", "isn't ", "aren't ", "wasn't ", "weren't "]:
            if (phrase in claim_lower) != (phrase in fact_lower):
                score *= 0.5

        if score > best_score:
            best_score = score
            best_match = (fact_text, verdict, sources)

    return best_match, best_score

async def fact_check(params: dict) -> dict:
    claim = params.get("claim", "").strip()
    category = params.get("category", "general").strip().lower()

    if not claim:
        return error_response("Please provide a 'claim' to fact-check.")

    if category not in ("science", "history", "tech", "general"):
        return error_response("Category must be 'science', 'history', 'tech', or 'general'.")

    match, score = score_claim(claim, category)

    if match and score > 0.3:
        fact_text, verdict, sources = match
        confidence = "high" if score > 0.7 else "medium"
        return success_response({
            "claim": claim,
            "verdict": verdict,
            "explanation": f"The claim {'matches' if verdict == 'true' else 'contradicts'} known information: '{fact_text}'",
            "sources": sources,
            "confidence": confidence,
            "category": category
        })

    return success_response({
        "claim": claim,
        "verdict": "unsupported",
        "explanation": "No matching fact found in the database for this claim.",
        "sources": [],
        "confidence": "low",
        "category": category,
        "note": "This claim could not be verified against the built-in fact database."
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
