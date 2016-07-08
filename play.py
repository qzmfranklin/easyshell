#!/usr/bin/env python3

"""An example shell, with subshell enabled.
"""

import pyshell

# The subshell classes must be defined before being referenced.
class KarShell(pyshell.Shell):
    """The KarShell.

    This message shows up when you type 'help'
    """
    pass

class FooShell(pyshell.Shell):
    @pyshell.subshell(KarShell, 'kar')
    def do_kar(self, args):
        return 'karPROMPT'

class BarShell(pyshell.Shell):
    pass

class MyShell(pyshell.Shell):

    # 'foo' and 'fsh' enters the FooShell with prompt 'foo-prompt'.
    @pyshell.subshell(FooShell, 'foo', 'fsh')
    def do_foo(self, args):
        return 'foo-prompt'

    # 'bar' enters the BarShell with prompt 'BarPrompt'.
    @pyshell.command('bar')
    @pyshell.subshell(BarShell)
    def do_bar(self, args):
        return 'BarPrompt'

    # The same Shell class, KarShell, can be freely reused.
    @pyshell.subshell(KarShell, 'kar0')
    def do_kar(self, args):
        return 'kar0'

    # If this command is called, enters the FooShell. But this command does not
    # directly correspond to any commands.
    @pyshell.subshell(FooShell)
    def print_and_launch_fsh(self, args):
        print('Launch the FooShell manually.')

    # 'hello', 'hi', and 'Ha--lo' print 'Hello world!' but does not enter any
    # subshell.
    @pyshell.command('hello', 'hi', 'Ha--lo')
    def do_hello(self, args):
        print('Hello world!')

    # Add helper method for 'foo' and 'fsh' commands.
    @pyshell.helper('foo', 'fsh')
    def help_foo(self, args_ignored):
        return 'foo,fsh         enter the foo-prompt subshell'


if __name__ == '__main__':

    MyShell(
            # Supply a custom root prompt.
            root_prompt = 'PlayBoy',

            # Supply a directory name to have persistent history.
            temp_dir = '/tmp/pyshell',

            # Debug mode prints debug information to self.stderr.
            debug = False,
    ).cmdloop()
