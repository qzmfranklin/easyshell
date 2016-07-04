"""A generic class to build line-oriented command interpreters.
"""

import readline
import shlex
import string
import sys

class Mode(object):

    def __init__(self, args, prompt_display):
        """
        Arguments:
            args: A list of strings.
            prompt_display: The string to appear in prompt. If None, only the
                cmd will appear.
        """
        self.args = args
        self.prompt_display = prompt_display

class Shell(object):

    def __init__(self, *,
            mode_stack = [],
            stdout = sys.stdout,
            intro = ''):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            mode_stack: A stack of Mode objects.
            stdout: The file object to write to for output.
        """
        self.cmd_queue = []

        self._mode_stack = mode_stack
        self._prompt = '({})$ '.format('-'.join( \
                [ m.prompt_display for m in mode_stack ]))

        self.stdout = stdout

        self.ruler = '='
        self.lastcmd = ''

        self.intro = intro
        self.doc_leader = ""
        self.doc_header = "Documented commands (type help <topic>):"
        self.misc_header = "Miscellaneous help topics:"
        self.undoc_header = "Undocumented commands:"
        self.nohelp = "*** No help on %s"

    @property
    def prompt(self):
        return str(self._prompt)

    def parse_line(self, line):
        """Parse a line of input.

        '?'  => help
        '!'  => shell
        C-D  => exit

        Arguments:
            line: A string, representing a line of input from the shell. This
                string is preprocessed by cmdloop() to convert the EOF character
                to '\\x04', i.e., 'D' - 64, if the EOF character is the only
                character from the shell.

        Returns:
            A tuple (cmd, args) where args is a list of strings. If the input
            line has only a single EOF character '\\x04', return ( 'exit', [] ).
        """
        if line == '\x04':
            return ( 'exit', ['\n'] )

        toks = shlex.split(line.strip())
        if len(toks) == 0:
            return ( '', [] )

        cmd = toks[0]
        if cmd == '?':
            cmd = 'help'
        elif cmd == '!':
            cmd = 'shell'

        return ( cmd, [] if len(toks) == 1 else toks[1:] )

    def launch_subshell(self, shell_cls, args, *, prompt_display = None):
        """Launch a subshell.

        Arguments:
            shell_cls: The Shell class object to instantiate and launch.
            args: Arguments used to launch this subshell.
            prompt_display: The name of the subshell. The default, None, means
                to use the shell_cls.__name__.
        """
        prompt_display = prompt_display if prompt_display else shell_cls.__name__
        mode = Mode(args, prompt_display)
        shell = shell_cls(
                mode_stack = self._mode_stack + [ mode ],
                stdout = self.stdout,
        )
        shell.cmdloop()

    def cmdloop(self):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        """
        old_completer = readline.get_completer()
        readline.set_completer(self.complete)
        readline.parse_and_bind('tab: complete')
        try:
            if self.intro:
                self.stdout.write(str(self.intro) + '\n')
            stop = False
            while not stop:
                if self.cmd_queue:
                    line = self.cmd_queue.pop(0)
                else:
                    try:
                        line = input(self.prompt).strip()
                    except EOFError:
                        line = chr(ord('D') - 64)
                stop = self._onecmd(line)
        finally:
            readline.set_completer(old_completer)

    def _onecmd(self, line):
        """Execute a command."""
        if not line:
            return
        cmd, args = self.parse_line(line)
        try:
            func = getattr(self, 'do_' + cmd)
            return func(args)
        except AttributeError:
            self.stdout.write("{}: command not found\n".format(cmd))
            return

    def do_exit(self, *args):
        """Exit this shell. Same as C-D."""
        self.stdout.write('\n')
        return True

    def completedefault(self, *ignored):
        """Method called to complete an input line when no command-specific
        complete_*() method is available.

        By default, it returns an empty list.
        """
        return []

    def completenames(self, text, *ignored):
        dotext = 'do_'+text
        return [a[3:] for a in self.get_names() if a.startswith(dotext)]

    def complete(self, text, state):
        """Return the next possible completion for 'text'.

        If a command has not been entered, then complete against command list.
        Otherwise try to call complete_<command> to get list of completions.
        """
        if state == 0:
            origline = readline.get_line_buffer()
            line = origline.lstrip()
            stripped = len(origline) - len(line)
            begidx = readline.get_begidx() - stripped
            endidx = readline.get_endidx() - stripped
            if begidx>0:
                cmd, args, foo = self.parseline(line)
                if cmd == '':
                    compfunc = self.completedefault
                else:
                    try:
                        compfunc = getattr(self, 'complete_' + cmd)
                    except AttributeError:
                        compfunc = self.completedefault
            else:
                compfunc = self.completenames
            self.completion_matches = compfunc(text, line, begidx, endidx)
        try:
            return self.completion_matches[state]
        except IndexError:
            return None

    __identchars = string.ascii_letters + string.digits + '_'
    def parseline(self, line):
        """Parse the line into a command name and a string containing
        the arguments.  Returns a tuple containing (command, args, line).
        'command' and 'args' may be None if the line couldn't be parsed.
        """
        line = line.strip()
        if not line:
            return None, None, line
        elif line[0] == '?':
            line = 'help ' + line[1:]
        elif line[0] == '!':
            if hasattr(self, 'do_shell'):
                line = 'shell ' + line[1:]
            else:
                return None, None, line
        i, n = 0, len(line)
        while i < n and line[i] in self.__identchars: i = i+1
        cmd, arg = line[:i], line[i:].strip()
        return cmd, arg, line

    def get_names(self):
        # This method used to pull in base class attributes
        # at a time dir() didn't do it yet.
        return dir(self.__class__)

    def complete_help(self, *args):
        commands = set(self.completenames(*args))
        topics = set(a[5:] for a in self.get_names()
                     if a.startswith('help_' + args[0]))
        return list(commands | topics)

    def do_help(self, arg):
        'List available commands with "help" or detailed help with "help cmd".'
        if arg:
            # XXX check arg syntax
            try:
                func = getattr(self, 'help_' + arg)
            except AttributeError:
                try:
                    doc=getattr(self, 'do_' + arg).__doc__
                    if doc:
                        self.stdout.write("%s\n"%str(doc))
                        return
                except AttributeError:
                    pass
                self.stdout.write("%s\n"%str(self.nohelp % (arg,)))
                return
            func()
        else:
            names = self.get_names()
            cmds_doc = []
            cmds_undoc = []
            help = {}
            for name in names:
                if name[:5] == 'help_':
                    help[name[5:]]=1
            names.sort()
            # There can be duplicates if routines overridden
            prevname = ''
            for name in names:
                if name[:3] == 'do_':
                    if name == prevname:
                        continue
                    prevname = name
                    cmd=name[3:]
                    if cmd in help:
                        cmds_doc.append(cmd)
                        del help[cmd]
                    elif getattr(self, name).__doc__:
                        cmds_doc.append(cmd)
                    else:
                        cmds_undoc.append(cmd)
            self.stdout.write("%s\n"%str(self.doc_leader))
            self.print_topics(self.doc_header,   cmds_doc,   15,80)
            self.print_topics(self.misc_header,  list(help.keys()),15,80)
            self.print_topics(self.undoc_header, cmds_undoc, 15,80)

    def print_topics(self, header, cmds, cmdlen, maxcol):
        if cmds:
            self.stdout.write("%s\n"%str(header))
            if self.ruler:
                self.stdout.write("%s\n"%str(self.ruler * len(header)))
            self.columnize(cmds, maxcol-1)
            self.stdout.write("\n")

    def columnize(self, list, displaywidth=80):
        """Display a list of strings as a compact set of columns.

        Each column is only as wide as necessary.
        Columns are separated by two spaces (one was not legible enough).
        """
        if not list:
            self.stdout.write("<empty>\n")
            return

        nonstrings = [i for i in range(len(list))
                        if not isinstance(list[i], str)]
        if nonstrings:
            raise TypeError("list[i] not a string for i in %s"
                            % ", ".join(map(str, nonstrings)))
        size = len(list)
        if size == 1:
            self.stdout.write('%s\n'%str(list[0]))
            return
        # Try every row count from 1 upwards
        for nrows in range(1, len(list)):
            ncols = (size+nrows-1) // nrows
            colwidths = []
            totwidth = -2
            for col in range(ncols):
                colwidth = 0
                for row in range(nrows):
                    i = row + nrows*col
                    if i >= size:
                        break
                    x = list[i]
                    colwidth = max(colwidth, len(x))
                colwidths.append(colwidth)
                totwidth += colwidth + 2
                if totwidth > displaywidth:
                    break
            if totwidth <= displaywidth:
                break
        else:
            nrows = len(list)
            ncols = 1
            colwidths = [0]
        for row in range(nrows):
            texts = []
            for col in range(ncols):
                i = row + nrows*col
                if i >= size:
                    x = ""
                else:
                    x = list[i]
                texts.append(x)
            while texts and not texts[-1]:
                del texts[-1]
            for col in range(len(texts)):
                texts[col] = texts[col].ljust(colwidths[col])
            self.stdout.write("%s\n"%str("  ".join(texts)))
