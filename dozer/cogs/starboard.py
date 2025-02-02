"""a cog that handles actions around a starboard/hall of fame"""
import datetime
import typing
import discord
from discord.ext.commands import has_permissions, guild_only

from ._utils import *
from ..asyncdb.orm import orm
from ..asyncdb import psqlt


class Starboard(Cog):
    """Various starboard functions."""
    def __init__(self, bot):
        super().__init__(bot)
        self.config_cache = {}

    def starboard_embed_footer(self, emoji=None, reaction_count=None):
        """create the footer for a starboard embed"""
        if emoji and reaction_count:
            return f"{reaction_count} {'reactions' if emoji.startswith('<') else emoji} | "
        else:
            return ""

    def make_starboard_embed(self, msg: discord.Message): #, emoji=None, reaction_count=None):
        """Makes a starboard embed."""
        e = discord.Embed(color=discord.Color.gold())
        e.set_author(name=msg.author.display_name, icon_url=member_avatar_url(msg.author))
        if len(msg.content):
            e.description = msg.content

        # Open question: how do we deal with attachment posts that aren't just an image?
        if len(msg.attachments) > 1:
            e.add_field(name="Attachments:", value="\n".join([a.url for a in msg.attachments[1:]]))
        if len(msg.attachments):
            e.set_image(url=msg.attachments[0].url)

        e.add_field(name="Jump link", value=f"[here]({msg.jump_url})")

        e.set_footer(text=str(msg.guild)) #self.starboard_embed_footer(emoji, reaction_count) + str(msg.guild))
        e.timestamp = datetime.datetime.utcnow()
        return e

    def make_config_embed(self, ctx, title, config):
        """Makes a config embed."""
        e = discord.Embed(title=title, color=discord.Color.gold())
        e.add_field(name="Channel", value=self.bot.get_channel(config.channel_id).mention)
        e.add_field(name="Emoji", value=config.emoji)
        e.add_field(name="Threshold", value=config.threshold)
        e.set_footer(text=f"For more information, try {ctx.prefix}help starboard")
        return e

    async def send_to_starboard(self, config, msg: discord.Message):
        """Sends a message to the starboard; if the message already exists in the starboard, update the reactions count"""
        starboard_channel = msg.guild.get_channel(config.channel_id)
        if starboard_channel is None:
            return
        msg_ent = await StarboardMessage.select_one(message_id=msg.id)
        reaction_count = ([r.count for r in msg.reactions if str(r.emoji) == config.emoji] or [0])[0]

        starboard_msg_content = f"{config.emoji} **{reaction_count}** {starboard_channel.mention} {msg.author.mention}"
        if msg_ent:
            msg_ent.reaction_count = reaction_count
            await msg_ent.update()
            try:
                starboard_msg = await starboard_channel.fetch_message(msg_ent.starboard_message_id)
            except discord.NotFound:
                return
            prev_embed = starboard_msg.embeds[0]
            await starboard_msg.edit(content=starboard_msg_content, embed=prev_embed)
        else:
            starboard_msg = await starboard_channel.send(starboard_msg_content, embed=self.make_starboard_embed(msg))
            msg_ent = StarboardMessage(message_id=msg.id, starboard_message_id=starboard_msg.id, reaction_count=reaction_count)
            await msg_ent.insert(_upsert="ON CONFLICT (message_id) DO UPDATE SET reaction_count=EXCLUDED.reaction_count")

    @Cog.listener()
    async def on_reaction_add(self, reaction, member):
        """Handles core reaction logic."""
        msg = reaction.message
        if not msg.guild:
            return
        if msg.guild.id in self.config_cache:
            config = self.config_cache[msg.guild.id]
        else:
            config = await StarboardConfig.select_one(guild_id=msg.guild.id)
            self.config_cache[msg.guild.id] = config

        # we cache null results for servers
        if config is None:
            return

        if reaction.count >= config.threshold and str(reaction.emoji) == config.emoji and member != msg.guild.me:
            await self.send_to_starboard(config, msg)
        elif reaction.count < config.threshold:
            star_ent = await StarboardMessage.select_one(message_id=msg.id)
            if star_ent is None:
                return
            starboard_channel = msg.guild.get_channel(config.channel_id)
            if starboard_channel is None:
                return
            try:
                starboard_msg = await starboard_channel.fetch_message(star_ent.starboard_message_id)
            except discord.NotFound:
                return
            await starboard_msg.delete()
            await star_ent.delete()

    @Cog.listener()
    async def on_reaction_remove(self, reaction, member):
        """Also handles reaction logic."""
        await self.on_reaction_add(reaction, member)

    @guild_only()
    @group(invoke_without_command=True, case_insensitive=True)
    @bot_has_permissions(embed_links=True)
    async def starboard(self, ctx):
        """Show the current server's starboard configuration.
           A starboard (or a hall of fame) is a channel the bot will repost messages in if they receive a certain number of configured reactions.

           To configure a starboard, use the `starboard config` subcommand.
           """
        config = await StarboardConfig.select_one(guild_id=ctx.guild.id)
        if config:
            await ctx.send(embed=self.make_config_embed(ctx, f"Starboard configuration for {ctx.guild}", config))
        else:
            await ctx.send(f"This server does not have a starboard configured! See `{ctx.prefix}help starboard` for more information.")
    starboard.example_usage = """
    `{prefix}starboard` - Show starboard configuration details.
    `{prefix}starboard config #hall-of-fame 🌟 5` - Set the bot to repost messages that have 5 star reactions to `#hall-of-fame`
    `{prefix}starboard add #channel 1285719825125` - add message with id `1285719825125` in `#channel` to the starboard manually.
    """

    @starboard.command()
    @has_permissions(manage_guild=True, manage_channels=True)
    @bot_has_permissions(add_reactions=True, embed_links=True)
    async def config(self, ctx, channel: discord.TextChannel, emoji: typing.Union[discord.Emoji, str], threshold: int):
        """Change the current starboard settings for the server."""
        try:
            await ctx.message.add_reaction(emoji)
            await ctx.message.remove_reaction(emoji, ctx.guild.me)
        except discord.HTTPException:
            await ctx.send(f"{ctx.author.mention}, bad argument: '{emoji}' is not an emoji!")
            return

        config = await StarboardConfig.select_one(guild_id=ctx.guild.id)
        if config:
            config.channel_id = channel.id
            config.emoji = str(emoji)
            config.threshold = threshold
            await config.update()
        else:
            config = StarboardConfig(guild_id=ctx.guild.id, channel_id=channel.id, emoji=str(emoji), threshold=threshold)
            await config.insert()
        if ctx.guild.id in self.config_cache:
            del self.config_cache[ctx.guild.id]
        await ctx.send(embed=self.make_config_embed(ctx, f"Updated configuration for {ctx.guild}!", config))
    config.example_usage = """
    `{prefix}starboard config #hall-of-fame 🌟 5` - Set the bot to repost messages that have 5 star reactions to `#hall-of-fame`
    """

    @starboard.command()
    @bot_has_permissions(embed_links=True)
    async def add(self, ctx, channel: discord.TextChannel, message_id: int):
        """Manually adds a message to the starboard. Note that the caller must have permissions to send messages to the starboard channel."""
        config = await StarboardConfig.select_one(guild_id=ctx.guild.id)
        if config:
            starboard_channel = ctx.guild.get_channel(config.channel_id)
            if not starboard_channel.permissions_for(ctx.author).send_messages:
                await ctx.send("You don't have permissions to add messages to the starboard channel!")
                return
            elif not starboard_channel.permissions_for(ctx.guild.me).send_messages:
                await ctx.send("I don't have permissions to add messages to the starboard channel!")
                return
        else:
            await ctx.send("This server does not have a starboard configured!")
            return
        try:
            msg = await channel.fetch_message(message_id)
            await self.send_to_starboard(config, msg)
        except discord.NotFound:
            await ctx.send(f"Message ID {message_id} was not found in {channel.mention}!")

        await ctx.send(f"Successfully posted message {message_id} to the starboard!")

    add.example_usage = """
    `{prefix}starboard add #channel 1285719825125` - add message with id `1285719825125` in `#channel` to the starboard manually.
    """


class StarboardConfig(orm.Model):
    """Main starboard server config data"""
    __tablename__ = "starboard_config"
    __primary_key__ = ("guild_id",)
    guild_id: psqlt.bigint
    channel_id: psqlt.bigint
    emoji: psqlt.text
    threshold: psqlt.bigint


class StarboardMessage(orm.Model):
    """Table that lists every starboard message ever"""
    __tablename__ = "starboard_messages"
    __primary_key__ = ("message_id",)
    message_id: psqlt.bigint
    starboard_message_id: psqlt.bigint
    reaction_count: psqlt.bigint


def setup(bot):
    """Add this cog to the main bot."""
    bot.add_cog(Starboard(bot))
