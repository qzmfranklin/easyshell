#!/usr/bin/env python3

"""An example shell, with subshell enabled.
"""

import pyshell


# The subshell classes must be defined before being referenced.
class KarShell(pyshell.Shell):
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
    @pyshell.command('p')
    def do_p(self, cmd, arg):
        print("cmd = '{}', arg = '{}'".format(cmd, arg))


class FooShell(pyshell.Shell):

    # 'kar' enters a subshell with a prompt string that depends on the
    # arguments.
    @pyshell.subshell(KarShell, 'kar')
    def do_kar(self, cmd, args):
        return 'karPROMPT' + '@'.join(args)


class BarShell(pyshell.Shell):
    pass


class MyShell(pyshell.Shell):

    def preloop(self):
        print('Hello! Welcome to MyShell.')

    def postloop(self):
        print('Thanks for using MyShell. Bye!')

    # 'foo' and 'fsh' enters the FooShell with prompt 'foo-prompt'.
    @pyshell.subshell(FooShell, 'foo', 'fsh')
    def do_foo(self, cmd, args_ignored):
        return 'foo-prompt'

    # 'bar' enters the BarShell with prompt 'BarPrompt'.
    @pyshell.command('bar')
    @pyshell.subshell(BarShell)
    def do_bar(self, cmd, args_ignored):
        return 'BarPrompt'

    # The same Shell class, KarShell, can be freely reused.
    @pyshell.subshell(KarShell, 'kar0')
    def do_kar(self, cmd, args_ignored):
        return 'kar0'

    # If this command is called, enters the FooShell. But this command does not
    # directly correspond to any commands.
    @pyshell.subshell(FooShell)
    def print_and_launch_fsh(self, cmd, args_ignored):
        print('Launch the FooShell manually.')

    # 'hello', 'hi', and 'Ha--lo' print 'Hello world!' but does not enter any
    # subshell. Note that the help message, by default, is just the doc string.
    @pyshell.command('hello', 'hi', 'Ha--lo')
    def do_hello(self, cmd, args_ignored):
        """Print 'Hello world!'."""
        print('Hello world!')

    # Add helper method for 'foo' and 'fsh' commands. The interface is detailed
    # in the doc string of the Shell.__driver_helper() method.
    @pyshell.helper('foo', 'fsh')
    def help_foo(self, cmd, args_ignored):
        return 'foo (--all|--no), fsh         Enter the foo-prompt subshell'

    # Add completer method for 'foo'. The interface is detailed in the doc
    # string of the Shell.__driver_completer() method.
    @pyshell.completer('foo')
    def complete_foo(self, cmd, args, text):
        if args:
            return
        return [ x for x in { '--all', '--no' } \
                if x.startswith(text) ]


if __name__ == '__main__':
    MyShell(
            # Supply a custom root prompt.
            root_prompt = 'PlayBoy',

            # Supply a directory name to have persistent history.
            temp_dir = '/tmp/pyshell',

            # Debug mode prints debug information to self.stderr.
            debug = False,
    ).cmdloop()
