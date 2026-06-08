from skills.utils import success_response, error_response, fetch_json

# Two words per line: w1|p1|d1|e1;w2|p2|d2|e2
D = """abandon|verb|To leave/give up.|abandon ship;ability|noun|Power to do.|solve problems
able|adj|Having power or means.|finish on time;about|prep|On the subject of.|about history
above|prep|In higher position.|above clouds;accept|verb|Agree to receive.|accepted job
access|noun|Means to approach.|library access;achieve|verb|Reach a goal.|achieved dream
action|noun|Process of doing.|action required;activity|noun|Something done.|outdoor activities
addition|noun|Adding something.|new room;address|noun|Where someone lives.|home address
adult|noun|Fully grown person.|responsibilities;advance|verb|Move forward.|technology advances
advantage|noun|Greater chance.|height advantage;advice|noun|Guidance offered.|good advice
affect|verb|Influence on.|affects mood;agree|verb|Same opinion.|agree with you
algorithm|noun|Process for calc.|sorting algorithms;allow|verb|To permit.|allow me
almost|adv|Very nearly.|almost there;already|adv|Before specified time.|already eaten
also|adv|In addition.|also paints;always|adv|At all times.|always on time
amount|noun|Quantity.|large amount;analysis|noun|Detailed exam.|analysis took weeks
ancient|adj|Distant past.|ancient ruins;animal|noun|Living organism.|wild animals
annual|adj|Once a year.|annual picnic;answer|noun|Reply.|correct answer
appear|verb|Come into sight.|rainbow appeared;application|noun|Formal request.|job application
approach|verb|Come near.|train approached;area|noun|Region.|dining area
argument|noun|Opposite views.|heated argument;artificial|adj|Made by humans.|AI system
atmosphere|noun|Gases around Earth.|atmosphere;attempt|verb|Try to do.|attempted climb
attention|noun|Concentration.|pay attention;attitude|noun|Way of thinking.|positive attitude
attract|verb|Draw toward.|magnets attract;authority|noun|Power to order.|teacher authority
available|adj|Able to be used.|tickets;average|noun|Typical amount.|average score
balance|noun|Weight distribution.|keep balance;beautiful|adj|Pleasing.|beautiful sunset
become|verb|Begin to be.|became doctor;behavior|noun|Way one acts.|good behavior
believe|verb|Accept as true.|believe you;benefit|noun|Advantage.|health benefits
brief|adj|Short.|brief meeting;bright|adj|Giving light.|bright sun
budget|noun|Income estimate.|plan budget;capable|adj|Having ability.|capable person
capacity|noun|Maximum amount.|capacity 50k;careful|adj|Avoiding harm.|careful with glass
category|noun|Class/division.|categories;certain|adj|Known for sure.|are you certain
challenge|noun|Difficult task.|climbing challenge;character|noun|Personal qualities.|good character
climate|noun|Weather.|climate change;command|verb|Give order.|general commanded
communicate|verb|Share info.|email comm;community|noun|Group in place.|community center
company|noun|Business.|tech company;compare|verb|Find differences.|compare options
compete|verb|Strive against.|athletes compete;complex|adj|Many parts.|complex problem
computer|noun|Electronic device.|uses computer;concept|noun|Abstract idea.|concept of time
concern|noun|Worry.|safety concern;conclusion|noun|Judgment.|reached conclusion
condition|noun|State.|good condition;confidence|noun|Trust.|confidence
confirm|verb|Establish truth.|confirm;conflict|noun|Disagreement.|conflict resolved
connect|verb|Bring together.|connect cables;conscious|adj|Aware.|conscious
consequence|noun|Result.|consequences;consider|verb|Think about.|consider options
construct|verb|Build.|construct model;consume|verb|Use up.|consume less
contain|verb|Hold within.|box contains;content|noun|Material.|book content
context|noun|Circumstances.|context matters;continue|verb|Keep doing.|continue work
contribute|verb|Give toward.|contribute ideas;control|verb|Exercise authority.|control situation
creative|adj|Inventive.|creative thinking;critical|adj|Adverse judgment.|critical feedback
crucial|adj|Very important.|crucial step;culture|noun|Group customs.|Japanese culture
current|adj|Present.|current situation;database|noun|Data set.|user database
debate|noun|Discussion.|lively debate;decade|noun|Ten years.|decade of progress
decision|noun|Conclusion.|make decision;decline|verb|Decrease/refuse.|population declined
defense|noun|Protection.|defense held;define|verb|State meaning.|define term
degree|noun|Unit/level.|science degree;demand|verb|Ask forcefully.|demand service
demonstrate|verb|Show clearly.|demonstrate;department|noun|Division.|sales department
depend|verb|Controlled by.|depends on weather;describe|verb|Give account.|describe events
design|verb|Plan form.|design logo;determine|verb|Decide.|determine cause
develop|verb|Grow.|develop skills;device|noun|Tool.|electronic devices
discover|verb|Find unexpectedly.|discover;discuss|verb|Talk about.|discuss plan
disease|noun|Disorder.|disease spread;display|verb|Show.|display artwork
economy|noun|Production/trade.|economy;educate|verb|Instruct.|educate children
efficient|adj|Productive.|efficient engine;element|noun|Basic part.|chemical elements
eliminate|verb|Remove.|eliminate errors;emerge|verb|Come out.|evidence emerged
emotion|noun|Feeling.|emotions high;emphasis|noun|Importance.|emphasis on quality
employ|verb|Give work.|employs 500;encounter|verb|Meet unexpectedly.|encounter problem
encourage|verb|Give support.|encourage team;energy|noun|Work capacity.|solar energy
engage|verb|Occupy attention.|engage audience;enhance|verb|Improve.|enhance skills
enormous|adj|Very large.|enormous building;ensure|verb|Make certain.|ensure safety
entire|adj|Whole.|entire world;environment|noun|Surroundings.|protect environment
establish|verb|Set up.|establish business;estimate|verb|Calculate roughly.|estimate cost
evaluate|verb|Assess.|evaluate results;evidence|noun|Facts.|evidence supports
evolution|noun|Development.|species evolution;examine|verb|Inspect.|examine evidence
example|noun|Model.|follow example;exchange|verb|Give and receive.|exchange info
execute|verb|Carry out.|execute program;exercise|noun|Activity.|daily exercise
exist|verb|Have reality.|does life exist;expand|verb|Become larger.|expand horizons
expect|verb|Regard as likely.|expect results;experience|noun|Contact.|work experience
experiment|noun|Scientific test.|conduct experiment;expert|noun|Knowledgeable person.|consult expert
explain|verb|Make clear.|explain concept;explore|verb|Discover.|explore city
express|verb|Convey thought.|express opinion;extend|verb|Make longer.|extend deadline
extract|verb|Remove.|extract data;factor|noun|Contributing circumstance.|key factor
feature|noun|Attribute.|many features;flexible|adj|Bending.|flexible schedule
forecast|noun|Prediction.|weather forecast;foundation|noun|Base.|strong foundation
framework|noun|Structure.|legal framework;function|noun|Relation.|math function
generate|verb|Produce.|generate electricity;global|adj|Worldwide.|global warming
guarantee|verb|Promise.|guarantee satisfaction;harmony|noun|Arrangement.|musical harmony
hypothesis|noun|Explanation.|test hypothesis;identical|adj|Exactly same.|identical twins
identity|noun|Who a person is.|verify identity;impact|noun|Effect.|environmental impact
implement|verb|Put into effect.|implement plan;improve|verb|Make better.|improve skills
include|verb|Contain as part.|include details;increase|verb|Become greater.|prices increased
indicate|verb|Point out.|signs indicate danger;individual|noun|Single person.|unique individual
industry|noun|Production.|auto industry;influence|noun|Capacity to affect.|peer influence
innovation|noun|New idea.|tech innovation;input|noun|Something put in.|user input
insight|noun|Understanding.|valuable insight;inspect|verb|Examine closely.|inspect product
inspire|verb|Fill with urge.|inspire others;install|verb|Place for use.|install software
integrate|verb|Combine.|integrate systems;intelligence|noun|Learning ability.|AI
interact|verb|Act with each other.|interact with apps;interest|noun|Wanting to know.|show interest
interpret|verb|Explain meaning.|interpret data;investigate|verb|Examine systematically.|investigate case
knowledge|noun|Information.|knowledge is power;maintain|verb|Keep condition.|maintain equipment
massive|adj|Large/heavy.|massive structure;mechanism|noun|System of parts.|clock mechanism
minimize|verb|Reduce.|minimize risk;modify|verb|Change.|modify design
monitor|verb|Observe.|monitor system;motivate|verb|Provide reason.|motivate team
navigate|verb|Plan route.|navigate website;negative|adj|Not positive.|negative attitude
negotiate|verb|Reach agreement.|negotiate terms;network|noun|Interconnected things.|computer network
obtain|verb|Get.|obtain permission;obvious|adj|Easily seen.|obvious answer
operate|verb|Control.|operate machine;opinion|noun|Belief.|in my opinion
opportunity|noun|Circumstances.|great opp;oppose|verb|Be against.|oppose decision
option|noun|Choice.|many options;organize|verb|Arrange.|organize files
original|adj|From beginning.|original copy;outcome|noun|Result.|trial outcome
output|noun|Amount produced.|factory output;participate|verb|Take part.|participate in event
phenomenon|noun|Observable event.|natural phenomenon;philosophy|noun|Study of fundamentals.|Greek philosophy
physical|adj|Body related.|physical exercise;positive|adj|Optimistic.|positive attitude
potential|noun|Latent qualities.|unlock potential;practical|adj|Useful.|practical solution
practice|noun|Repeated exercise.|practice makes perfect;predict|verb|Foretell.|predict weather
prefer|verb|Like better.|prefer tea;previous|adj|Before.|previous experience
principle|noun|Fundamental truth.|moral principles;priority|noun|Importance.|set priorities
procedure|noun|Way of doing.|follow procedure;process|noun|Series of actions.|mfg process
program|noun|Instructions.|write program;progress|noun|Forward movement.|make progress
project|noun|Undertaking.|research project;promote|verb|Support.|promote health
psychology|noun|Mind study.|clinical psychology;purchase|verb|Buy.|purchase item
pursue|verb|Follow.|pursue dreams;random|adj|Without method.|random selection
range|noun|Variation area.|wide range;rapid|adj|Very quick.|rapid growth
rational|adj|Reason based.|rational decision;reaction|noun|Response.|chemical reaction
recognize|verb|Identify.|recognize pattern;recommend|verb|Suggest.|recommend book
recover|verb|Return to normal.|recover;reduce|verb|Make smaller.|reduce costs
reflect|verb|Throw back.|mirrors reflect;reform|verb|Improve.|reform system
regulate|verb|Control by rules.|regulate industry;reject|verb|Refuse.|reject proposal
relate|verb|Make connection.|relate to topic;release|verb|Set free.|release software
relevant|adj|Connected.|relevant info;rely|verb|Depend on.|rely on data
remain|verb|Stay.|remain calm;remove|verb|Take away.|remove obstacle
replace|verb|Take place of.|replace battery;represent|verb|Act for.|represent company
require|verb|Need.|require assistance;research|noun|Investigation.|scientific research
resolve|verb|Find solution.|resolve issue;resource|noun|Supply.|natural resources
respond|verb|Reply.|respond to query;restore|verb|Bring back.|restore data
restrict|verb|Limit.|restrict access;reveal|verb|Make known.|reveal truth
revenue|noun|Income.|annual revenue;revolution|noun|Dramatic change.|industrial revolution
schedule|noun|Plan.|flight schedule;sequence|noun|Order.|in sequence
severe|adj|Intense.|severe weather;significant|adj|Great.|significant discovery
similar|adj|Resembling.|similar results;sophisticated|adj|Complex.|sophisticated tech
specific|adj|Clearly defined.|specific instructions;stability|noun|Stable state.|economic stability
strategy|noun|Action plan.|business strategy;summarize|verb|Brief statement.|summarize article
symbol|noun|Representation.|peace symbol;technology|noun|Applied science.|modern technology
temporary|adj|Limited time.|temporary solution;tradition|noun|Custom.|family tradition
transfer|verb|Move.|transfer files;transform|verb|Change thoroughly.|transform org
transition|noun|Changing process.|peaceful transition;ultimate|adj|Most extreme.|ultimate goal
understand|verb|Perceive meaning.|understand;unique|adj|Only one.|unique opportunity
universal|adj|Relating to all.|universal rights;valid|adj|Sound/correct.|valid argument
version|noun|Form.|latest version;vision|noun|Ability to see.|night vision
vital|adj|Necessary.|vital info;volume|noun|Space amount.|turn up volume
widespread|adj|Over large area.|widespread support"""

W = {}
for line in D.strip().split("\n"):
    for part in line.split(";"):
        p = part.split("|", 3)
        if len(p) == 4:
            W[p[0]] = [{"partOfSpeech": p[1], "definitions": [{"definition": p[2], "example": p[3]}]}]

async def dictionary(params: dict) -> dict:
    word = params.get("word", "").strip().lower()
    if not word:
        return error_response("Please provide a 'word' parameter.")
    if word in W:
        return success_response({"word": word, "phonetic": "", "meanings": W[word]})
    data = await fetch_json(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
    if not data:
        return error_response(f"No definition found for '{word}'.")
    entry = data[0]
    phonetic = entry.get("phonetic") or (entry.get("phonetics") or [{}])[0].get("text", "")
    meanings = []
    for m in entry.get("meanings", []):
        defs = [{"definition": d.get("definition", "")} | ({"example": d["example"]} if d.get("example") else {}) for d in m.get("definitions", [])]
        meanings.append({"partOfSpeech": m.get("partOfSpeech", ""), "definitions": defs})
    return success_response({"word": word, "phonetic": phonetic, "meanings": meanings})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
