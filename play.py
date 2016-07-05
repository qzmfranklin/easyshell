#!/usr/bin/env python3

"""An example shell, with subshell enabled.

$ ./play.py
()$ foo
(FooShell)$ kar
(FooShell-kar)$
(FooShell)$
()$
"""

import pyshell

class MyShell(pyshell.Shell):

    @pyshell.command('foo')
    def do_foo(self, args):
        self.launch_subshell(FooShell, args)

    @pyshell.command('bar')
    def do_bar(self, args):
        self.launch_subshell(BarShell, args, prompt_display = 'bar')

class FooShell(pyshell.Shell):

    @pyshell.command('kar')
    def do_kar(self, args):
        self.launch_subshell(KarShell, args, prompt_display = 'kar')

class KarShell(pyshell.Shell):
    pass

class BarShell(pyshell.Shell):
    pass

if __name__ == '__main__':
    MyShell().cmdloop()
