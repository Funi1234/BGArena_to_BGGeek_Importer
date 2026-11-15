"""Convert BGA player results to BGG player records."""


def build_player_data(game, config):
    """Map player identities and preserve BGA's first-place results, including ties."""
    results = game.get('player_details', [])
    players = []
    for result in results:
        name = result['name']
        username = None
        if name == config.bga_username:
            name = config.bgg_username
            username = config.bgg_username
        elif name in config.player_mappings:
            name = config.player_mappings[name]
            username = name
        player = {'name': name, 'username': username, 'score': result.get('score')}
        if result.get('rank') == 1:
            player['win'] = True
        players.append(player)
    if not any(p['name'] == config.bgg_username for p in players):
        players.insert(0, {'name': config.bgg_username, 'username': config.bgg_username, 'score': None})
    return players
