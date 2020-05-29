"""Initializes the bot and deals with the configuration file"""

import json
import os
import sys
import asyncio
import uvloop
from .asyncdb.orm import orm

# switch to uvloop for event loops
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

config = {
    'prefix': '&', 'developers': [],
    'tba': {
        'key': ''
    },
    'toa': {
        'key': 'Put TOA API key here',
        'app_name': 'Dozer',
        'teamdata_url': ''
    },
    'log_level': 'INFO',
    'db_url': 'postgres:///dozer',
    'gmaps_key': "PUT GOOGLE MAPS API KEY HERE",
    'tz_url': '',
    'discord_token': "Put Discord API Token here.",
    'news': {
        'check_interval': 5.0,
        'twitch': {
            'client_id': "Put Twitch Client ID here",
            'client_secret': "Put Twitch Secret Here"
        }
    },
    'debug': False,
    'is_backup': False
}
config_file = 'config.json'

if os.path.isfile(config_file):
    with open(config_file) as f:
        config.update(json.load(f))

with open('config.json', 'w') as f:
    json.dump(config, f, indent='\t')

asyncio.get_event_loop().run_until_complete(db_init(config['db_url']))

if 'discord_token' not in config:
    sys.exit('Discord token must be supplied in configuration - please add one to config.json')

if sys.version_info < (3, 6):
    sys.exit('Dozer requires Python 3.6 or higher to run. This is version %s.' % '.'.join(sys.version_info[:3]))

from . import Dozer  # After version check

bot = Dozer(config)

for ext in os.listdir('dozer/cogs'):
    if not ext.startswith(('_', '.')):
        bot.load_extension('dozer.cogs.' + ext[:-3])  # Remove '.py'

loop = asyncio.get_event_loop()
loop.run_until_complete(orm.connect(dsn=config['db_url']))
loop.run_until_complete(orm.Model.create_all_tables())
bot.run()

# restart the bot if the bot flagged itself to do so
if bot._restarting:
    script = sys.argv[0]
    if script.startswith(os.getcwd()):
        script = script[len(os.getcwd()):].lstrip(os.sep)

    if script.endswith('__main__.py'):
        args = [sys.executable, '-m', script[:-len('__main__.py')].rstrip(os.sep).replace(os.sep, '.')]
    else:
        args = [sys.executable, script]
    os.execv(sys.executable, args + sys.argv[1:])
