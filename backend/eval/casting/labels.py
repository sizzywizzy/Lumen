"""The labelled set, hand-written: a casting brief, and the film and part it came from.

Only the brief is written here. The right answer is not — it is resolved from
TMDb by `run.py resolve`, which looks the film up, finds that character in its
cast and records whoever TMDb says played them. So a lapse of memory on my part
cannot become a wrong label: the worst it can do is fail to resolve, loudly.

**Three words may never appear in a brief**: the actor's name, the film's title
and the character's name. Any of them turns the search into a name lookup and
makes the recall number meaningless — the catch this whole evaluation is built
around. `test_casting_recall.py` checks every brief for all three rather than
trusting that I remembered.

Each brief is written as a casting director would write it: what the part needs,
not what the performance was. Praise ("a towering performance") describes an
actor and would leak; "a man in his fifties who has stopped expecting to be
believed" describes a part, and is the thing a search should be able to serve.

The spread is deliberate — 1991 to 2023, twelve languages, leads and supporting
parts, ages from late teens to seventies, because a set drawn from one decade of
English-language leads would measure one corner of the problem and be quoted as
if it measured the whole.
"""

# (film title, year, character as TMDb spells it, the brief)
LABELS = [
    # ------------------------------------------------------------- thrillers --
    ("The Silence of the Lambs", 1991, "Clarice Starling",
     "A trainee at a federal law-enforcement academy in her late twenties, working class, "
     "sharp and visibly out of her depth among senior men; must hold a two-hander with an "
     "older predator without ever seeming safe. English-speaking."),
    ("Se7en", 1995, "Somerset",
     "A homicide detective a week from retirement, sixty, literate and tired, who has stopped "
     "believing the work changes anything; plays against a hot-headed younger partner. English-speaking."),
    ("No Country for Old Men", 2007, "Anton Chigurh",
     "An implacable killer for hire, forties, foreign-accented, with an unsettling stillness and "
     "a private code he applies to strangers; almost no raised voice. English-speaking."),
    ("Zodiac", 2007, "Robert Graysmith",
     "A newspaper cartoonist in his thirties, boyish and socially awkward, whose obsession with an "
     "unsolved case outlasts everyone else's; eager rather than heroic. English-speaking."),
    ("Prisoners", 2013, "Detective Loki",
     "A young detective, thirties, tightly wound and meticulous, with facial tics and a temper he "
     "keeps just in check; carries a procedural thriller alone. English-speaking."),
    ("Sicario", 2015, "Alejandro",
     "A quiet Latin American operative in his forties attached to a cross-border task force, "
     "courteous and unreadable, with a private motive he never explains. Spanish and English."),
    ("Burning", 2018, "Ben",
     "An affluent, unruffled man in his thirties whose ease with money makes everyone around him "
     "feel poor; charm with something unlit underneath. Korean-speaking."),
    ("Oldboy", 2003, "Oh Dae-su",
     "A man imprisoned in one room for fifteen years without explanation, forties, who comes out "
     "feral and single-minded; heavy physical demands. Korean-speaking."),

    # ---------------------------------------------------------------- drama --
    ("There Will Be Blood", 2007, "Daniel Plainview",
     "A turn-of-the-century oil prospector, forties to fifties, a magnetic public speaker and a "
     "private misanthrope; the film rests entirely on him. English-speaking."),
    ("The Master", 2012, "Freddie Quell",
     "A drifting navy veteran in his thirties, alcoholic and physically coiled, drawn to a "
     "charismatic older man who offers him a system to live by. English-speaking."),
    ("Whiplash", 2014, "Fletcher",
     "A conservatory conductor in his fifties who teaches by humiliation, entirely certain he is "
     "right; needs precise comic timing inside genuine menace. English-speaking."),
    ("Moonlight", 2016, "Juan",
     "A Miami drug dealer in his thirties who becomes an unlikely father figure to a bullied boy; "
     "gentle, watchful, morally compromised. English-speaking."),
    ("Lady Bird", 2017, "Lady Bird McPherson",
     "A Catholic-school senior, seventeen, from a family with no money, who has renamed herself and "
     "is desperate to leave her home town; comic and raw by turns. English-speaking."),
    ("Marriage Story", 2019, "Nora Fanshaw",
     "A Los Angeles divorce lawyer, fifties, expensively warm, who can deliver a four-minute monologue "
     "about the double standard applied to mothers. English-speaking."),
    ("Nomadland", 2020, "Fern",
     "A widow in her sixties living out of a van and taking seasonal work, self-contained and "
     "undramatic; must hold the screen opposite non-professionals. English-speaking."),
    ("First Reformed", 2017, "Ernst Toller",
     "The pastor of a dwindling historic church, fifties, ill and drinking, keeping a journal as his "
     "faith turns to something harder. English-speaking."),
    ("The Wrestler", 2008, "Randy",
     "A professional wrestler twenty years past his fame, fifties, wrecked body, working a deli "
     "counter; enormous physical commitment required. English-speaking."),
    ("Uncut Gems", 2019, "Howard Ratner",
     "A diamond-district jeweller and compulsive gambler, forties, talking over everyone, always one "
     "deal from ruin; relentless verbal energy. English-speaking."),
    ("Michael Clayton", 2007, "Karen Crowder",
     "A corporate general counsel in her forties, rehearsing her own answers in hotel mirrors, "
     "sweating through a decision she is not built for. English-speaking."),
    ("Aftersun", 2022, "Calum",
     "A young father, barely thirty, on a package holiday with his eleven-year-old daughter, "
     "depressed in a way he hides badly from her and well from himself. Scottish, English-speaking."),
    ("The Banshees of Inisherin", 2022, "Colm Doherty",
     "A fiddle player on a small island, sixties, who abruptly and without cruelty ends a lifelong "
     "friendship because he wants to spend what time is left composing. Irish, English-speaking."),
    ("Tár", 2022, "Lydia Tár",
     "A world-famous orchestral conductor, fifties, fluent in German, imperious in a lecture hall and "
     "unravelling in private; must plausibly conduct. English and German."),

    # ------------------------------------------------ genre and spectacle --
    ("Mad Max: Fury Road", 2015, "Imperator Furiosa",
     "A shaven-headed war captain with a prosthetic arm, forties, driving a war rig across a desert; "
     "almost no dialogue, entirely physical. English-speaking."),
    ("Get Out", 2017, "Chris Washington",
     "A Black photographer in his twenties meeting his white girlfriend's family for the first time; "
     "must play mounting unease while staying likeable. English-speaking."),
    ("Arrival", 2016, "Louise Banks",
     "A university linguist in her forties recruited to communicate with something that has landed; "
     "grief carried quietly under procedural work. English-speaking."),
    ("Black Swan", 2010, "Nina Sayers",
     "A ballet dancer in her twenties, technically perfect and terrified, living with a controlling "
     "mother; serious dance ability required. English-speaking."),
    ("Everything Everywhere All at Once", 2022, "Evelyn Wang",
     "A middle-aged laundromat owner and immigrant mother being audited, who turns out to be the least "
     "impressive version of herself across every universe; comedy, martial arts and grief. "
     "Mandarin, Cantonese and English."),
    ("Train to Busan", 2016, "Seok-woo",
     "A self-absorbed fund manager, forties, taking his young daughter on a train journey that becomes "
     "a survival crisis; an arc from selfishness to sacrifice. Korean-speaking."),
    ("Pan's Labyrinth", 2006, "Capitán Vidal",
     "A fascist army captain in 1944, forties, obsessed with his unborn son and his dead father's watch; "
     "immaculate, sadistic, no camp. Spanish-speaking."),
    ("The Favourite", 2018, "Queen Anne",
     "An ailing, gout-ridden queen in her forties, petulant and grieving seventeen lost children, "
     "manipulated by two women at court; comic and pitiable at once. English-speaking."),

    # ----------------------------------------------- world cinema, leads --
    ("Parasite", 2019, "Ki-taek",
     "An unemployed father in his fifties, folding pizza boxes in a semi-basement flat, whose easy "
     "fatalism curdles over the film. Korean-speaking."),
    ("Roma", 2018, "Cleo",
     "A live-in domestic worker in her twenties for a middle-class 1970s family, indigenous, largely "
     "silent, the emotional centre of the film; non-professional acceptable. Spanish and Mixtec."),
    ("Shoplifters", 2018, "Osamu Shibata",
     "A casual labourer in his fifties heading a family that shoplifts to live, teaching a child to "
     "steal with real tenderness. Japanese-speaking."),
    ("Drive My Car", 2021, "Yūsuke Kafuku",
     "A stage actor and director in his late forties, recently widowed, who rehearses a Chekhov "
     "production while being driven each day by a young chauffeur. Japanese-speaking."),
    ("A Separation", 2011, "Nader",
     "A middle-class Tehran husband in his forties caring for a father with dementia, refusing to "
     "leave the country as his marriage ends; stubborn, sympathetic, wrong. Persian-speaking."),
    ("The Lives of Others", 2006, "Gerd Wiesler",
     "A Stasi surveillance officer in his forties, austere and friendless, slowly changed by the "
     "couple he is assigned to listen to; almost affectless. German-speaking."),
    ("City of God", 2002, "Zé Pequeno / Dadinho",
     "A young gang leader in a Rio favela, early twenties, gleeful and pitiless, who came up from "
     "nothing; non-professional acceptable. Portuguese-speaking."),
    ("A Prophet", 2009, "Malik El Djebena",
     "An illiterate nineteen-year-old of Algerian descent entering a French prison, who learns to read, "
     "to speak Corsican and to run things. French and Arabic."),
    ("Amélie", 2001, "Amélie Poulain",
     "A Montmartre waitress in her twenties, solitary and whimsical, who arranges other people's "
     "happiness while avoiding her own; direct address to camera. French-speaking."),
    ("Portrait of a Lady on Fire", 2019, "Marianne",
     "A painter in her late twenties in 1770 Brittany, sent to paint a portrait in secret and falling "
     "for her subject; contained, watchful. French-speaking."),
    ("Son of Saul", 2015, "Saul Ausländer",
     "A Hungarian Jewish prisoner forced to work in a death camp's crematoria, forties, shot almost "
     "entirely in close-up on his face. Hungarian and Yiddish."),
    ("Ida", 2013, "Wanda",
     "A hard-drinking state judge in 1960s Poland, fifties, who tells her novice niece the truth about "
     "their family; caustic, black-and-white, spare. Polish-speaking."),
    ("Cold War", 2018, "Zula",
     "A Polish folk singer from a rough background, twenties into forties, whose affair with a musician "
     "spans fifteen years and two sides of a border; must sing. Polish-speaking."),
    ("The Handmaiden", 2016, "Sook-hee",
     "A young pickpocket placed as a handmaiden to a Japanese heiress in colonial Korea as part of a "
     "con, twenties, who falls for her mark. Korean and Japanese."),
    ("Y Tu Mamá También", 2001, "Tenoch Iturbide",
     "A privileged Mexico City teenager on a road trip with his best friend and an older woman, "
     "seventeen, all bravado and no idea. Spanish-speaking."),
    ("The Farewell", 2019, "Billi",
     "A Chinese-American woman in her early thirties who returns to Changchun for a staged wedding, "
     "the family having hidden a terminal diagnosis from her grandmother. Mandarin and English."),
    ("Past Lives", 2023, "Nora",
     "A Korean-Canadian playwright in her thirties in New York, reunited after twenty-four years with "
     "a childhood friend from Seoul; enormous restraint. Korean and English."),
    ("Minari", 2020, "Soonja",
     "A Korean grandmother in her seventies who arrives to live with her daughter's family on an "
     "Arkansas farm, profane, card-playing and nothing like a grandmother should be. Korean-speaking."),
    ("Anatomy of a Fall", 2023, "Sandra Voyter",
     "A German novelist in her forties living in the French Alps, on trial for her husband's death, "
     "giving evidence in a second language she is losing patience with. French, German and English."),
    ("The Zone of Interest", 2023, "Hedwig Höss",
     "The wife of a camp commandant, thirties, running a beautiful garden and household against a wall, "
     "proud of her home and entirely incurious. German-speaking."),
    ("RRR", 2022, "Komaram Bheem",
     "A tribal guardian in 1920s India, thirties, immense physical presence, who goes undercover in the "
     "city to recover a child taken by the British. Telugu-speaking."),
    ("Monsoon Wedding", 2001, "Lalit Verma",
     "A Delhi father of the bride, fifties, stressed about the cost of the wedding and eventually forced "
     "to confront something in his own family. Hindi and English."),
]
