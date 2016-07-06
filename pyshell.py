"""A generic class to build line-oriented command interpreters.
"""

import os
import readline
import shlex
import string
import subprocess
import sys
import tempfile

# Decorators with arguments is a little bit tricky to get right. A good
# thread on it is:
#       http://stackoverflow.com/questions/5929107/python-decorators-with-parameters
def command(*names):
    """Decorator function for adding __command__ to a function object.
    Arguments:
        names: Names of command that should trigger this function object.
    """
    def decorated_func(f):
        f.__command__ = list(names)
        return f
    return decorated_func

# The naming convention is same as the inspect module, which has such predicate
# methods as isfunction, isclass, ismethod, etc..
def iscommand(f):
    """Is the function object a command or not."""
    return hasattr(f, '__command__')

# A parametrized decorator decorating a method is very tricky. To fully
# understand, please first consult this thread:
#       http://stackoverflow.com/questions/11731136/python-class-method-decorator-w-self-arguments
# Then note that when the method being decorated is printed, its __name__
# attribute is unchanged but the repr() function displays the method as
# 'inner_func'.
def subshell(shell_cls, *names):
    """Decorator function for launching a subshell.

    Returns:
        A string used as the prompt.
    """
    def decorated_func(f):
        def inner_func(self, args):
            prompt_display = f(self, args)
            return self.launch_subshell(shell_cls, args,
                    prompt_display = prompt_display)
        inner_func.__name__ = f.__name__
        return command(*names)(inner_func) if names else inner_func
    return decorated_func

