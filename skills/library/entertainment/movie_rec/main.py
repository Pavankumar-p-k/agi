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

from skills.utils import success_response, error_response

MOVIES = [
    {"title": "The Shawshank Redemption", "year": 1994, "genre": "drama", "rating": 9.3, "description": "Two imprisoned men bond over a number of years, finding solace and eventual redemption through acts of common decency."},
    {"title": "The Godfather", "year": 1972, "genre": "drama", "rating": 9.2, "description": "The aging patriarch of an organized crime dynasty transfers control to his reluctant son."},
    {"title": "The Dark Knight", "year": 2008, "genre": "action", "rating": 9.0, "description": "When the menace of the Joker threatens Gotham, Batman must accept one of the greatest tests."},
    {"title": "Pulp Fiction", "year": 1994, "genre": "drama", "rating": 8.9, "description": "The lives of two mob hitmen, a boxer, a gangster and his wife intertwine in four tales of violence and redemption."},
    {"title": "Schindler's List", "year": 1993, "genre": "drama", "rating": 9.0, "description": "In German-occupied Poland during World War II, industrialist Oskar Schindler gradually becomes concerned for his Jewish workforce."},
    {"title": "Inception", "year": 2010, "genre": "sci-fi", "rating": 8.8, "description": "A thief who steals corporate secrets through dream-sharing technology is given the task of planting an idea."},
    {"title": "Fight Club", "year": 1999, "genre": "drama", "rating": 8.8, "description": "An insomniac office worker and a devil-may-care soap maker form an underground fight club."},
    {"title": "Forrest Gump", "year": 1994, "genre": "drama", "rating": 8.8, "description": "The presidencies of Kennedy and Johnson through the eyes of an Alabama man with an IQ of 75."},
    {"title": "The Matrix", "year": 1999, "genre": "sci-fi", "rating": 8.7, "description": "A computer hacker learns about the true nature of reality and his role in the war against its controllers."},
    {"title": "Interstellar", "year": 2014, "genre": "sci-fi", "rating": 8.7, "description": "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival."},
    {"title": "The Silence of the Lambs", "year": 1991, "genre": "horror", "rating": 8.6, "description": "A young FBI cadet seeks the help of an incarcerated cannibal killer to catch another serial killer."},
    {"title": "Star Wars: A New Hope", "year": 1977, "genre": "sci-fi", "rating": 8.6, "description": "Luke Skywalker joins forces with a Jedi Knight, a cocky pilot, a Wookiee and two droids to save the galaxy."},
    {"title": "Goodfellas", "year": 1990, "genre": "drama", "rating": 8.7, "description": "The story of Henry Hill and his life in the mob, covering his relationship with his wife and his partners."},
    {"title": "The Departed", "year": 2006, "genre": "drama", "rating": 8.5, "description": "An undercover cop and a mole in the police attempt to identify each other while infiltrating a gang."},
    {"title": "Parasite", "year": 2019, "genre": "drama", "rating": 8.5, "description": "Greed and class discrimination threaten the newly formed symbiotic relationship between the wealthy Park family and the destitute Kim clan."},
    {"title": "Gladiator", "year": 2000, "genre": "action", "rating": 8.5, "description": "A former Roman General sets out to exact vengeance against the corrupt emperor who murdered his family."},
    {"title": "The Lord of the Rings: The Fellowship of the Ring", "year": 2001, "genre": "action", "rating": 8.8, "description": "A meek Hobbit from the Shire and eight companions set out on a journey to destroy the powerful One Ring."},
    {"title": "Avengers: Endgame", "year": 2019, "genre": "action", "rating": 8.4, "description": "The Avengers assemble once more to reverse Thanos' actions and restore balance to the universe."},
    {"title": "Mad Max: Fury Road", "year": 2015, "genre": "action", "rating": 8.1, "description": "In a post-apocalyptic wasteland, a woman rebels against a tyrannical ruler in search of her homeland."},
    {"title": "John Wick", "year": 2014, "genre": "action", "rating": 7.4, "description": "An ex-hit-man comes out of retirement to track down the gangsters that killed his dog and took everything."},
    {"title": "Die Hard", "year": 1988, "genre": "action", "rating": 8.2, "description": "A New York City police officer tries to save his wife and others from a group of terrorists in a skyscraper."},
    {"title": "Terminator 2: Judgment Day", "year": 1991, "genre": "action", "rating": 8.6, "description": "A cyborg protects a young boy from a more advanced cyborg sent back in time to kill him."},
    {"title": "Superbad", "year": 2007, "genre": "comedy", "rating": 7.6, "description": "Two co-dependent high school seniors navigate their final weeks of school and a wild party."},
    {"title": "The Hangover", "year": 2009, "genre": "comedy", "rating": 7.7, "description": "Three buddies wake up from a bachelor party in Las Vegas with no memory of the previous night."},
    {"title": "Bridesmaids", "year": 2011, "genre": "comedy", "rating": 6.8, "description": "Competition between the maid of honor and a bridesmaid threatens to upend the wedding."},
    {"title": "Dumb and Dumber", "year": 1994, "genre": "comedy", "rating": 7.3, "description": "The cross-country adventures of two good-natured but incredibly stupid friends."},
    {"title": "Step Brothers", "year": 2008, "genre": "comedy", "rating": 6.9, "description": "Two aimless middle-aged brothers still living at home are forced together when their parents marry."},
    {"title": "Anchorman: The Legend of Ron Burgundy", "year": 2004, "genre": "comedy", "rating": 7.2, "description": "Ron Burgundy is San Diego's top-rated newsman in the 1970s, until a ambitious female reporter joins the team."},
    {"title": "The Grand Budapest Hotel", "year": 2014, "genre": "comedy", "rating": 8.1, "description": "A writer encounters the owner of an aging high-class hotel, who tells of his early years serving as a lobby boy."},
    {"title": "The Truman Show", "year": 1998, "genre": "drama", "rating": 8.2, "description": "An insurance salesman discovers his whole life is actually a reality TV show."},
    {"title": "Blade Runner 2049", "year": 2017, "genre": "sci-fi", "rating": 8.0, "description": "Young Blade Runner K's discovery of a long-buried secret leads him to track down former Blade Runner Rick Deckard."},
    {"title": "Arrival", "year": 2016, "genre": "sci-fi", "rating": 7.9, "description": "A linguist works with the military to communicate with alien lifeforms after twelve mysterious spacecraft appear."},
    {"title": "The Shining", "year": 1980, "genre": "horror", "rating": 8.4, "description": "A family heads to an isolated hotel for the winter where a sinister presence influences the father into violence."},
    {"title": "Get Out", "year": 2017, "genre": "horror", "rating": 7.7, "description": "A young African-American visits his white girlfriend's parents for the weekend, where his simmering uneasiness about their reception of him eventually reaches a boiling point."},
    {"title": "A Quiet Place", "year": 2018, "genre": "horror", "rating": 7.5, "description": "In a post-apocalyptic world, a family is forced to live in silence while hiding from monsters with ultra-sensitive hearing."},
    {"title": "Hereditary", "year": 2018, "genre": "horror", "rating": 7.3, "description": "A grieving family is haunted by tragic and disturbing occurrences after the death of their secretive grandmother."},
    {"title": "The Witch", "year": 2015, "genre": "horror", "rating": 7.0, "description": "A family in 1630s New England is torn apart by the forces of witchcraft, black magic and possession."},
    {"title": "La La Land", "year": 2016, "genre": "drama", "rating": 8.0, "description": "While navigating their careers in Los Angeles, a pianist and an actress fall in love while attempting to reconcile their aspirations."},
    {"title": "Whiplash", "year": 2014, "genre": "drama", "rating": 8.5, "description": "A promising young drummer enrolls at a music conservatory where an abusive instructor will stop at nothing to realize a student's potential."},
    {"title": "The Social Network", "year": 2010, "genre": "drama", "rating": 7.8, "description": "As Harvard student Mark Zuckerberg creates the social networking site Facebook, he finds it both complicates and enriches his life."},
    {"title": "Joker", "year": 2019, "genre": "drama", "rating": 8.4, "description": "In Gotham City, mentally troubled comedian Arthur Fleck is disregarded and mistreated by society, leading him to become the Joker."},
    {"title": "Django Unchained", "year": 2012, "genre": "drama", "rating": 8.5, "description": "With the help of a German bounty-hunter, a freed slave sets out to rescue his wife from a brutal plantation owner."},
    {"title": "Inglourious Basterds", "year": 2009, "genre": "action", "rating": 8.3, "description": "In Nazi-occupied France during World War II, a plan to assassinate Nazi leaders by a group of Jewish U.S. soldiers coincides with a theatre owner's vengeful plans."},
    {"title": "Back to the Future", "year": 1985, "genre": "sci-fi", "rating": 8.5, "description": "Marty McFly, a 17-year-old high school student, is accidentally sent thirty years into the past in a time-traveling DeLorean."},
    {"title": "Jurassic Park", "year": 1993, "genre": "sci-fi", "rating": 8.2, "description": "A pragmatic paleontologist touring an almost complete theme park on an island in Central America is tasked with protecting a couple of kids after an outage."},
    {"title": "E.T. the Extra-Terrestrial", "year": 1982, "genre": "sci-fi", "rating": 7.9, "description": "A troubled child summons the courage to help a friendly alien escape Earth and return to his home world."},
    {"title": "The Sixth Sense", "year": 1999, "genre": "horror", "rating": 8.1, "description": "A frightened, withdrawn Philadelphia boy who communicates with spirits seeks the help of a disheartened child psychologist."},
    {"title": "Alien", "year": 1979, "genre": "horror", "rating": 8.5, "description": "The crew of a commercial spacecraft encounter a deadly lifeform after investigating an unknown transmission."},
    {"title": "The Thing", "year": 1982, "genre": "horror", "rating": 8.2, "description": "A research team in Antarctica is hunted by a shape-shifting alien that assumes the appearance of its victims."},
    {"title": "Groundhog Day", "year": 1993, "genre": "comedy", "rating": 8.0, "description": "A weatherman finds himself inexplicably living the same day over and over again."},
    {"title": "Monty Python and the Holy Grail", "year": 1975, "genre": "comedy", "rating": 8.2, "description": "King Arthur and his knights embark on a surreal, low-budget search for the Holy Grail."},
    {"title": "The Princess Bride", "year": 1987, "genre": "comedy", "rating": 8.0, "description": "A bedridden boy's grandfather reads him the story of a farmboy-turned-pirate who encounters numerous obstacles, enemies and allies."},
    {"title": "Airplane!", "year": 1980, "genre": "comedy", "rating": 7.7, "description": "A man afraid to fly must ensure that a plane lands safely after the pilots become sick."},
    {"title": "Ghostbusters", "year": 1984, "genre": "comedy", "rating": 7.8, "description": "Three former parapsychology professors set up shop as a unique ghost removal service."},
    {"title": "Toy Story", "year": 1995, "genre": "comedy", "rating": 8.3, "description": "A cowboy doll is profoundly threatened and jealous when a new spaceman action figure supplants him as top toy."},
    {"title": "The Incredibles", "year": 2004, "genre": "action", "rating": 8.0, "description": "A family of undercover superheroes, while trying to live a quiet suburban life, are forced into action to save the world."},
    {"title": "The Lion King", "year": 1994, "genre": "drama", "rating": 8.5, "description": "Lion prince Simba flees his kingdom after the murder of his father, only to learn the true meaning of responsibility and bravery."},
    {"title": "Spirited Away", "year": 2001, "genre": "drama", "rating": 8.6, "description": "During her family's move to the suburbs, a sullen 10-year-old girl wanders into a world ruled by gods, witches and spirits."},
    {"title": "Blade Runner", "year": 1982, "genre": "sci-fi", "rating": 8.1, "description": "A blade runner must pursue and terminate four replicants who stole a ship in space and have returned to Earth to find their creator."},
    {"title": "Gravity", "year": 2013, "genre": "sci-fi", "rating": 7.7, "description": "Two astronauts work together to survive after an accident leaves them stranded in space."},
    {"title": "The Martian", "year": 2015, "genre": "sci-fi", "rating": 8.0, "description": "An astronaut becomes stranded on Mars after his team assumes him dead, and must rely on his ingenuity to survive."},
    {"title": "Saving Private Ryan", "year": 1998, "genre": "action", "rating": 8.6, "description": "Following the Normandy Landings, a group of U.S. soldiers go behind enemy lines to retrieve a paratrooper whose brothers have been killed in action."},
    {"title": "Braveheart", "year": 1995, "genre": "action", "rating": 8.3, "description": "Scottish warrior William Wallace leads his countrymen in a rebellion to free his homeland from the tyranny of King Edward I."},
    {"title": "The Avengers", "year": 2012, "genre": "action", "rating": 8.0, "description": "Earth's mightiest heroes must come together and learn to fight as a team to stop the mischievous Loki and his alien army."},
    {"title": "Iron Man", "year": 2008, "genre": "action", "rating": 7.9, "description": "After being held captive in an Afghan cave, an industrialist builds an armored suit and escapes, then becomes a superhero."},
    {"title": "Captain America: The Winter Soldier", "year": 2014, "genre": "action", "rating": 7.7, "description": "As Steve Rogers struggles to embrace his role in the modern world, he teams up with Natasha Romanoff to battle a mysterious threat."},
    {"title": "The Prestige", "year": 2006, "genre": "drama", "rating": 8.5, "description": "After a tragic accident two stage magicians engage in a battle to create the ultimate illusion while sacrificing everything they have."},
    {"title": "Memento", "year": 2000, "genre": "drama", "rating": 8.4, "description": "A man with short-term memory loss attempts to track down his wife's murderer using a system of Polaroid photos and tattoos."},
    {"title": "Se7en", "year": 1995, "genre": "drama", "rating": 8.6, "description": "Two detectives hunt a serial killer who uses the seven deadly sins as his motives."},
    {"title": "The Usual Suspects", "year": 1995, "genre": "drama", "rating": 8.5, "description": "A sole survivor tells of the twisty events leading up to a horrific gun battle on a boat, which begin when five criminals meet at a police lineup."},
    {"title": "12 Angry Men", "year": 1957, "genre": "drama", "rating": 9.0, "description": "A jury holdout attempts to prevent a miscarriage of justice by forcing his colleagues to reconsider the evidence."},
    {"title": "Citizen Kane", "year": 1941, "genre": "drama", "rating": 8.3, "description": "Following the death of a publishing tycoon, news reporters scramble to discover the meaning of his final utterance."},
    {"title": "The Green Mile", "year": 1999, "genre": "drama", "rating": 8.6, "description": "The lives of guards on Death Row are affected by one of their charges: a black man accused of child murder and rape, who has the gift of healing."},
    {"title": "Coco", "year": 2017, "genre": "drama", "rating": 8.4, "description": "Aspiring musician Miguel, confronted with his family's ancestral ban on music, enters the Land of the Dead to find his great-great-grandfather."},
    {"title": "Up", "year": 2009, "genre": "comedy", "rating": 8.3, "description": "78-year-old Carl Fredricksen travels to Paradise Falls in his house equipped with balloons, inadvertently taking a young stowaway."},
    {"title": "Finding Nemo", "year": 2003, "genre": "comedy", "rating": 8.2, "description": "After his son is captured, a timid clownfish sets out on a journey across the ocean to bring him home."},
    {"title": "Shrek", "year": 2001, "genre": "comedy", "rating": 7.9, "description": "A mean lord exiles fairytale creatures to the swamp of a grumpy ogre, who must go on a quest to rescue a princess."},
    {"title": "Hot Fuzz", "year": 2007, "genre": "comedy", "rating": 7.8, "description": "A skilled London police officer, after being transferred to a quiet village, uncovers a dark secret behind the idyllic facade."},
    {"title": "Shaun of the Dead", "year": 2004, "genre": "comedy", "rating": 7.9, "description": "A man decides to turn his life around by winning back his ex-girlfriend, reconciling his relationship with his mother, and dealing with an entire community that has returned from the dead."},
    {"title": "Dune", "year": 2021, "genre": "sci-fi", "rating": 8.0, "description": "A noble family becomes embroiled in a war for control over the galaxy's most valuable asset while its heir becomes troubled by visions of a dark future."},
    {"title": "Tenet", "year": 2020, "genre": "sci-fi", "rating": 7.3, "description": "Armed with only one word, Tenet, and fighting for the survival of the entire world, a Protagonist journeys through a twilight world of international espionage."},
    {"title": "The Batman", "year": 2022, "genre": "action", "rating": 7.8, "description": "When a sadistic serial killer begins murdering key political figures in Gotham, Batman is forced to investigate the city's hidden corruption."},
    {"title": "Everything Everywhere All at Once", "year": 2022, "genre": "sci-fi", "rating": 7.8, "description": "A middle-aged Chinese immigrant is swept up into an insane adventure in which she alone can save existence by exploring other universes."},
    {"title": "Top Gun: Maverick", "year": 2022, "genre": "action", "rating": 8.3, "description": "After more than thirty years of service as a top naval aviator, Pete 'Maverick' Mitchell is where he belongs, pushing the envelope as a courageous test pilot."},
    {"title": "No Country for Old Men", "year": 2007, "genre": "drama", "rating": 8.2, "description": "Violence and mayhem ensue after a hunter stumbles upon a drug deal gone wrong and more than two million dollars in cash near the Rio Grande."},
    {"title": "There Will Be Blood", "year": 2007, "genre": "drama", "rating": 8.2, "description": "A story of family, religion, hatred, oil and madness, focusing on a greedy oil prospector who turns into a monstrous figure."},
    {"title": "Oldboy", "year": 2003, "genre": "drama", "rating": 8.3, "description": "After being kidnapped and imprisoned for fifteen years, Oh Dae-Su is released, only to find he must find his captor in five days."},
    {"title": "Casablanca", "year": 1942, "genre": "drama", "rating": 8.5, "description": "A cynical American expatriate struggles to decide whether or not he should help his former lover and her fugitive husband escape French Morocco."},
    {"title": "Seven Samurai", "year": 1954, "genre": "action", "rating": 8.6, "description": "A poor village under attack by bandits recruits seven unemployed samurai to help them defend themselves."},
    {"title": "Good Will Hunting", "year": 1997, "genre": "drama", "rating": 8.3, "description": "Will Hunting, a janitor at MIT, has a gift for mathematics, but needs help from a psychologist to find direction in his life."},
    {"title": "The Godfather Part II", "year": 1974, "genre": "drama", "rating": 9.0, "description": "The early life and career of Vito Corleone in 1920s New York City is portrayed, while his son Michael expands and tightens his grip on the family crime syndicate."},
    {"title": "Raiders of the Lost Ark", "year": 1981, "genre": "action", "rating": 8.4, "description": "Archaeologist Indiana Jones races to recover a biblical artifact that can locate the Ark of the Covenant."},
    {"title": "The Pianist", "year": 2002, "genre": "drama", "rating": 8.5, "description": "A Polish Jewish musician struggles to survive the destruction of the Warsaw ghetto of World War II."},
    {"title": "The Exorcist", "year": 1973, "genre": "horror", "rating": 8.1, "description": "When a 12-year-old girl is possessed by a mysterious entity, her mother seeks the help of two priests to save her."},
    {"title": "Psycho", "year": 1960, "genre": "horror", "rating": 8.5, "description": "A Phoenix secretary embezzles $40,000 from her employer's client, goes on the run, and checks into a remote motel run by a young man under the domination of his mother."},
    {"title": "The Conjuring", "year": 2013, "genre": "horror", "rating": 7.5, "description": "Paranormal investigators Ed and Lorraine Warren work to help a family terrorized by a dark presence in their farmhouse."},
    {"title": "Taxi Driver", "year": 1976, "genre": "drama", "rating": 8.2, "description": "A mentally unstable Vietnam War veteran works as a night-time taxi driver in New York City where the perceived decadence and sleaze feeds his urge to take action."},
    {"title": "American History X", "year": 1998, "genre": "drama", "rating": 8.5, "description": "A former neo-nazi skinhead tries to prevent his younger brother from going down the same wrong path that he did."},
    {"title": "The Big Lebowski", "year": 1998, "genre": "comedy", "rating": 8.1, "description": "Jeff 'The Dude' Lebowski, mistaken for a millionaire of the same name, seeks restitution for his ruined rug and enlists his bowling buddies to help get it."},
]

async def movie_rec(params: dict) -> dict:
    pool = MOVIES
    genre = params.get("genre", "").lower()
    mood = params.get("mood", "").lower()
    min_rating = params.get("min_rating")
    valid_genres = {"action", "comedy", "drama", "sci-fi", "horror"}
    if genre in valid_genres:
        pool = [m for m in pool if m["genre"] == genre]
    else:
        genre = ""
    if mood:
        pool = [m for m in pool if mood in m["description"].lower() or mood in m["title"].lower()]
    if min_rating is not None:
        try:
            min_rating = float(min_rating)
            pool = [m for m in pool if m["rating"] >= min_rating]
        except (ValueError, TypeError):
            pass
    if not pool:
        return error_response("No movies found matching your criteria")
    return success_response({"movies": pool, "total": len(pool)})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
