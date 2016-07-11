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

import os
import textwrap

from easyshell import completer, shell

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
    MyShell(
            # Supply a custom root prompt.
            root_prompt = 'PlayBoy',

            # Supply a directory name to have persistent history.
            temp_dir = '/tmp/shell',

            # Debug mode prints debug information to self.stderr.
            debug = False,
    ).cmdloop()
