"""A generic class to build line-oriented command interpreters.
"""

import os
import readline
import shlex
import subprocess
import sys
import tempfile
import textwrap
import traceback

# Decorators with arguments is a little bit tricky to get right. A good
# thread on it is:
#       http://stackoverflow.com/questions/5929107/python-decorators-with-parameters
def command(*commands):
    """Decorate a function to be the entry function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.
    """
    def decorated_func(f):
        f.__command__ = list(commands)
        return f
    return decorated_func

# The naming convention is same as the inspect module, which has such predicate
# methods as isfunction, isclass, ismethod, etc..
def iscommand(f):
    """Is the function object a command or not."""
    return hasattr(f, '__command__')

def helper(*commands):
    """Decorate a function to be the helper function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.
    """
    def decorated_func(f):
        f.__help_targets__ = list(commands)
        return f
    return decorated_func

def ishelper(f):
    """Is the function object a completer function or not."""
    return hasattr(f, '__help_targets__')

def completer(*commands):
    """Decorate a function to be the completer function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.
    """
    def decorated_func(f):
        f.__complete_targets__ = list(commands)
        return f
    return decorated_func

def iscompleter(f):
    """Is the function object a completer function or not."""
    return hasattr(f, '__help_complete__')

# A parametrized decorator decorating a method is very tricky. To fully
# understand, please first consult this thread:
#       http://stackoverflow.com/questions/11731136/python-class-method-decorator-w-self-arguments
# Then note that when the method being decorated is printed, its __name__
# attribute is unchanged but the repr() function displays the method as
# 'inner_func'.
def subshell(shell_cls, *commands):
    """Decorate a function to launch a Shell subshell.

    Arguments:
        shell_cls: A subclass of Shell to be launched.
        commands: Names of command that should trigger this function object.

    Returns:
        A string used as the prompt.
    """
    def decorated_func(f):
        def inner_func(self, args):
            prompt_display = f(self, args)
            return self.launch_subshell(shell_cls, args,
                    prompt_display = prompt_display)
        inner_func.__name__ = f.__name__
        return command(*commands)(inner_func) if commands else inner_func
    return decorated_func

