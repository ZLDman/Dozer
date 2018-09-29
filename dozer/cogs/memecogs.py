from ._utils import *

import random
import discord


class MemeCog(Cog):
    pass


class OofboticsCog(MemeCog):
    guild_id = 433993458928058368

    async def on_message(self, msg):
        if msg.guild.id != self.guild_id:
            return
        if msg.author.id == 407204519190069258: # zihao lmao
            if random.randint(0, 100) == 28:
                await self.bot.cogs["Moderation"]._mute(msg.author, reason="because", seconds=120, orig_channel=msg.channel)


def setup(bot):
    for cog in [OofboticsCog]:
        bot.add_cog(cog(bot))