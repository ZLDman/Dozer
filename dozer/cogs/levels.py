import discord
from discord.ext.commands import BadArgument, cooldown, BucketType, Group, has_permissions


from ._utils import *


class Levels(Cog):

    async def on_message(self, message):
        # i am far too lazy to work on this lmao
        pass


def setup(bot):
    bot.add_cog(Levels(bot))
