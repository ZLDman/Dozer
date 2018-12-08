"""Plowie-specific cog functionality"""
import discord
from discord.ext.commands import BadArgument, guild_only

from ._utils import *
from .. import db


class Plowie(Cog):
    """Plowie-specific cog functionality"""

    async def on_ready(self):
        """Update bot status to remain accurate."""

    async def on_guild_join(self, guild):  # pylint: disable=unused-argument
        """Update bot status to remain accurate."""

    async def on_guild_remove(self, guild):  # pylint: disable=unused-argument
        """Update bot status to remain accurate."""

    async def on_member_join(self, member):
        """pass"""

    async def on_member_leave(self, member):
        """pass"""


def setup(bot):
    """bot setup, just like every other cog!"""
    bot.add_cog(Plowie(bot))
