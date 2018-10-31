# pylint: skip-file
import random
from ._utils import *
import discord


class MemeCog(Cog):
    pass


class OofboticsCog(MemeCog):
    guild_id = 433993458928058368

    async def on_message(self, msg):
        if msg.guild.id != self.guild_id:
            return
        if msg.author.id == 434835322501726208:
            if random.randint(0, 50) == 14:
                await self.bot.cogs["Moderation"]._mute(msg.author, reason="zihao", seconds=120, orig_channel=msg.channel)


def setup(bot):
    for cog in [OofboticsCog]:
        bot.add_cog(cog(bot))
