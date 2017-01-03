from .base import command, helper, completer, subshell
from .basic_shell import BasicShell
from .debugging_shell import DebuggingShell

class _Shell(BasicShell):

    """Embed DebuggingShell into BasicShell."""

    @subshell(DebuggingShell, 'debug', internal = True)
    def _do_debug(self, cmd, args):
        """\
        Enter the debugging shell.
            debug               Show current debugging status, i.e, on/off.
            debug {on,off}      Turn on/off debugging info.
            debug shell         Enter debugging shell.
            debug toggle        Toggle current debugging status.
        """
        if not args:
            self.stdout.write('on' if self.debug else 'off')
            self.stdout.write('\n')
            return
        if len(args) > 1:
            self.stderr.write('debug: too many arguments: {}\n'.format(args))
            return
        action = args[0]
        if action == 'on':
            self.debug = True
        elif action == 'off':
            self.debug = False
        elif action == 'shell':
            return 'DEBUG'
        elif action == 'toggle':
            self.debug = not self.debug
            self.stdout.write('on' if self.debug else 'off')
            self.stdout.write('\n')
        else:
            self.stderr.write('debug: unrecognized argument: {}\n'.format(action))

    @completer('debug')
    def _complete_debug(self, cmd, args, text):
        if args:
            return []
        return [ x for x in { 'on', 'off', 'shell', 'toggle', } \
                if x.startswith(text) ]

class Shell(_Shell):

    """Interactive shell.

    Get help:
            help                Display information about this shell and its
                                commands.
            <TAB>               Display commands.
            ?<TAB>              Display this message.
            <command>?<TAB>     Display help message for <command>.

    Execute a real shell command.
            ! <command>         Execute <command> using subprocess.Popen().
    """
    pass
