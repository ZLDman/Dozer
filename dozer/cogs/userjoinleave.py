import discord
from discord.ext.commands import BadArgument, guild_only

from ._utils import *
from .. import db

class UserJoinLeave(Cog):
    def __init__(self, bot):
        super().__init__(bot)
        #bot.get_cog("Teams").on_member_join = None

    async def on_member_join(self, member):
        pass

    async def on_member_leave(self, member):
        pass

def setup(bot):
    bot.add_cog(UserJoinLeave(bot))
"""
class MemberTable(db.DatabaseObject):
    id = db.Column(db.Integer, primary_key=True)
    guild_id = db.Column(db.Integer, primary_key=True)
    meta = db.Column(db.String, nullable=True)
"""