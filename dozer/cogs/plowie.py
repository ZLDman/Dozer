"""Plowie-specific cog functionality"""
import discord
from discord.ext.commands import BadArgument, guild_only

from ._utils import *
from .. import db


class Plowie(Cog):
    """Plowie-specific cog functionality"""

    async def update_status(self):
        """Dynamically update the bot's status."""
        game = discord.Game(name='%help | %d guilds' % (self.bot.config['prefix'], len(self.bot.guilds)))
        await self.bot.change_presence(activity=game)

    async def line_print(self, ctx: discord.abc.Messageable, title, iterable, color=discord.Color.default()):
        """Prints out the contents of an iterable into an embed and sends it. Can handle long iterables."""
        buf = ""
        embed_buf = []
        for i in map(str, iterable):
            if len(buf) + len(i) + 1 > 2048:
                embed_buf.append(buf)
                buf = ""
            buf += i + "\n"
        embed_buf.append(buf)
        first = True
        for i in embed_buf:
            if first:
                await ctx.send(embed=discord.Embed(title=title, description=i, color=color))
                first = False
            else:
                await ctx.send(embed=discord.Embed(description=i, color=color))

    async def on_ready(self):
        """Update bot status to remain accurate."""
        await self.update_status()

    async def on_guild_join(self, guild):  # pylint: disable=unused-argument
        """Update bot status to remain accurate."""
        await self.update_status()

    async def on_guild_remove(self, guild):  # pylint: disable=unused-argument
        """Update bot status to remain accurate."""
        await self.update_status()

    async def on_member_join(self, member):
        """pass"""
        pass

    async def on_member_leave(self, member):
        """pass"""
        pass

    async def listservers(self, ctx):
        """Lists the servers that Plowie is in."""
        await self.line_print(ctx, "List of servers:", self.bot.guilds, color=discord.Color.blue())

def setup(bot):
    """bot setup, just like every other cog!"""
    bot.add_cog(Plowie(bot))
