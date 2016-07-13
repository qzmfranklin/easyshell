"""An example shell, with subshell enabled.
"""

import argparse
import os
import sys
import subprocess
import textwrap

from . import completer, shell

# The subshell classes must be defined before being referenced.
class KarShell(shell.Shell):
    """The KarShell.

    This message shows up when you type 'help'
    """

    # Overwrite the parser to apply a different lexing rule.
    # The exact interface is documented in the parse_line() method.
    def parse_line(self, line):
        return line[0], line[1:]

    # The 'p' command uses a different lexing rule than other shells.
    # To visualize the difference in the lexing rule, try the following input,
    # (actual characters are enclosed within a pair of single quotes):
    #       '  p  didj -dd jidd jvi'
    @shell.command('p')
    def do_p(self, cmd, arg):
        """\
        Please try:
            panything
        """
        print("cmd = '{}', arg = '{}'".format(cmd, arg))


class FooShell(shell.Shell):

    # 'kar' enters a subshell with a prompt string that depends on the
    # arguments.
    @shell.subshell(KarShell, 'kar')
    def do_kar(self, cmd, args):
        return 'karPROMPT' + '@'.join(args)


class BarShell(shell.Shell):

    # Any unicode string can be a command.
    @shell.command('hello', '你好', 'こんにちは', 'Bonjour', 'Χαίρετε', 'Halo-😜')
    def do_hello(self, cmd, args_ignored):
        """Print 'Hello world!'."""
        print('Hello world!')


class MyShell(shell.Shell):

    def preloop(self):
        print(textwrap.dedent('''\
                Hello! Welcome to MyShell.
                Enter '?' followed by a tab to get help.
                '''))

    def postloop(self):
        print('Thanks for using MyShell. Bye!')

    # 'foo' and 'fsh' enters the FooShell with prompt 'foo-prompt'.
    @shell.subshell(FooShell, 'foo', 'fsh')
    def do_foo(self, cmd, args_ignored):
        return 'foo-prompt'

    # Add helper method for 'foo' and 'fsh' commands. The interface is detailed
    # in the doc string of the Shell.__driver_helper() method.
    @shell.helper('foo', 'fsh')
    def help_foo(self, cmd, args_ignored):
        return 'foo (--all|--no), fsh         Enter the foo-prompt subshell.'

    # Add completer method for 'foo'. The interface is detailed in the doc
    # string of the Shell.__driver_completer() method.
    @shell.completer('foo')
    def complete_foo(self, cmd, args, text):
        if args:
            return
        return [ x for x in { '--all', '--no' } \
                if x.startswith(text) ]

    # 'bar' enters the BarShell with prompt 'BarPrompt'.
    @shell.subshell(BarShell, 'bar')
    def do_bar(self, cmd, args_ignored):
        return 'BarPrompt'

    # The same Shell class, KarShell, can be freely reused.
    @shell.subshell(KarShell, 'kar-🐶')
    def do_kar(self, cmd, args_ignored):
        """\
        Enter the kar-🐶 subshell.
        Yes, emojis can be part of a command.
        """
        return 'kar-🐶'

    # 'cat' uses the file-system completer that ships with easyshell. Note that
    # the command's name 'cat' does not nesessarily have to relate to the name
    # of the method, which is 'do_show' in this case.
    @shell.command('cat')
    def do_show(self, cmd, args):
        """\
        Display content of a file.
            cat                 Display current working directory.
            cat <file>          Display content of a file.
        """
        if not args:
            self.stdout.write(os.getcwd())
            self.stdout.write('\n')
            return
        if len(args) > 1:
            self.stderr.write('cat: too many arguments: {}\n'.format(args))
            return
        fname = args[0]
        with open(fname, 'r', encoding = 'utf8') as f:
            self.stdout.write(f.read())
            self.stdout.write('\n')

    # Use the file system completer to complete file names.
    @shell.completer('cat')
    def complete_show(self, cmd, args, text):
        if not args:
            return completer.fs.find_matches(text)


if __name__ == '__main__':

    def __update_sp(sp):
        def __stdin(s):
            if s is None:
                return None
            if s == '-':
                return sys.stdin
            return open(s, 'r', encoding = 'utf8')
        sp.add_argument('--root-prompt',
                metavar = 'STR',
                default = 'PlayBoy',
                help = 'the root prompt string')
        sp.add_argument('--temp-dir',
                metavar = 'DIR',
                default = '/tmp/shell',
                help = 'the directory to save history files')
        sp.add_argument('--debug',
                action = 'store_true',
                help = 'turn debug infomation on')
        sp.add_argument('file',
                metavar = 'FILE',
                nargs = '?',
                type = __stdin,
                help = "execute script in non-interactive mode. '-' = stdin")

    parser = argparse.ArgumentParser(description = __doc__,
            formatter_class = argparse.ArgumentDefaultsHelpFormatter)
    __update_sp(parser)
    args = parser.parse_args()

    if args.file:
        proc = subprocess.Popen(
                ['python3', '-m', 'easyshell'],
                stdin = subprocess.PIPE,
                stdout = subprocess.DEVNULL,
                stderr = sys.stderr,
                universal_newlines = True,
        )
        proc.communicate(args.file.read(), timeout = 5)
        proc.wait(timeout = 60)
    else:
        d = vars(args)
        del d['file']
        MyShell(**d).cmdloop()
