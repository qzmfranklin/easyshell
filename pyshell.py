"""A generic class to build line-oriented command interpreters.
"""

import readline
import shlex
import string
import subprocess
import sys
import tempfile

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

    EOF = chr(ord('D') - 64)

    def __init__(self, *,
            mode_stack = [],
            stdout = sys.stdout,
            stderr = sys.stderr,
            cmd_prefix = 'do_',
            intro = ''):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            mode_stack: A stack of Mode objects.
            stdout: The file object to write to for output.
            cmd_prefix: Default 'do_' means all methods whose names start with
                'do_' are command methods.
        """
        self._mode_stack = mode_stack
        self._prompt = '({})$ '.format('-'.join( \
                [ m.prompt_display for m in mode_stack ]))

        self.cmd_prefix = cmd_prefix
        self.intro = intro

        self.stdout = stdout
        self.stderr = stderr

        self.cmd_queue = []

        self.ruler = '='
        self.lastcmd = ''

        self.doc_leader = ""
        self.doc_header = "Documented commands (type help <topic>):"
        self.misc_header = "Miscellaneous help topics:"
        self.undoc_header = "Undocumented commands:"
        self.nohelp = "*** No help on %s"

        readline.parse_and_bind('tab: complete')

    @property
    def prompt(self):
        return str(self._prompt)

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

        The completer function, together with the history buffer, is saved and
        restored upon exit.

        The history buffer is saved and restored from a temporary file.
        """
        # Save the completer function and the history buffer.

        # CAVEAT: The readline library handles history files solely by the
        # filenames. This forces us to a) use NamedTemporaryFile() instead of
        # TemporaryFile(), and b) close the generated file before feeding the
        # file name to readline.write_history_file). Usually this should be
        # fine. But there is a small risk of race condition in this solution.
        old_completer = readline.get_completer()
        history_tmpfile = tempfile.NamedTemporaryFile('w+')
        history_tmpfile.close()
        readline.write_history_file(history_tmpfile.name)
        readline.clear_history()

        # Load the new completer function and start a new history buffer.
        readline.set_completer(self.complete)

        # main loop
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
                        line = Shell.EOF
                stop = self._onecmd(line)
        finally:
            # Restore the completer function and the history buffer.
            readline.set_completer(old_completer)
            readline.clear_history()
            readline.read_history_file(history_tmpfile.name)

    def _parse_line(self, line):
        """Parse a line of input.

        '?'  => help
        '!'  => shell
        C-D  => exit, insert 'exit\\n' to the command line.

        Arguments:
            line: A string, representing a line of input from the shell. This
                string is preprocessed by cmdloop() to convert the EOF character
                to '\\x04', i.e., 'D' - 64, if the EOF character is the only
                character from the shell.

        Returns:
            A tuple (cmd, args) where args is a list of strings. If the input
            line has only a single EOF character '\\x04', return ( 'exit', [] ).
        """
        if line == Shell.EOF:
            # This is a hack to allow the EOF character to behave exactly like
            # typing the 'exit' command.
            readline.insert_text('exit\n')
            readline.redisplay()
            return ( 'exit', [] )

        toks = shlex.split(line.strip())
        if len(toks) == 0:
            return ( '', [] )

        cmd = toks[0]
        if cmd == '?':
            cmd = 'help'
        elif cmd == '!':
            cmd = 'exec'

        return ( cmd, [] if len(toks) == 1 else toks[1:] )

    def _onecmd(self, line):
        """Execute a command."""
        if not line:
            return
        cmd, args = self._parse_line(line)
        if hasattr(self, 'do_' + cmd):
            func = getattr(self, 'do_' + cmd)
            return func(args)
        else:
            self.stderr.write("{}: command not found\n".format(cmd))

    def do_exit(self, args):
        """Exit this shell. Same as C-D."""
        return True

    def do_exec(self, args):
        """Execute a command using subprocess.Popen()."""
        proc = subprocess.Popen(args, stdout = self.stdout)
        proc.wait()

    def complete(self, text, state):
        """Completer function of this shell.

        Use readline.get_line_buffer() to

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
                    compfunc = self.__complete_default
                else:
                    if hasattr(self, 'complete_' + cmd):
                        compfunc = getattr(self, 'complete_' + cmd)
                    else:
                        compfunc = self.__complete_default
            else:
                compfunc = self.completenames
            self.completion_matches = compfunc(text, line, begidx, endidx)
        try:
            return self.completion_matches[state]
        except IndexError:
            return None

    def __complete_default(self, *args, **kwargs):
        return []

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

    def completenames(self, text, *ignored):
        start_text = self.cmd_prefix + text
        return [ name[len(self.cmd_prefix):] \
                        for name in dir(self.__class__) \
                        if name.startswith(start_text)
                ]

    def complete_help(self, *args):
        commands = set(self.completenames(*args))
        topics = set(a[5:] for a in dir(self.__class__)
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
            names = dir(self.__class__)
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
