"""Role management commands."""

import discord
import discord.utils
from discord.ext.commands import cooldown, BucketType, has_permissions, BadArgument, MissingPermissions

from ._utils import *
from ..asyncdb.orm import orm
from ..asyncdb import psqlt



class Roles(Cog):
    """Commands for role management."""

    def __init__(self, bot):
        super().__init__(bot)
        for command in self.giveme.walk_commands():
            @command.before_invoke
            async def givemeautopurge(self, ctx):
                """Before invoking a giveme command, run a purge"""
                if await self.ctx_purge(ctx):
                    await ctx.send("Purged missing roles")

    @staticmethod
    def normalize(name):
        """Normalizes a role for consistency in the DB."""
        return name.strip().casefold()

    @Cog.listener('on_member_join')
    async def on_member_join(self, member):
        """Restores a member's roles when they join if they have joined before."""
        if 'silent' in self.bot.config and self.bot.config['silent']:
            return

        me = member.guild.me
        top_restorable = me.top_role.position if me.guild_permissions.manage_roles else 0

        missing_roles = await MissingRole.select(guild_id=member.guild.id, member_id=member.id)
        # no missing rules to return
        if not missing_roles:
            return

        valid, cant_give, missing = set(), set(), set()
        for missing_role in missing_roles:
            role = member.guild.get_role(missing_role.role_id)
            if role is None:  # Role with that ID does not exist
                missing.add(missing_role.role_name)
            elif role.position > top_restorable:
                cant_give.add(role.name)
            else:
                valid.add(role)

        await member.add_roles(*valid)
        if not missing and not cant_give:
            return

        e = discord.Embed(title=f'Welcome back to the {member.guild.name} server, {member}!', color=discord.Color.blue())
        if missing:
            e.add_field(name='I couldn\'t restore these roles, as they don\'t exist.', value='\n'.join(sorted(missing)))
        if cant_give:
            e.add_field(name='I couldn\'t restore these roles, as I don\'t have permission.',
                        value='\n'.join(sorted(cant_give)))

        # let's also make regiving roles atomic...ish.
        async with orm.acquire() as conn:
            for missing_role in missing_roles:
                await missing_role.delete(_conn=conn)

        # mmmm i love questionable code i didn't write.
        send_perms = discord.Permissions()
        send_perms.update(send_messages=True, embed_links=True)
        try:
            dest = next(channel for channel in member.guild.text_channels if channel.permissions_for(me) >= send_perms)
        except StopIteration:
            dest = await member.guild.owner.create_dm()

        await dest.send(embed=e)

    @Cog.listener('on_member_remove')
    async def on_member_remove(self, member):
        """Saves a member's roles when they leave in case they rejoin."""
        guild_id = member.guild.id
        member_id = member.id
        async with orm.acquire() as conn:
            for role in member.roles[1:]:  # Exclude the @everyone role
                await MissingRole(role_id=role.id, role_name=role.name,
                                  member_id=member_id, guild_id=guild_id).insert(_upsert="ON CONFLICT DO NOTHING", _conn=conn)

    async def giveme_purge(self, role_id_list):
        """Purges roles in the giveme database that no longer exist"""
        if not role_id_list:
            return
        async with orm.acquire() as conn:
            await conn.fetch(f"DELETE FROM {GiveableRole.table_name()} "
                             f"WHERE role_id=ANY({','.join('$' + str(i + 1) for i in range(len(role_id_list)))})", role_id_list)

    async def ctx_purge(self, ctx):
        """Purges all giveme roles that no longer exist in a guild"""
        counter = 0
        roles = await GiveableRole.select(guild_id=ctx.guild.id)
        guild_roles = []
        role_id_list = []
        for i in ctx.guild.roles:
            guild_roles.append(i.id)
        for ent in roles:
            if ent.role_id not in guild_roles:
                role_id_list.append(ent.role_id)
                counter += 1
        await self.giveme_purge(role_id_list)
        return counter

    @Cog.listener("on_guild_role_delete")
    async def on_guild_role_delete(self, role):
        """Automatically delete giveme roles if they are deleted from the guild"""
        rolelist = [role.id]
        await self.giveme_purge(rolelist)

    @group(invoke_without_command=True)
    @bot_has_permissions(manage_roles=True)
    async def giveme(self, ctx, *, roles):
        """Give you one or more giveable roles, separated by commas."""
        norm_names = set(self.normalize(name) for name in roles.split(','))

        giveable_ids = set(gr.role_id for gr in await GiveableRole.select(guild_id=ctx.guild.id))
        valid = set(role for role in ctx.guild.roles if role.id in giveable_ids and self.normalize(role.name) in norm_names)

        already_have = valid & set(ctx.author.roles)
        given = valid - already_have
        await ctx.author.add_roles(*given)

        e = discord.Embed(color=discord.Color.blue())
        if given:
            given_names = sorted((role.name for role in given), key=str.casefold)
            e.add_field(name='Gave you {} role(s)!'.format(len(given)), value='\n'.join(given_names), inline=False)
        if already_have:
            already_have_names = sorted((role.name for role in already_have), key=str.casefold)
            e.add_field(name='You already have {} role(s)!'.format(len(already_have)),
                        value='\n'.join(already_have_names), inline=False)
        extra = len(norm_names) - len(valid)
        if extra > 0:
            e.add_field(name='{} role(s) could not be found!'.format(extra),
                        value='Use `{0.prefix}{0.invoked_with} list` to find valid giveable roles!'.format(ctx),
                        inline=False)
        await ctx.send(embed=e)

    giveme.example_usage = """
    `{prefix}giveme Java` - gives you the role called Java, if it exists
    `{prefix}giveme Java, Python` - gives you the roles called Java and Python, if they exist
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def purge(self, ctx):
        """Force a purge of giveme roles that no longer exist in the guild"""
        counter = await self.ctx_purge(ctx)
        await ctx.send("Purged {} role(s)".format(counter))

    @cooldown(1, 10, BucketType.channel)
    @giveme.group(name='list', invoke_without_command=True)
    @bot_has_permissions(manage_roles=True)
    async def list_roles(self, ctx):
        """Lists all giveable roles for this server."""
        names = [ctx.guild.get_role(ent.role_id).name for ent in await GiveableRole.select(guild_id=ctx.guild.id)]
        e = discord.Embed(title='Roles available to self-assign', color=discord.Color.blue())
        e.description = '\n'.join(sorted(names, key=str.casefold))
        await ctx.send(embed=e)

    list_roles.example_usage = """
    `{prefix}giveme list` - lists all giveable roles
    """

    @list_roles.command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def add(self, ctx, role: discord.Role):
        """Makes an existing role giveable, or creates one if it doesn't exist. Name must not contain commas.
        Similar to create, but will use an existing role if one exists."""
        if ',' in role.name:
            raise BadArgument('giveable role names must not contain commas!')
        norm_name = self.normalize(role.name)

        if await GiveableRole.select_one(role_id=role.id):
            raise BadArgument('that role already exists and is giveable!')
        candidates = [role for role in ctx.guild.roles if self.normalize(role.name) == norm_name]

        if len(candidates) > 1:
            raise BadArgument('{} roles with that name exist!'.format(len(candidates)))

        await GiveableRole(role_id=role.id, guild_id=ctx.guild.id).insert()
        await ctx.send(f'Role "{role.name}" added! Use `{ctx.prefix}giveme {role.name}` to get it!')

    add.example_usage = """
    `{prefix}giveme list add Java` - creates or finds a role named "Java" and makes it giveable
    `{prefix}giveme Java` - gives you the Java role that was just found or created
    """

    @list_roles.command(name="remove")
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_guild=True)
    async def removefromlist(self, ctx, role: discord.Role):
        """Deletes and removes a giveable role."""

        norm_name = self.normalize(role.name)
        ent = await GiveableRole.select_one(role_id=role.id)
        if ent is None:
            raise BadArgument('that role does not exist or is not giveable!')
        await ent.delete()

        await ctx.send('Role "{0}" deleted from list!'.format(role.name))

    removefromlist.example_usage = """
    `{prefix}giveme list remove Java` - removes the role "Java" from the list of giveable roles but does not remove it from the server or members who have it 
    """

    @giveme.command()
    @bot_has_permissions(manage_roles=True)
    async def remove(self, ctx, *, roles):
        """Removes multiple giveable roles from you. Names must be separated by commas."""
        norm_names = [self.normalize(name) for name in roles.split(',')]
        giveable_ids = set(gr.role_id for gr in await GiveableRole.select(guild_id=ctx.guild.id))
        valid = set(role for role in ctx.guild.roles if role.id in giveable_ids and self.normalize(role.name) in norm_names)

        removed = valid & set(ctx.author.roles)
        dont_have = valid - removed
        await ctx.author.remove_roles(*removed)

        e = discord.Embed(color=discord.Color.blue())
        if removed:
            removed_names = sorted((role.name for role in removed), key=str.casefold)
            e.add_field(name='Removed {} role(s)!'.format(len(removed)), value='\n'.join(removed_names), inline=False)
        if dont_have:
            dont_have_names = sorted((role.name for role in dont_have), key=str.casefold)
            e.add_field(name='You didn\'t have {} role(s)!'.format(len(dont_have)), value='\n'.join(dont_have_names),
                        inline=False)
        extra = len(norm_names) - len(valid)
        if extra > 0:
            e.add_field(name='{} role(s) could not be found!'.format(extra),
                        value='Use `{0.prefix}giveme list` to find valid giveable roles!'.format(ctx),
                        inline=False)
        await ctx.send(embed=e)

    remove.example_usage = """
    `{prefix}giveme remove Java` - removes the role called "Java" from you (if it can be given with `{prefix}giveme`)
    `{prefix}giveme remove Java, Python` - removes the roles called "Java" and "Python" from you
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def give(self, ctx, member: discord.Member, *, role: discord.Role):
        """Gives a member a role. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot give roles higher than your top role!')
        await member.add_roles(role)
        await ctx.send(f'Successfully gave {member} `{role}`!')
    give.example_usage = """
    `{prefix}give cooldude#1234 Java` - gives cooldude any role, giveable or not, named Java
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def take(self, ctx, member: discord.Member, *, role: discord.Role):
        """Takes a role from a member. Not restricted to giveable roles."""
        if role > ctx.author.top_role:
            raise BadArgument('Cannot take roles higher than your top role!')
        await member.remove_roles(role)
        await ctx.send(f'Successfully took `{role}` from {member}!')

    take.example_usage = """
    `{prefix}take cooldude#1234 Java` - takes any role named Java, giveable or not, from cooldude
    """

    @command()
    @bot_has_permissions(manage_roles=True)
    async def rolecolor(self, ctx, role: discord.Role, color: discord.Color = None):
        """Displays the color of a given role, or sets it to a new value."""
        # required perms are conditional based on arguments
        if color is not None:
            if not ctx.channel.permissions_for(ctx.author).manage_roles:
                raise MissingPermissions(["manage_roles"])
            await role.edit(color=color)
            message = f"Set role color of `{role}` to **{color}**!"
        else:
            message = f"The role color of `{role}` is **{role.color}**"

        await ctx.send(embed=discord.Embed(description=message, color=role.color))

    rolecolor.example_usage = """
    `{prefix}rolecolor "Simbot Red"` - displays the color of the "Simbot Red" role in hexcode format
    `{prefix}rolecolor Bolb #FCC21B` - set the color of the "Bolb" role to #FCC21B
    """

class GiveableRole(orm.Model):
    """Database object for maintaining a list of giveable roles."""
    __tablename__ = 'giveable_roles'
    __primary_key__ = ("role_id",)

    role_id: psqlt.bigint
    guild_id: psqlt.bigint

class MissingRole(orm.Model):
    """Holds what roles a given member had when they last left the guild."""
    __tablename__ = 'missing_roles'
    __primary_key__ = ('role_id', 'member_id')

    role_id: psqlt.bigint
    guild_id: psqlt.bigint
    member_id: psqlt.bigint
    role_name: psqlt.varchar(100)


def setup(bot):
    """Adds the roles cog to the main bot project."""
    bot.add_cog(Roles(bot))
