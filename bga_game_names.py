"""Mapping of BGA internal game names to human-readable display names.

This is needed because BGA's internal game names (e.g., 'sevenwondersdice')
don't match the actual game titles (e.g., '7 Wonders Dice'), and we can't
reliably scrape the display names from BGA's website programmatically.
"""

from typing import Optional

# Mapping of BGA internal names to display names and optional BGG IDs
# Format: "bga_name": ("Display Name", bgg_id or None)
BGA_GAME_NAMES = {
    # Popular games
    "arknova": ("Ark Nova", 342942),
    "sevenwonders": ("7 Wonders", 68448),
    "sevenwondersdice": ("7 Wonders Dice", 446231),
    "wingspan": ("Wingspan", 266192),
    "azul": ("Azul", 230802),
    "splendor": ("Splendor", 148228),
    "carcassonne": ("Carcassonne", 822),
    "tickettoride": ("Ticket to Ride", 9209),
    "catan": ("Catan", 13),
    "catannewenergies": ("Catan: New Energies", 406399),
    "kingdomino": ("Kingdomino", 204583),
    "sushigo": ("Sushi Go!", 133473),
    "patchwork": ("Patchwork", 163412),
    "pandemic": ("Pandemic", 30549),
    "jaipur": ("Jaipur", 54043),
    "hanabi": ("Hanabi", 98778),
    "lostcities": ("Lost Cities", 50),
    "jumpdrive": ("Jump Drive", 205597),
    "raceforthe galaxy": ("Race for the Galaxy", 28143),
    "throughtheages": ("Through the Ages: A New Story of Civilization", 182028),
    "agricola": ("Agricola", 31260),
    "terramystica": ("Terra Mystica", 120677),
    "brass": ("Brass: Birmingham", 224517),
    "greatwesterntrail": ("Great Western Trail", 193738),
    "gaia": ("Gaia Project", 220308),
    "ares": ("Terraforming Mars: Ares Expedition", 328871),
    "terraformingmars": ("Terraforming Mars", 167791),
    "scythe": ("Scythe", 169786),
    "stonespinedesertwhisperers": ("Stonespine Architects", 322925),
    "seasonsofrice": ("Seasons of Rice", 353316),
    "cannonades": ("Cannonades", 348776),
    "tipperary": ("Tipperary", 370245),
    "mlem": ("MLEM: Space Agency", 332686),
    "heat": ("Heat: Pedal to the Metal", 366013),
    "clans": ("Clans of Caledonia", 216132),
    "barrage": ("Barrage", 251247),
    "parks": ("PARKS", 266524),
    "cascadia": ("Cascadia", 295947),
    "explorers": ("Explorers of the North Sea", 176371),
    "raiders": ("Raiders of the North Sea", 170042),
    "architects": ("Architects of the West Kingdom", 236457),
    "paladins": ("Paladins of the West Kingdom", 266810),
    "viticulture": ("Viticulture Essential Edition", 183394),
    "everdell": ("Everdell", 199792),
    "santorini": ("Santorini", 194655),
    "onitama": ("Onitama", 160477),
    "takenoko": ("Takenoko", 70919),
    "kingdombuilder": ("Kingdom Builder", 107529),
    "downtownabbey": ("Downton Abbey", 358035),
    "seasons": ("Seasons", 108745),
    "smallworld": ("Small World", 40692),
    "dicethrone": ("Dice Throne", 216459),
    "tokaido": ("Tokaido", 123540),
    "century": ("Century: Spice Road", 209685),
    "inventions": ("Inventions: Evolution of Ideas", 324015),
    "loco": ("Loco Momo", 296534),
    "quoridor": ("Quoridor", 624),
    "coloretto": ("Coloretto", 5782),
    "rally": ("Rallyman: GT", 256589),
    "quantum": ("Quantum", 143519),
    "flamme": ("Flamme Rouge", 199478),
    "coup": ("Coup", 131357),
    "conspiracy": ("Conspiracy: Abyss Universe", 278718),
    "ninetynine": ("Ninety-Nine", 5604),
    "homesteaders": ("Homesteaders", 26566),
}


def get_display_name(bga_name: str) -> str:
    """Get display name for a BGA game.

    Args:
        bga_name: BGA internal game name

    Returns:
        Human-readable display name
    """
    if bga_name in BGA_GAME_NAMES:
        return BGA_GAME_NAMES[bga_name][0]

    # Fallback: humanize the name
    import re
    # Insert space before capital letters
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', bga_name)
    # Capitalize each word
    return ' '.join(word.capitalize() for word in spaced.split())


def get_bgg_id(bga_name: str) -> Optional[int]:
    """Get BGG ID for a BGA game if known.

    Args:
        bga_name: BGA internal game name

    Returns:
        BGG ID or None if not known
    """
    if bga_name in BGA_GAME_NAMES:
        return BGA_GAME_NAMES[bga_name][1]
    return None