class Shell(object):

    """Recursive interactive shell.

    Exit shell:
            end                 exit to the root shell
            exit, C-D           exit to the parent shell

    Manipulate history:
            history             display history of this shell
            history clear       clear history of this shell

    Execute a command in the Linux shell:
            ! <command>         execute <command> using subprocess.Popen

    Get help:
            <TAB>               display all valid commands
            ?<TAB>              display this message
            {help|?}<CR>        display this message
            {help|?} <command>  display high level help message about <command>
            <command> [args]?<TAB>
                                display help message for the incomplete command:
                                    <command> [args]
    """

    class _Mode(object):
        """Stack mode information used when entering and leaving a subshell.
        """
        def __init__(self, args, prompt_display):
            self.args = args
            self.prompt_display = prompt_display

    EOF = chr(ord('D') - 64)
    _non_delims = '-?'

    def __init__(self, *,
            debug = False,
            mode_stack = [],
            root_prompt = 'root',
            stdout = sys.stdout,
            stderr = sys.stderr,
            temp_dir = None):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            debug: If True, print_debug() prints to self.stderr.
            mode_stack: A stack of Shell._Mode objects.
            root_prompt: The root prompt.
            stdout, stderr: The file objects to write to for output and error.
            temp_dir: The temporary directory to save history files. The default
                value, None, means to generate such a directory.
        """
        self.debug = debug
        self.stdout = stdout
        self.stderr = stderr
        self._mode_stack = mode_stack
        self.root_prompt = root_prompt
        self._temp_dir = temp_dir if temp_dir else tempfile.mkdtemp()
        os.makedirs(os.path.join(self._temp_dir, 'history'), exist_ok = True)

        readline.parse_and_bind('tab: complete')

        self._cmd_map = self.__build_cmd_map()
        self._helper_map = self.__build_helper_map()
        self._completer_map = self.__build_completer_map()

    def __build_cmd_map(self):
        """Build a mapping from command names to method names.

        One command name maps to at most one method.
        Multiple command names can map to the same method.

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

    def __build_helper_map(self):
        """Build a mapping from command names to helper names.

        One command name maps to at most one helper method.
        Multiple command names can map to the same helper method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Raises:
            PyShellError: A command maps to multiple helper methods.
        """
        ret = {}
        for name in dir(self):
            obj = getattr(self, name)
            if ishelper(obj):
                for cmd in obj.__help_targets__:
                    if cmd in ret.keys():
                        raise PyShellError("The command '{}' already has helper"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, ret[cmd], obj.__name__))
                    ret[cmd] = obj.__name__
        return ret

    def __build_completer_map(self):
        """Build a mapping from command names to completer names.

        One command name maps to at most one completer method.
        Multiple command names can map to the same completer method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Raises:
            PyShellError: A command maps to multiple helper methods.
        """
        ret = {}
        for name in dir(self):
            obj = getattr(self, name)
            if iscompleter(obj):
                for cmd in obj.__complete_targets__:
                    if cmd in ret.keys():
                        raise PyShellError("The command '{}' already has"
                                           " complter"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, ret[cmd], obj.__name__))
                    ret[cmd] = obj.__name__
        return ret

    @property
    def prompt(self):
        return '({})$ '.format('-'.join(
                [ self.root_prompt ] + \
                [ m.prompt_display for m in self._mode_stack ]))

    @property
    def history_fname(self):
        """The temporary for storing the history of this shell."""
        return os.path.join(self._temp_dir, 'history', 's-' + self.prompt[1:-2])

    def print_debug(self, msg):
        if self.debug:
            print(msg, file = self.stderr)

    def launch_subshell(self, shell_cls, args, *, prompt_display = None):
        """Launch a subshell.

        The doc string of the cmdloop() method explains how shell histories and
        history files are saved and restored.

        The design of the Shell class encourage launching of subshells through
        the subshell() decorator function. Nonetheless, the user has the option
        of directly launching subshells via this method.

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
                debug = self.debug,
                mode_stack = self._mode_stack + [ mode ],
                root_prompt = self.root_prompt,
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
        """Start the interactive shell.

        Returns:
            'end': Inform the parent shell to to keep exiting until the root
                shell is reached.
            False, None, or anything that are evaluated as False: Exit this
                shell, enter the parent shell.

        History:

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

            Certain characters such as '-' could be part of a command. But by
            default they are considered the delimiters by the readline library,
            which causes completion candidates with those characters to
            malfunction.

            The old completer delimiters are saved before the loop and restored
            after the loop ends. This is to keep the environment clean.
        """
        self.print_debug("Enter subshell '{}'".format(self.prompt))

        # Save the completer function, the history buffer, and the
        # completer_delims.
        old_completer = readline.get_completer()
        old_delims = readline.get_completer_delims()
        new_delims = ''.join(list(set(old_delims) - set(Shell._non_delims)))
        readline.set_completer_delims(new_delims)

        # Load the new completer function and start a new history buffer.
        readline.set_completer(self.__driver_completer)
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)

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
                exit_directive = self.__exec_cmd(line)
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

        '?'     => help
        '!'     => shell
        C-D     => exit, insert 'exit\\n' to the command line.
        other   => other commands

        The input line is tokenized using the same rules as the way bash shell
        tokenizes inputs. All quoting and escaping rules from the bash shell
        apply here too.

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

    def __exec_cmd(self, line):
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
        if not args:
            self.stdout.write(self.doc_string())
            self.stdout.write('\n')
            sys.stdout.flush()
        else:
            # TODO: use registered helper function.
            pass

    @command('history')
    def _do_history(self, args):
        """Dump the history in this shell.

        A side effect is that this method flushes the current history buffer to
        the history file, whose file name is given by the history_fname
        property.
        """
        if args and args[0] == 'clear':
            readline.clear_history()
            readline.write_history_file(self.history_fname)
        else:
            readline.write_history_file(self.history_fname)
            with open(self.history_fname, 'r', encoding = 'utf8') as f:
                self.stdout.write(f.read())

    @helper('history')
    def _help_history(self, args_ignored):
        return textwrap.dedent('''\
                history             Display history
                history clear       Clear history
                ''')

    def __driver_completer(self, text, state):
        """Display help messages and complete.

        Arguments:
            text: A string, that is the current completion scope.
            state: An integer.

        Returns:
            A string used to replace the given text, if any.
            None if no completion candidates are found.

        Raises:
            As this function is called via the readline complete callback, any
            errors and exceptions are silently ignored.

        Ideally, a seperate callback method, __get_help_message() should be
        registered with the readline library to be triggered with the '?'
        character. That would give the user a very convenient and clean way of
        displaying the most relevant help messages, i.e., entering '?' shows
        help messages without changing the line buffer.

        Unfortunately, the python readline library does not expose such an
        interface for us.

        Given this restriction, here is what I have decided to do:
          - The user types the '?' character *and* hit tab to display
            help messages.
          - The '?' character + tab only triggers the display of help messages
            when the '?' character is the last non-whitespace character in the
            line buffer.
          - If the '?' character is the leading non-whitespace character in the
            line buffer, it is interpreted as the 'help' command.
          - If '?' is the only non-whitespace character, display self.__doc__,
          - If a '?' character is neither the leading nor the trailing
            non-whitespace character, it is treated as part of the arguments.
          - The trailing non-whitespace '?' character persists after the help
            messages are displayed.
        """
        origline = readline.get_line_buffer()

        # If the line ends with '?', instead of looking for completion
        # candidates, display help messages.
        line = origline.lstrip()
        if line and line[-1] == '?':
            self.__driver_helper(line)
            return

        # Try to complete the line.
        line = origline.lstrip()
        offset = len(origline) - len(line)
        begidx = readline.get_begidx() - offset
        endidx = readline.get_endidx() - offset
        try:
            if begidx == 0:
                # If the line is empty, list all commands.
                return self.__complete_cmds(text)[state]
            else:
                # TODO: Otherwise, try the completer method registered with the command.
                return
        except IndexError:
            pass
        except:
            self.stderr.write('\n')
            self.stderr.write(traceback.format_exc())

    @classmethod
    def doc_string(cls):
        """Get the doc string of this class.

        If this class does not have a doc string or the doc string is empty, try
        its base classes until the root base class, Shell, is reached.

        CAVEAT:
            This method assumes that this class and all its super classes are
            derived from Shell or object.
        """
        clz = cls
        while not clz.__doc__:
            clz = clz.__bases__[0]
        return clz.__doc__

    def __complete_cmds(self, text = ''):
        """Get the list of commands whose names start with a given text."""
        return [ name for name in self._cmd_map.keys() if name.startswith(text) ]

    def __driver_helper(self, line):
        """Driver level helper method.

        1.  Display help message for the given input. Internally calls
            self.__get_help_message() to obtain the help message.
        2.  Re-display the prompt and the input line.

        Arguments:
            line: The input line.

        Raises:
            Errors from helper methods print stack trace without terminating
            this shell. Other exceptions will terminate this shell.
        """
        if line.strip() == '?':
            self.stdout.write('\n')
            self.stdout.write(self.doc_string())
        else:
            toks = shlex.split(line[:-1])
            try:
                msg = self.__get_help_message(toks)
            except Exception as e:
                self.stderr.write('\n')
                self.stderr.write(traceback.format_exc())
                self.stderr.flush()
            self.stdout.write('\n')
            self.stdout.write(msg)
        # Restore the prompt and the original input.
        self.stdout.write('\n')
        self.stdout.write(self.prompt)
        self.stdout.write(line)
        self.stdout.flush()

    def __get_help_message(self, toks):
        """Write help message to file.

        Only called by the __driver_helper() method.

        Arguments:
            toks: The list of command followed by its arguments.
            fp: The file-like object to write help messages to.

        Returns:
            The help message.

        Raises:
             As this function is called via the readline complete callback, any
             errors and exceptions are silently ignored.
        """
        cmd = toks[0]
        if cmd in self._helper_map.keys():
            helper_name = self._helper_map[cmd]
            helper_method = getattr(self, helper_name)
            args = toks[1:] if len(toks) > 1 else []
            return helper_method(args)
        else:
            return textwrap.dedent('''\
                            No help message is found for:
                            {}
                            '''.format(textwrap.indent(subprocess.list2cmdline(toks), '    ')))
