"""Curated backtest universe of retired LEGO sets.

Selection criteria:
- Retired between 2021-2024 (enables 12-36 month hold horizon testing)
- Mix of appreciation winners and flat/declining losers
- Distributed across 10+ themes and 4 price tiers
- ~200 sets for statistical significance (target: 500+ trade samples)

Set numbers are BrickLink-compatible (without -1 suffix).
The bootstrap script appends "-1" when writing to bricklink_items.
"""

# Price tiers:
#   S = Small (<$50 RRP)
#   M = Medium ($50-$150)
#   L = Large ($150-$400)
#   XL = Flagship ($400+)

BACKTEST_SETS: tuple[str, ...] = (
    # =========================================================================
    # Star Wars (30 sets -- highest collector demand theme)
    # =========================================================================
    # XL flagships (strong appreciation expected)
    "75192",  # Millennium Falcon (UCS), $849
    "75252",  # Imperial Star Destroyer (UCS), $699
    "75313",  # AT-AT (UCS), $799
    "75309",  # Republic Gunship (UCS), $349
    "75341",  # Luke's Landspeeder (UCS), $239
    # L sets
    "75290",  # Mos Eisley Cantina, $349
    "75318",  # The Child (Mandalorian), $79
    "75244",  # Tantive IV, $199
    "75292",  # Razor Crest, $129
    "75314",  # Bad Batch Attack Shuttle, $99
    "75316",  # Mandalorian Starfighter, $59
    "75312",  # Boba Fett's Starship, $49
    "75315",  # Imperial Light Cruiser, $159
    "75322",  # Hoth AT-ST, $49
    "75320",  # Snowtrooper Battle Pack, $15
    # M/S sets (mixed -- many losers due to oversupply)
    "75319",  # Mandalorian Forge, $29
    "75317",  # Mandalorian & The Child BrickHeadz, $19
    "75299",  # Trouble on Tatooine, $29
    "75300",  # Imperial TIE Fighter, $39
    "75301",  # Luke's X-Wing Fighter, $49
    "75302",  # Imperial Shuttle, $69
    "75304",  # Darth Vader Helmet, $69
    "75305",  # Scout Trooper Helmet, $49
    "75306",  # Imperial Probe Droid, $59
    "75308",  # R2-D2, $239
    "75324",  # Dark Trooper Attack, $29
    "75325",  # Mandalorian's N-1 Starfighter, $59
    "75326",  # Boba Fett's Throne Room, $99
    "75328",  # Mandalorian Helmet, $59
    "75335",  # BD-1, $99

    # =========================================================================
    # Creator Expert / Icons (25 sets -- modular + display sets)
    # =========================================================================
    # Modular buildings (historically strong appreciation)
    "10270",  # Bookshop, $179
    "10278",  # Police Station, $199
    "10297",  # Boutique Hotel, $199
    "10264",  # Corner Garage, $199
    # Vehicles
    "10265",  # Ford Mustang, $149
    "10271",  # Fiat 500, $89
    "10295",  # Porsche 911, $149
    "10300",  # Back to the Future DeLorean, $169
    "10304",  # Chevrolet Camaro Z28, $169
    # Botanicals / Display
    "10280",  # Flower Bouquet, $49
    "10281",  # Bonsai Tree, $49
    "10289",  # Bird of Paradise, $99
    "10311",  # Orchid, $49
    "10313",  # Wildflower Bouquet, $49
    "10314",  # Dried Flower Centerpiece, $49
    "10309",  # Succulents, $49
    # Icons
    "10283",  # NASA Discovery Shuttle, $199
    "10282",  # adidas Originals Superstar, $89
    "10284",  # Camp Nou - FC Barcelona, $349
    "10293",  # Santa's Visit, $99
    "10294",  # Titanic, $629
    "10298",  # Vespa 125, $99
    "10299",  # Real Madrid Santiago Bernabeu, $349
    "10306",  # Atari 2600, $239
    "10307",  # Eiffel Tower, $629
    "10312",  # Jazz Club, $229

    # =========================================================================
    # Ideas (20 sets -- unique designs, variable appreciation)
    # =========================================================================
    "21322",  # Pirates of Barracuda Bay, $199
    "21323",  # Grand Piano, $349
    "21325",  # Medieval Blacksmith, $149
    "21326",  # Winnie the Pooh, $99
    "21327",  # Typewriter, $199
    "21328",  # Seinfeld, $79
    "21329",  # Fender Stratocaster, $99
    "21330",  # Home Alone, $249
    "21331",  # Sonic the Hedgehog, $69
    "21332",  # The Globe, $199
    "21333",  # Van Gogh Starry Night, $169
    "21334",  # Jazz Quartet, $99
    "21335",  # Motorised Lighthouse, $299
    "21336",  # The Office, $119
    "21337",  # Table Football, $249
    "21338",  # A-Frame Cabin, $179
    "21339",  # BTS Dynamite, $99
    "21340",  # Tales of the Space Age, $49
    "21341",  # Disney Hocus Pocus, $229
    "21343",  # Viking Village, $139

    # =========================================================================
    # Architecture (10 sets -- steady appreciation, niche collector base)
    # =========================================================================
    "21054",  # The White House, $99
    "21056",  # Taj Mahal, $119
    "21057",  # Singapore, $59
    "21058",  # Great Pyramid of Giza, $129
    "21060",  # Himeji Castle, $139
    "21061",  # Notre-Dame de Paris, $229
    "21042",  # Statue of Liberty, $119
    "21044",  # Paris, $49
    "21051",  # Tokyo, $59
    "21052",  # Dubai, $59

    # =========================================================================
    # Technic (20 sets -- varies widely by theme/license)
    # =========================================================================
    "42083",  # Bugatti Chiron, $349
    "42096",  # Porsche 911 RSR, $149
    "42110",  # Land Rover Defender, $199
    "42111",  # Dom's Dodge Charger, $99
    "42115",  # Lamborghini Sian, $379
    "42125",  # Ferrari 488 GTE, $49
    "42126",  # Ford F-150 Raptor, $99
    "42127",  # Batman - Batmobile, $89
    "42128",  # Heavy-Duty Tow Truck, $159
    "42129",  # 4x4 Mercedes G 500, $199
    "42130",  # BMW M 1000 RR, $229
    "42131",  # Cat D11 Bulldozer, $449
    "42140",  # Transformation Vehicle, $44
    "42141",  # McLaren Formula 1, $179
    "42143",  # Ferrari Daytona SP3, $449
    "42145",  # Airbus H175 Rescue Helicopter, $209
    "42151",  # Bugatti Bolide, $49
    "42152",  # Firefighter Aircraft, $59
    "42153",  # NASCAR Camaro ZL1, $29
    "42155",  # The Batman - Batcycle, $9

    # =========================================================================
    # Harry Potter (15 sets -- licensed theme, decent collector demand)
    # =========================================================================
    "75969",  # Hogwarts Astronomy Tower, $99
    "75978",  # Diagon Alley, $399
    "75979",  # Hedwig, $39
    "75980",  # Attack on the Burrow, $99
    "76389",  # Hogwarts Chamber of Secrets, $139
    "76391",  # Hogwarts Icons, $249
    "76393",  # Harry & Hermione, $39
    "76405",  # Hogwarts Express Collectors, $499
    "76407",  # Shrieking Shack & Whomping Willow, $89
    "76408",  # 12 Grimmauld Place, $119
    "76388",  # Hogsmeade Village Visit, $79
    "76392",  # Hogwarts Wizard Chess, $69
    "76394",  # Fawkes Dumbledore Phoenix, $39
    "76395",  # Hogwarts First Flying Lesson, $29
    "76396",  # Hogwarts Divination Class, $29

    # =========================================================================
    # Marvel / DC (15 sets -- superhero theme, mixed results)
    # =========================================================================
    "76178",  # Daily Bugle, $349
    "76218",  # Sanctum Sanctorum, $249
    "76209",  # Thor's Hammer, $99
    "76161",  # 1989 Batwing, $199
    "76183",  # Batcave The Riddler Face-off, $79
    "76181",  # Batmobile: The Penguin Chase, $29
    "76179",  # Batman & Selina Kyle Motorcycle, $9
    "76215",  # Black Panther, $349
    "76210",  # Iron Man Hulkbuster, $549
    "76240",  # Batmobile Tumbler, $269
    "76391",  # Hogwarts Icons Collectors, $249
    "76219",  # Spider-Man & Green Goblin, $19
    "76187",  # Venom, $69
    "76188",  # Batman Classic TV Series Batmobile, $29
    "76239",  # Batmobile Tumbler: Scarecrow, $39

    # =========================================================================
    # City / Classic / Other (15 sets -- mass market, often losers)
    # =========================================================================
    "60337",  # Express Passenger Train, $189
    "60336",  # Freight Train, $199
    "60197",  # Passenger Train, $159
    "60198",  # Cargo Train, $229
    "60295",  # Stunt Show Arena, $79
    "60351",  # Rocket Launch Center, $149
    "31120",  # Medieval Castle, $99
    "31141",  # Main Street, $109
    "31109",  # Pirate Ship, $99
    "43222",  # Disney Castle, $399
    "43197",  # The Ice Castle, $219
    "71741",  # Ninjago City Gardens, $299
    "71764",  # Ninja Training Center, $49
    "71395",  # Super Mario 64 ? Block, $169
    "71374",  # NES, $229

    # =========================================================================
    # Niche themes (10 sets -- expected losers/underperformers for balance)
    # =========================================================================
    "40499",  # Santa's Sleigh, $34
    "40554",  # Jake Sully & his Avatar, $19
    "40566",  # Ray the Castaway, $14
    "40586",  # Moving Truck, $14
    "41703",  # Friendship Tree House (Friends), $69
    "41704",  # Main Street Building (Friends), $109
    "41757",  # Botanical Garden (Friends), $99
    "42160",  # Audi RS Q e-tron (Technic small), $29
    "71360",  # Super Mario Starter Course, $59
    "71387",  # Luigi Starter Course, $59
)
