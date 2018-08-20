import discord
from discord.ext.commands import BadArgument, guild_only

from ._utils import *
from .. import db

class Plowie(Cog):
    def __init__(self, bot):
        super().__init__(bot)

    async def update_status(self):
        game = discord.Game(name='%splowie | %d guilds' % (self.bot.config['prefix'], len(self.bot.guilds)))
        await self.bot.change_presence(activity=game)

    async def line_print(self, ctx: discord.abc.Messageable, title, iterable, color=discord.Color.default()):
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
        await self.update_status()

    async def on_guild_join(self, guild):
        await self.update_status()

    async def on_guild_remove(self, guild):
        await self.update_status()

    async def on_member_join(self, member):
        pass

    async def on_member_leave(self, member):
        pass


    @command()
    async def plowie(self, ctx):
        """Display Plowie-specific info"""
        e = discord.Embed(title="Plowie", description=f"Dozer for the masses (build )", color=discord.Color.blue())
        e.set_thumbnail(url=self.bot.user.avatar_url)
        e.add_field(name="About", value="Plowie is a fork of Dozer by the FRC Discord Development Team run by @guineawheek#5381, with a few extras tacked on and less stringent server requirements, making it suitable for personal servers. ")
        e.add_field(name="Extra features", value="So far, Plowie offers `%afk`, and the timed mutes/deafens subsystem is much more robust. This bot may occasionally get features before they are merged into upstream Dozer. ")
        e.add_field(name="Support", value="`%help` provides the general command reference; for special inquiries/feature requests contact @guineawheek#5381. Feature requests can be server specific.")
        e.add_field(name="Code", value="Check out the code [here!](https://github.com/guineawheek/Dozer/tree/plowie)")
        e.add_field(name="Invite link", value="Want to add Plowie to your server? [Click here!](https://discordapp.com/oauth2/authorize?client_id=474456308813266945&scope=bot&permissions=502656071)")
        await ctx.send(embed=e)

    async def listservers(self, ctx):
        """Lists the servers that Plowie is in."""
        await self.line_print(ctx, "List of servers:", self.bot.guilds, color=discord.Color.blue())

def setup(bot):
    bot.add_cog(Plowie(bot))
