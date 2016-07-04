#!/usr/bin/env python3

import pyshell

class MyShell(pyshell.Shell):
    def do_foo(self, args):
        self.launch_subshell(FooShell, args)
    def do_bar(self, args):
        self.launch_subshell(BarShell, args, prompt_display = 'bar')

class FooShell(pyshell.Shell):
    def do_kar(self, args):
        self.launch_subshell(KarShell, args, prompt_display = 'kar')

class KarShell(pyshell.Shell):
    pass

class BarShell(pyshell.Shell):
    pass

if __name__ == '__main__':
    MyShell().cmdloop()
