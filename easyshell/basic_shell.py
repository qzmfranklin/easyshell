import math
import os
import readline
import shutil
import subprocess
import terminaltables
import textwrap

from .base import _ShellBase, command, helper, completer, iscommand, getcommands

class BasicShell(_ShellBase):

    """Shell with a few built-in commands."""

    @command('!', internal = True, visible = False)
    def _do_exec(self, cmd, args):
        """Execute a command using subprocess.Popen().
        """
        if not args:
            self.stderr.write("execute: empty command\n")
            return
        proc = subprocess.Popen(subprocess.list2cmdline(args),
                shell = True, stdout = self.stdout)
        proc.wait()

    @command('end', 'exit', internal = True, nargs = '?')
    def _do_exit(self, cmd, args):
        """\
        Exit shell.
            exit | C-D          Exit to the parent shell.
            exit root | end     Exit to the root shell.
            exit all            Exit to the command line.
        """
        if cmd == 'end':
            if not args:
                return 'root'
            else:
                self.stderr.write(textwrap.dedent('''\
                        end: unrecognized arguments: {}
                        ''')).format(args)

        # Hereafter, cmd == 'exit'.
        if not args:
            return True
        if len(args) > 1:
            self.stderr.write(textwrap.dedent('''\
                    exit: too many arguments: {}
                    ''')).format(args)
        exit_directive = args[0]
        if exit_directive == 'root':
            return 'root'
        if exit_directive == 'all':
            return 'all'
        self.stderr.write(textwrap.dedent('''\
                exit: unrecognized arguments: {}
                ''')).format(args)

    @completer('exit')
    def _complete_exit(self, cmd, args, text):
        """Find candidates for the 'exit' command."""
        if args:
            return
        return [ x for x in { 'root', 'all', } \
                if x.startswith(text) ]

    @command('history', internal = True, nargs = '?')
    def _do_history(self, cmd, args):
        """\
        Display history.
            history             Display history.
            history clear       Clear history.
            history clearall    Clear history for all shells.
        """
        if args and args[0] == 'clear':
            readline.clear_history()
            readline.write_history_file(self.history_fname)
        elif args and args[0] == 'clearall':
            readline.clear_history()
            shutil.rmtree(self._temp_dir, ignore_errors = True)
            os.makedirs(os.path.join(self._temp_dir, 'history'))
        else:
            readline.write_history_file(self.history_fname)
            with open(self.history_fname, 'r', encoding = 'utf8') as f:
                self.stdout.write(f.read())

    @completer('history')
    def _complete_history(self, cmd, args, text):
        """Find candidates for the 'history' command."""
        if args:
            return
        return [ x for x in { 'clear', 'clearall' } \
                if x.startswith(text) ]

    @command('stack', internal = True, nargs = '?')
    def _do_stack(self, cmd, args):
        """\
        Manage the shell stack.
            stack               Display the stack.
            stack <depth>       Exit to the stack by its depth.
        """
        if not args:
            self.__dump_stack()
            return
        if len(args) > 1:
            self.stderr.write('stack: too many arguments: {}\n'.format(args))
            return
        try:
            depth = int(args[0])
        except ValueError:
            self.stderr.write("stack: depth is not an integer: '{}'\n".format(args[0]))
            return
        if depth < 0:
            self.stderr.write('stack: negative depth: {}\n'.format(depth))
            return
        return depth

    @completer('stack')
    def _complete_stack(self, cmd, args, text):
        if not args:
            return [ str(i) for i in range(len(self._mode_stack) + 1) ]

    def __dump_stack(self):
        """Dump the shell stack in a human friendly way.

        An example output is:
                0    PlayBoy
                1    └── foo-prompt: foo@[]
                2        └── karPROMPT: kar@[]
                3            └── DEBUG: debug@['shell']
        """
        maxdepth = len(self._mode_stack)
        maxdepth_strlen = len(str(maxdepth))
        index_width = 4 - (-maxdepth_strlen) % 4 + 4
        index_str = lambda i: '{:<{}d}'.format(i, index_width)

        self.stdout.write(index_str(0) + self.root_prompt)
        self.stdout.write('\n')

        tree_prefix = '└── '
        for i in range(maxdepth):
            index_prefix = index_str(i + 1)
            whitespace_prefix = ' ' * len(tree_prefix) * i
            mode = self._mode_stack[i]
            line = index_prefix + whitespace_prefix + \
                    tree_prefix + mode.prompt_display + \
                    ': {}@{}'.format(mode.cmd, mode.args)
            self.stdout.write(line)
            self.stdout.write('\n')

    @command('help', internal = True, nargs = 0)
    def _do_help(self, cmd, args):
        """Display doc strings of the shell and its commands.
        """
        print(self.doc_string())
        print()

        # Create data of the commands table.
        data_unsorted = []
        cls = self.__class__
        for name in dir(cls):
            obj = getattr(cls, name)
            if iscommand(obj):
                cmds = []
                for cmd in getcommands(obj):
                    cmds.append(cmd)
                cmd_str = ','.join(sorted(cmds))
                doc_str = textwrap.dedent(obj.__doc__) if obj.__doc__ else \
                        '(no doc string available)'
                data_unsorted.append([cmd_str, doc_str])
        data_sorted = sorted(data_unsorted, key = lambda x: x[0])
        data = [['COMMANDS', 'DOC STRING']] + data_sorted

        # Create the commands table.
        table_banner = 'List of Available Commands'
        table = terminaltables.SingleTable(data, table_banner)
        table.inner_row_border = True
        table.inner_heading_row_border = True
        print(table.table)