class Shell(object):

    class _Mode(object):
        """Stack mode information used when entering and leaving a subshell.
        """
        def __init__(self, args, prompt_display):
            self.args = args
            self.prompt_display = prompt_display

    EOF = chr(ord('D') - 64)
    _non_delims = '-'

    def __init__(self, *,
            mode_stack = [],
            stdout = sys.stdout,
            stderr = sys.stderr,
            root_prompt = 'root',
            temp_dir = None):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            mode_stack: A stack of Shell._Mode objects.
            stdout, stderr: The file objects to write to for output and error.
            temp_dir: The temporary directory to save history files. The default
                value, None, means to generate such a directory.
        """
        self.stdout = stdout
        self.stderr = stderr
        self._mode_stack = mode_stack
        self._prompt = '({})$ '.format('-'.join(
                [ root_prompt ] + \
                [ m.prompt_display for m in mode_stack ]))
        self._temp_dir = temp_dir if temp_dir else tempfile.mkdtemp()
        os.makedirs(os.path.join(self._temp_dir, 'history'), exist_ok = True)

        readline.parse_and_bind('tab: complete')

        self._cmd_map = self.__build_cmd_map()

    def __build_cmd_map(self):
        """Build a mapping from commands to method names.

        One command maps to at most one method.
        Multiple commands can map to the same method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.
        """
        ret = {}
        for name in dir(self):
            obj = getattr(self, name)
            if iscommand(obj):
                for cmd in obj.__command__:
                    ret[cmd] = obj.__name__
        return ret

    @property
    def prompt(self):
        return str(self._prompt)

    @property
    def history_fname(self):
        """The temporary for storing the history of this shell."""
        return os.path.join(self._temp_dir, 'history', 's-' + self.prompt[1:-2])

    def print_debug(self, msg):
        pass

    def launch_subshell(self, shell_cls, args, *, prompt_display = None):
        """Launch a subshell.

        The doc string of the cmdloop() method explains how shell histories and
        history files are saved and restored.

        Arguments:
            shell_cls: The Shell class object to instantiate and launch.
            args: Arguments used to launch this subshell.
            prompt_display: The name of the subshell. The default, None, means
                to use the shell_cls.__name__.

        Returns:
            'end': Inform the parent shell to keep exiting until the root shell
                is reached.
            False, None, or anything that are evaluated as False: Inform the
                parent shell to stay in that parent shell.
        """
        # Save history of the current shell.
        readline.write_history_file(self.history_fname)

        prompt_display = prompt_display if prompt_display else shell_cls.__name__
        mode = Shell._Mode(args, prompt_display)
        shell = shell_cls(
                mode_stack = self._mode_stack + [ mode ],
                stdout = self.stdout,
                stderr = self.stderr,
                temp_dir = self._temp_dir,
        )
        # The subshell creates its own history context.
        self.print_debug("Leave parent shell '{}'".format(self.prompt))
        exit_directive = shell.cmdloop()
        self.print_debug("Enter parent shell '{}': {}".format(self.prompt, exit_directive))

        # Restore history.
        readline.clear_history()
        readline.read_history_file(self.history_fname)

        return 'end' if exit_directive == 'end' else False

    def cmdloop(self):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        The completer function, together with the history buffer, is saved and
        restored upon exit.

        Returns:
            'end': Inform the parent shell to to keep exiting until the root
                shell is reached.
            False, None, or anything that are evaluated as False: Exit this
                shell, enter the parent shell.

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
        self.print_debug("Enter subshell '{}'".format(self.prompt))

        # Save the completer function, the history buffer, and the
        # completer_delims.
        old_completer = readline.get_completer()
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)
        old_delims = readline.get_completer_delims()
        new_delims = ''.join(list(set(old_delims) - set(Shell._non_delims)))
        readline.set_completer_delims(new_delims)

        # Load the new completer function and start a new history buffer.
        readline.set_completer(self._driver_completer)

        # main loop
        try:
            # The exit_directive could be one { True, False, 'end' }.
            #       True:   Leave this shell, enter the parent shell.
            #       False:  Continue with the loop.
            #       'end':  Exit to the root shell.
            # TODO: For the above logic, the if-elif statements in the while
            # loop seems a bit convoluted.  Maybe it could be cleaner.
            exit_directive = False
            while True:
                if exit_directive == 'end':
                    if self._mode_stack:
                        break
                elif exit_directive == True:
                    break
                try:
                    line = input(self.prompt).strip()
                except EOFError:
                    line = Shell.EOF
                exit_directive = self._onecmd(line)
        finally:
            # Restore the completer function, save the history, and restore old
            # delims.
            readline.set_completer(old_completer)
            readline.write_history_file(self.history_fname)
            readline.set_completer_delims(old_delims)

        self.print_debug("Leave subshell '{}': {}".format(self.prompt, exit_directive))

        return exit_directive

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
        """Execute a command.

        emptyline: no-op
        unknown command: print error message
        known command: invoke the corresponding method
        """
        if not line:
            return

        cmd, args = self._parse_line(line)
        if not cmd in self._cmd_map.keys():
            self.stderr.write("{}: command not found\n".format(cmd))
            return

        func_name = self._cmd_map[cmd]
        func = getattr(self, func_name)
        return func(args)

    @command('end')
    def _do_end(self, args):
        """Exit to the root shell."""
        return 'end'

    @command('exec')
    def _do_exec(self, args):
        """Execute a command using subprocess.Popen()."""
        if not args:
            self.stderr.write("exec: empty command\n")
            return
        proc = subprocess.Popen(args, shell = True, stdout = self.stdout)
        proc.wait()

    @command('exit')
    def _do_exit(self, args):
        """Exit this shell. Same as C-D."""
        return True

    @command('help')
    def _do_help(self, args):
        """Print help messages most relevant to the current line."""
        pass

    @command('history')
    def _do_history(self, args):
        """Dump the history in this shell.

        A side effect is that this method flushes the current history buffer to
        the history file, whose file name is given by the history_fname
        property.
        """
        readline.write_history_file(self.history_fname)
        with open(self.history_fname, 'r', encoding = 'utf8') as f:
            self.stdout.write(f.read())

    def _driver_completer(self, text, state):
        """Driver level completer function of this shell.

        The interface of this method is defined the readline library.

        If the command ends with '?', invoke the help method, __help(), to
        provide most relevant help messages and valid candidates.

        If the command does not end with '?', invoke the actual completer
        method, __complete().

        Arguments:
            text: A string, that is the current completion scope.
            state: An integer.

        Returns:
            A string used to replace the given text, if any.
            None if no completion candidates are found.
        """
        origline = readline.get_line_buffer()
        line = origline.lstrip()
        offset = len(origline) - len(line)
        begidx = readline.get_begidx() - offset
        endidx = readline.get_endidx() - offset
        if begidx == 0:
            return self.__complete_cmds(text)[state]
        else:
            # TODO: Complete for general cases.
            return None

    def __complete_cmds(self, text):
        """Get the list of commands whose names start with a given text."""
        return [ name for name in self._cmd_map.keys() if name.startswith(text) ]
