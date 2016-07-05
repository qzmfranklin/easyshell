"""A generic class to build line-oriented command interpreters.
"""

import os
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

    cmd_prefix = 'do_'
    EOF = chr(ord('D') - 64)
    _special_delims = '?!'

    def __init__(self, *,
            mode_stack = [],
            stdout = sys.stdout,
            stderr = sys.stderr,
            temp_dir = None):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            mode_stack: A stack of Mode objects.
            stdout, stderr: The file objects to write to for output and error.
            temp_dir: The temporary directory to save history files. The default
                value, None, means to generate such a directory.
        """
        self.stdout = stdout
        self.stderr = stderr
        self._mode_stack = mode_stack
        self._prompt = '({})$ '.format('-'.join( \
                [ m.prompt_display for m in mode_stack ]))
        self._temp_dir = temp_dir if temp_dir else tempfile.mkdtemp()
        os.makedirs(os.path.join(self._temp_dir, 'history'), exist_ok = True)

        self._completion_matches = []

        readline.parse_and_bind('tab: complete')

    @property
    def prompt(self):
        return str(self._prompt)

    @property
    def history_fname(self):
        return os.path.join(self._temp_dir, 'history', 's-' + self.prompt[1:-2])

    def launch_subshell(self, shell_cls, args, *, prompt_display = None):
        """Launch a subshell.

        The doc string of the cmdloop() method explains how shell histories and
        history files are saved and restored.

        Arguments:
            shell_cls: The Shell class object to instantiate and launch.
            args: Arguments used to launch this subshell.
            prompt_display: The name of the subshell. The default, None, means
                to use the shell_cls.__name__.
        """
        # Save history of the current shell.
        readline.write_history_file(self.history_fname)

        prompt_display = prompt_display if prompt_display else shell_cls.__name__
        mode = Mode(args, prompt_display)
        shell = shell_cls(
                mode_stack = self._mode_stack + [ mode ],
                stdout = self.stdout,
                stderr = self.stderr,
                temp_dir = self._temp_dir,
        )
        # The subshell creates its own history context.
        shell.cmdloop()

        # Restore history.
        readline.clear_history()
        readline.read_history_file(self.history_fname)

    def cmdloop(self):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        The completer function, together with the history buffer, is saved and
        restored upon exit.

        Shell history:

            Shell histories are persistently saved to files, whose name matches
            the prompt string. For example, if the prompt of a subshell is
            '(Foo-Bar-Kar)$ ', the name of its history file is s-Foo-Bar-Kar.
            The history_fname property encodes this algorithm.

            All history files are saved to the the directory whose path is
            self._temp_dir. Subshells use the same temp_dir as their parent
            shells, thus their root shell.

            The history of the parent shell is saved and restored by the parent
            shell, as in launch_subshell(). The history of the subshell is saved
            and restored by the subshell, as in cmdloop().

            When a subshell is started, i.e., when the cmdloop() method of the
            subshell is called, the subshell will try to load its own history
            file, whose file name is determined by the naming convention
            introduced earlier.

        Completer Delimiters:

            Two special delimiters '?' and '!' are expanded into 'help' and
            'exec' respectively. But by default they are completer_delims, which
            are never selected as any completion scope.

            The old completer delimiters are saved before the loop and restored
            after the loop ends. This is to keep the environment clean.
        """
        # Save the completer function, the history buffer, and the
        # completer_delims.
        old_completer = readline.get_completer()
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)
        old_delims = readline.get_completer_delims()
        new_delims = ''.join(list(set(old_delims) - set(Shell._special_delims)))
        readline.set_completer_delims(new_delims)

        # Load the new completer function and start a new history buffer.
        readline.set_completer(self._completer)

        # main loop
        try:
            stop = False
            while not stop:
                try:
                    line = input(self.prompt).strip()
                except EOFError:
                    line = Shell.EOF
                stop = self._onecmd(line)
        finally:
            # Restore the completer function, save the history, and restore old
            # delims.
            readline.set_completer(old_completer)
            readline.write_history_file(self.history_fname)
            readline.set_completer_delims(old_delims)

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
        if not args:
            self.stderr.write("exec: empty command\n")
            return
        proc = subprocess.Popen(args, shell = True, stdout = self.stdout)
        proc.wait()

    def do_history(self, args):
        """Dump the history in this shell.

        A side effect is that this method flushes the current history buffer to
        the history file, whose file name is given by the history_fname
        property.
        """
        readline.write_history_file(self.history_fname)
        with open(self.history_fname, 'r', encoding = 'utf8') as f:
            self.stdout.write(f.read())

    def _completer(self, text, state):
        """Driver level completer function of this shell.

        The interface of this method is defined the readline library.

        Arguments:
            text: A string, that is the current completion scope.
            state: An integer.

        Returns:
            A string used to replace the given text.
        """
        if state == 0:
            origline = readline.get_line_buffer()
            line = origline.lstrip()
            offset = len(origline) - len(line)
            begidx = readline.get_begidx() - offset
            endidx = readline.get_endidx() - offset
            # If the current scope is the first token in the line. Leading '?'
            # is converted to 'help'. Leading '!' is converted to 'exec'.
            if begidx == 0:
                if text == '?':
                    return 'help'
                elif text == '!':
                    return 'exec'
                else: # Otherwise try to match the prefix of available commands.
                    self._completion_matches = self._get_cmds_with_prefix(text)
            else:
                self._completion_macthes = []
                return None

        return self._completion_matches[state]

    def __complete_default(self, *args, **kwargs):
        return []

    def _get_cmds_with_prefix(self, text):
        """Get the list of commands starting with the given text."""
        start_text = Shell.cmd_prefix + text
        return [ name[len(Shell.cmd_prefix):] \
                        for name in dir(self.__class__) \
                        if name.startswith(start_text)
                ]

    def completenames(self, text, *ignored):
        start_text = Shell.cmd_prefix + text
        return [ name[len(Shell.cmd_prefix):] \
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
