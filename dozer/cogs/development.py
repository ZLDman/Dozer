"""Commands specific to development. Only approved developers can use these commands."""
import copy
import re
import logging
import discord

from discord.ext.commands import NotOwner

from ._utils import *

logger = logging.getLogger("dozer")


class Development(Cog):
    """
    Commands useful for developing the bot.
    These commands are restricted to bot developers.
    """
    def __init__(self, bot):
        super().__init__(bot)
        self.eval_globals = {}
        for module in ('asyncio', 'collections', 'discord', 'inspect', 'itertools'):
            self.eval_globals[module] = __import__(module)
        self.eval_globals['__builtins__'] = __import__('builtins')
        for attr in ('line_print',):
            self.eval_globals[attr] = getattr(self, attr)

    def __local_check(self, ctx):  # All of this cog is only available to devs
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        return True

    @staticmethod
    async def line_print(ctx: discord.abc.Messageable, title, iterable, color=discord.Color.default()):
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

    @command()
    async def reload(self, ctx, cog):
        """Reloads a cog."""
        extension = 'dozer.cogs.' + cog
        msg = await ctx.send('Reloading extension %s' % extension)
        self.bot.unload_extension(extension)
        self.bot.load_extension(extension)
        await msg.edit(content='Reloaded extension %s' % extension)

    reload.example_usage = """
    `{prefix}reload development` - reloads the development cog
    """

    @command(name='eval')
    async def evaluate(self, ctx, *, code):
        """
        Evaluates Python.
        Await is valid and `{ctx}` is the command context.
        """
        if code.startswith('```'):
            code = code.strip('```').partition('\n')[2].strip()  # Remove multiline code blocks
        else:
            code = code.strip('`').strip()  # Remove single-line code blocks, if necessary

        logger.info(f"Evaluating code at request of {ctx.author} ({ctx.author.id}) in '{ctx.guild}' #{ctx.channel}:")
        logger.info("-"*32)
        for line in code.splitlines():
            logger.info(line)
        logger.info("-"*32)

        e = discord.Embed(type='rich')
        e.add_field(name='Code', value='```py\n%s\n```' % code, inline=False)
        try:
            locals_ = locals()
            load_function(code, self.eval_globals, locals_)
            ret = await locals_['evaluated_function'](ctx)

            e.title = 'Python Evaluation - Success'
            e.color = 0x00FF00
            e.add_field(name='Output', value='```\n%s (%s)\n```' % (repr(ret), type(ret).__name__), inline=False)
        except Exception as err:
            e.title = 'Python Evaluation - Error'
            e.color = 0xFF0000
            e.add_field(name='Error', value='```\n%s\n```' % repr(err))
        await ctx.send('', embed=e)

    evaluate.example_usage = """
    `{prefix}eval 0.1 + 0.2` - calculates 0.1 + 0.2
    `{prefix}eval await ctx.send('Hello world!')` - send "Hello World!" to this channel
    """

    @command(name='su', pass_context=True)
    async def pseudo(self, ctx, user: discord.Member, *, command):
        """Execute a command as another user."""
        msg = copy.copy(ctx.message)
        msg.author = user
        msg.content = command
        context = await self.bot.get_context(msg)
        return await self.bot.invoke(context)

    pseudo.example_usage = """
    `{prefix}su cooldude#1234 {prefix}ping` - simulate cooldude sending `{prefix}ping`
    """

    @command()
    async def listservers(self, ctx):
        """Lists the servers that Plowie is in."""
        await self.line_print(ctx, "List of servers:", self.bot.guilds, color=discord.Color.blue())


def load_function(code, globals_, locals_):
    """Loads the user-evaluted code as a function so it can be executed."""
    function_header = 'async def evaluated_function(ctx):'

    lines = code.splitlines()
    if len(lines) > 1:
        indent = 4
        for line in lines:
            line_indent = re.search(r'\S', line).start()  # First non-WS character is length of indent
            if line_indent:
                indent = line_indent
                break
        line_sep = '\n' + ' ' * indent
        exec(function_header + line_sep + line_sep.join(lines), globals_, locals_)
    else:
        try:
            exec(function_header + '\n\treturn ' + lines[0], globals_, locals_)
        except SyntaxError as err:  # Either adding the 'return' caused an error, or it's user error
            if err.text[err.offset - 1] == '=' or err.text[err.offset - 3:err.offset] == 'del' \
                    or err.text[err.offset - 6:err.offset] == 'return':  # return-caused error
                exec(function_header + '\n\t' + lines[0], globals_, locals_)
            else:  # user error
                raise err


def setup(bot):
    """Adds the development cog to the bot."""
    bot.add_cog(Development(bot))
