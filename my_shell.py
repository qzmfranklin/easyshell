#!/usr/bin/env python3

#  A python3 library for creating recursive shells.
#
#  Copyright (C) 2016,  Zhongming Qu
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""An example shell, with subshell enabled.
"""

import easyshell
import textwrap


# The subshell classes must be defined before being referenced.
class KarShell(easyshell.Shell):
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
    @easyshell.command('p')
    def do_p(self, cmd, arg):
        """\
        Please try:
            panything
        """
        print("cmd = '{}', arg = '{}'".format(cmd, arg))


class FooShell(easyshell.Shell):

    # 'kar' enters a subshell with a prompt string that depends on the
    # arguments.
    @easyshell.subshell(KarShell, 'kar')
    def do_kar(self, cmd, args):
        return 'karPROMPT' + '@'.join(args)


class BarShell(easyshell.Shell):
    pass


class MyShell(easyshell.Shell):

    def preloop(self):
        print(textwrap.dedent('''\
                Hello! Welcome to MyShell. To get help, enter '?' followed by a tab.'''))

    def postloop(self):
        print('Thanks for using MyShell. Bye!')

    # 'foo' and 'fsh' enters the FooShell with prompt 'foo-prompt'.
    @easyshell.subshell(FooShell, 'foo', 'fsh')
    def do_foo(self, cmd, args_ignored):
        return 'foo-prompt'

    # 'bar' enters the BarShell with prompt 'BarPrompt'.
    @easyshell.command('bar')
    @easyshell.subshell(BarShell)
    def do_bar(self, cmd, args_ignored):
        return 'BarPrompt'

    # The same Shell class, KarShell, can be freely reused.
    @easyshell.subshell(KarShell, 'kar0')
    def do_kar(self, cmd, args_ignored):
        return 'kar0'

    # If this command is called, enters the FooShell. But this command does not
    # directly correspond to any commands.
    @easyshell.subshell(FooShell)
    def print_and_launch_fsh(self, cmd, args_ignored):
        print('Launch the FooShell manually.')

    # 'hello', 'hi', and 'Ha--lo' print 'Hello world!' but does not enter any
    # subshell. Note that the help message, by default, is just the doc string.
    @easyshell.command('hello', 'hi', 'Ha--lo')
    def do_hello(self, cmd, args_ignored):
        """Print 'Hello world!'."""
        print('Hello world!')

    # Add helper method for 'foo' and 'fsh' commands. The interface is detailed
    # in the doc string of the Shell.__driver_helper() method.
    @easyshell.helper('foo', 'fsh')
    def help_foo(self, cmd, args_ignored):
        return 'foo (--all|--no), fsh         Enter the foo-prompt subshell'

    # Add completer method for 'foo'. The interface is detailed in the doc
    # string of the Shell.__driver_completer() method.
    @easyshell.completer('foo')
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
            temp_dir = '/tmp/easyshell',

            # Debug mode prints debug information to self.stderr.
            debug = False,
    ).cmdloop()
