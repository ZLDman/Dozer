# pylint: skip-file
import random
from ._utils import *
import discord


class MemeCog(Cog):
    pass


class OofboticsCog(MemeCog):
    guild_id = 433993458928058368

    async def on_message(self, msg):
        if not msg.guild or msg.guild.id != self.guild_id:
            return
        if msg.author.id == 434835322501726208:
            moderation = self.bot.cogs["Moderation"]
            if random.randint(0, 50) == 14:
                if await moderation._mute(msg.author, reason="zihao", seconds=120, orig_channel=msg.channel):
                    await moderation.mod_log(msg.guild.me, "muted", msg.author, "zihao", msg.channel, discord.Color.red())


def setup(bot):
    for cog in [OofboticsCog]:
        bot.add_cog(cog(bot))
