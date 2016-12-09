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


"""A generic class to build line-oriented command interpreters.
"""

import multiprocessing
import os
import readline
import shlex
import subprocess
import sys
import tempfile
import textwrap
import traceback

def isdeprecated(f):
    """Is the function object deprecated or not."""
    return hasattr(f, '__deprecated__') and f.__deprecated__

def iscommand(f):
    """Is the function object a command or not."""
    return hasattr(f, '__command__')

def deprecated(f):
    """Decorate a function object as deprecated.

    Work nicely with the @command and @subshell decorators.

    Add a __deprecated__ field to the input object and set it to True.
    """
    def inner_func(*args, **kwargs):
        print(textwrap.dedent("""\
                This command is deprecated and is subject to complete
                removal at any later version without notice.
                """))
        f(*args, **kwargs)
    inner_func.__deprecated__ = True
    inner_func.__doc__ = f.__doc__
    inner_func.__name__ = f.__name__
    if iscommand(f):
        inner_func.__command__ = f.__command__
    return inner_func

# Decorators with arguments is a little bit tricky to get right. A good
# thread on it is:
#       http://stackoverflow.com/questions/5929107/python-decorators-with-parameters
def command(*commands, visible = True, internal = False, nargs = '*'):
    """Decorate a function to be the entry function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.
        visible: This command is visible in tab completions.
        internal: The lexing rule is unchanged even if the parse_line() method
            is overloaded in the subclasses.
        nargs: Short for number of arguments. Similar to the nargs argument in
            the argparse module. Has the following valid values:
                    a non-negative integer
                    a list/set/tuple/range of non-negative integers
                    '*':        zero or more
                    '?':        zero or one
                    '+':        one or more
            The command method, whose interface is described below, will check
            the number of arguments. If it does not match this nargs argument,
            an error message will be printed to self.stderr and the shell is
            resumed.

    ----------------------------
    Interface of command methods:

        @command('foo', 'bar')
        def bar(self, args):
            '''The method invoked by 'foo' and 'bar' commands.

            Arguments:
                args: A list of strings. This list is obtianed via
                    shlex.split().
            '''
            pass
    """
    # Strict checking of the nargs argument.
    allowed_strs = {'*', '?', '+'}
    err_str = textwrap.dedent('''\
            command: '{}' is invalid, must be a non-negative integer, a
            list/set/tuple/range of non-negative integer, or one of {}
            '''.format(nargs, allowed_strs))
    if isinstance(nargs, str):
        if not nargs in allowed_strs:
            raise RuntimeError(err_str)
    elif isinstance(nargs, int):
        if nargs < 0:
            raise RuntimeError(err_str)
    else:
        nargs = list(nargs)
        for ele in nargs:
            if not isinstance(ele, int) or ele < 0:
                raise RuntimeError(err_str)

    def decorated_func(f):
        def inner_func(self, cmd, args):
            # Check the number of args according to nargs.
            n = len(args)
            if isinstance(nargs, str):
                if nargs == '*':
                    pass
                elif nargs == '?':
                    if n > 1:
                        self.error("{}: expect 0 or 1 argument, provided {}: {}\n".
                                format(cmd, n, args))
                        return
                elif nargs == '+':
                    if n == 0:
                        self.error("{}: expect 1 or more arguments, provided {}: {}\n".
                                format(cmd, n, args))
                        return
            elif isinstance(nargs, int):
                if n != nargs:
                        self.error("{}: expect {} arguments, provided {}: {}\n".
                                format(cmd, nargs, n, args))
                        return
            else:
                # nargs is already converted to a list.
                if not n in nargs:
                        self.error("{}: the number of arguments could be one of "
                                "{}, provided {}: {}\n".
                                format(cmd, nargs, n, args))
                        return
            return f(self, cmd, args)
        inner_func.__name__ = f.__name__
        inner_func.__doc__ = f.__doc__
        inner_func.__command__ = {
                'commands': list(commands),
                'visible': visible,
                'internal': internal,
        }
        # If f is deprecated, inner_func should also be deprecated. Do not use
        # the deprecated() function directly, as that adds duplicate warning
        # message.
        if isdeprecated(f):
            inner_func.__deprecated__ = True
        return inner_func
    return decorated_func


# The naming convention is same as the inspect module, which has such predicate
# methods as isfunction, isclass, ismethod, etc..

def getcommands(f):
    """Get the list of commands that this function object is registered for."""
    return f.__command__['commands']


def isvisiblecommand(f):
    """Is the function object a visible command or not."""
    return getattr(f, '__command__')['visible']


def isinternalcommand(f):
    """Is the function object an internal command or not."""
    return getattr(f, '__command__')['internal']

def isdeprecatedcommand(f):
    """Is the function object an deprecated command or not."""
    return getattr(f, '__command__')['deprecated']

def helper(*commands):
    """Decorate a function to be the helper function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.

    ---------------------------
    Interface of helper methods:

        @helper('some-command')
        def help_foo(self, args):
            '''
            Arguments:
                args: A list of arguments.

            Returns:
                A string that is the help message.
            '''
            pass
    """
    def decorated_func(f):
        f.__help_targets__ = list(commands)
        return f
    return decorated_func


def ishelper(f):
    """Is the function object a helper function or not."""
    return hasattr(f, '__help_targets__')


def completer(*commands):
    """Decorate a function to be the completer function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.

    ------------------------------
    Interface of completer methods:

        @completer('some-other_command')
        def complete_foo(self, args, text):
            '''
            Arguments:
                args: A list of arguments. The first token, i.e, the command
                    itself, is not included.
                text: The scope of text being replaced.

                A few examples, with '$' representing the shell prompt and
                '|' represents the cursor position:
                        $ |
                        $ history|
                            handled by the __driver_completer() method
                        $ history |
                            args = []
                            text = ''
                        $ history cle|
                            args = []
                            text = 'cle'
                        $ history clear |
                            args = ['clear']
                            text = ''

            Returns:
                A list of candidates. If no candidate was found, return
                either [] or None.
            '''
            pass
    """
    def decorated_func(f):
        f.__complete_targets__ = list(commands)
        return f
    return decorated_func


def iscompleter(f):
    """Is the function object a completer function or not."""
    return hasattr(f, '__complete_targets__')


# A parametrized decorator decorating a method is very tricky. To fully
# understand, please first consult this thread:
#       http://stackoverflow.com/questions/11731136/python-class-method-decorator-w-self-arguments
# Then note that when the method being decorated is printed, its __name__
# attribute is unchanged but the repr() function displays the method as
# 'inner_func'.
def subshell(shell_cls, *commands, **kwargs):
    """Decorate a function to conditionally launch a _ShellBase subshell.

    Arguments:
        shell_cls: A subclass of _ShellBase to be launched.
        commands: Names of command that should trigger this function object.
        kwargs: The keyword arguments for the command decorator method.

    -----------------------------
    Interface of methods decorated by this decorator method:

        @command(SomeShellClass, 'foo', 'bar')
        def bar(self, cmd, args):
            '''The command 'foo' invokes this method then launches the subshell.

            Arguments:
                cmd: A string, the name of the command that triggered this
                    function. This is useful for knowing which command, in this
                    case, 'foo' or 'bar', triggered this method.
                args: The list of arguments passed along with the command.

            Returns:
                There are three categories of valid return values.
                    None, False, or anything that evaluates to False: The
                        subshell is not invoked. This is useful for making a
                        command conditionally launch a subshell.
                    String: A string will appended to the prompt string to
                        uniquely identify the subshell.
                    A 2-tuple of type (string, dict): The string will be
                        appended to the prompt string. The dictionary stores the
                        data passed to the subshell. These data are the context
                        of the subshell. The parent shell must conform to the
                        subhshell class in terms of which key-value pairs to
                        pass to the subshell.
            '''
            pass
    """
    def decorated_func(f):
        def inner_func(self, cmd, args):
            retval = f(self, cmd, args)
            # Do not launch the subshell if the return value is None.
            if not retval:
                return
            # Pass the context (see the doc string) to the subshell if the
            # return value is a 2-tuple. Otherwise, the context is just an empty
            # dictionary.
            if isinstance(retval, tuple):
                prompt, context = retval
            else:
                prompt = retval
                context = {}
            return self.launch_subshell(shell_cls, cmd, args,
                    prompt = prompt, context = context)
        inner_func.__name__ = f.__name__
        inner_func.__doc__ = f.__doc__
        obj = command(*commands, **kwargs)(inner_func) if commands else inner_func
        obj.__launch_subshell__ = shell_cls
        return obj
    return decorated_func


def issubshellcommand(f):
    """Does the function object launch a subshell or not."""
    return hasattr(f, '__launch_subshell__')

class _ShellBase(object):

    """Base shell class.

    This class implements the following core infrastructures:
          - Recursively launch subshell.
          - Register commands, helpers, and completers.
          - The ?<TAB> help experience.
          - Comment a line that starts with # .
          - Context of a shell.

    Subclasses in the same module must implement a few command methods and
    completer methods to become a functional shell:
          - ! (hidden)
          - exit
          - history
    """

    class _Mode(object):
        """Stack mode information used when entering and leaving a subshell.

        Attributes:
            shell: This subshell.
            cmd: The command, as a unicode string, that was issued in the parent
                shell for entering this subshell.
            args: Any additional arguments that were issued with the @cmd.
            prompt: The unicode string to add to the prompt.
            context: A dictionary storing the contextual information that the
                subshell will utilize.
        """
        def __init__(self, *, shell, cmd, args, prompt, context):
            self.shell = shell
            self.cmd = cmd
            self.args = args
            self.prompt = prompt
            self.context = context

    EOF = chr(ord('D') - 64)

    # These characters are not treated as delimiters.
    #   char    |       rationale
    # ----------+--------------------------------------------------------
    #     -     |  Allow commands to contain '-'.
    # ----------+--------------------------------------------------------
    #     /\    |  Allow generic filename matching.
    # ----------+--------------------------------------------------------
    #     ~     |  Allow '~' to be expanded to $HOME.
    _non_delims = r'-/\~'

    def __init__(self, *,
            batch_mode = False,
            debug = False,
            mode_stack = [],
            pipe_end = None,
            root_prompt = 'root',
            stdout = sys.stdout,
            stderr = sys.stderr,
            temp_dir = None):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            batch_mode: stdin is superseded by the pipe_end.
            debug: If True, print_debug() prints to self.stderr.
            mode_stack: A stack of _ShellBase._Mode objects.
            pipe_end: The receiving end of the pipe when run in batch mode.
            root_prompt: The root prompt.
            stdout, stderr: The file objects to write to for output and error.
            temp_dir: The temporary directory to save history files. The default
                value, None, means to generate such a directory.
        """
        self.batch_mode = batch_mode
        self._pipe_end = pipe_end
        self.debug = debug
        self.stdout = stdout
        self.stderr = stderr
        self._mode_stack = mode_stack
        self.root_prompt = root_prompt
        self._temp_dir = temp_dir if temp_dir else tempfile.mkdtemp()
        os.makedirs(os.path.join(self._temp_dir, 'history'), exist_ok = True)

        readline.parse_and_bind('tab: complete')

        # Even though __build_XXX_map() methods are class methods, they must be
        # called via self. Otherwise they cannot find the commands.
        self._cmd_map_all, self._cmd_map_visible, self._cmd_map_internal = self.__build_cmd_maps()
        self._helper_map = self.__build_helper_map()
        self._completer_map = self.__build_completer_map()

        self.__completion_candidates = []

    @property
    def context(self):
        """Get the context dictionary of this shell.

        If this shell is a subshell, the context dictionary is passed via the
        second element of the 2-tuple of the return value of the the method
        decorated by the @subshell decorator. See the doc string of the
        @subshell decorator method for how that is done.

        If this shell is the root shell or the parent shell passed an empty
        context to this shell, this property returns an empty dictionary.
        """
        return self._mode_stack[-1].context

    @classmethod
    def doc_string(cls):
        """Get the doc string of this class.

        If this class does not have a doc string or the doc string is empty, try
        its base classes until the root base class, _ShellBase, is reached.

        CAVEAT:
            This method assumes that this class and all its super classes are
            derived from _ShellBase or object.
        """
        clz = cls
        while not clz.__doc__:
            clz = clz.__bases__[0]
        return clz.__doc__

    @property
    def prompt(self):
        return '({})$ '.format('-'.join(
                [ self.root_prompt ] + \
                [ m.prompt for m in self._mode_stack ]))

    @property
    def history_fname(self):
        """The temporary for storing the history of this shell."""
        return os.path.join(self._temp_dir, 'history', 's-' + self.prompt[1:-2])

    @property
    def parent(self):
        """The immediate parent shell object that launched this shell."""
        return self._mode_stack[-1].shell

    def print_debug(self, msg):
        if self.debug:
            print(msg, file = self.stderr)

    def error(self, msg):
        """Print message to self.stderr as-is."""
        self.stderr.write(msg)

    def warning(self, msg):
        """Print a warning to self.stdout as=is."""
        self.stdout.write(msg)

    def launch_subshell(self, shell_cls, cmd, args, *, prompt = None, context =
            {}):
        """Launch a subshell.

        The doc string of the cmdloop() method explains how shell histories and
        history files are saved and restored.

        The design of the _ShellBase class encourage launching of subshells through
        the subshell() decorator function. Nonetheless, the user has the option
        of directly launching subshells via this method.

        Arguments:
            shell_cls: The _ShellBase class object to instantiate and launch.
            args: Arguments used to launch this subshell.
            prompt: The name of the subshell. The default, None, means
                to use the shell_cls.__name__.
            context: A dictionary to pass to the subshell as its context.

        Returns:
            'root': Inform the parent shell to keep exiting until the root shell
                is reached.
            'all': Exit the the command line.
            False, None, or anything that are evaluated as False: Inform the
                parent shell to stay in that parent shell.
            An integer indicating the depth of shell to exit to. 0 = root shell.
        """
        # Save history of the current shell.
        readline.write_history_file(self.history_fname)

        prompt = prompt if prompt else shell_cls.__name__
        mode = _ShellBase._Mode(
                shell = self,
                cmd = cmd,
                args = args,
                prompt = prompt,
                context = context,
        )
        shell = shell_cls(
                batch_mode = self.batch_mode,
                debug = self.debug,
                mode_stack = self._mode_stack + [ mode ],
                pipe_end = self._pipe_end,
                root_prompt = self.root_prompt,
                stdout = self.stdout,
                stderr = self.stderr,
                temp_dir = self._temp_dir,
        )
        # The subshell creates its own history context.
        self.print_debug("Leave parent shell '{}'".format(self.prompt))
        exit_directive = shell.cmdloop()
        self.print_debug("Enter parent shell '{}': {}".format(self.prompt, exit_directive))

        # Restore history. The subshell could have deleted the history file of
        # this shell via 'history clearall'.
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)

        if not exit_directive is True:
            return exit_directive

    def batch_string(self, content):
        """Process a string in batch mode.

        Arguments:
            content: A unicode string representing the content to be processed.
        """
        pipe_send, pipe_recv = multiprocessing.Pipe()
        self._pipe_end = pipe_recv
        proc = multiprocessing.Process(target = self.cmdloop)
        for line in content.split('\n'):
            pipe_send.send(line)
        pipe_send.close()
        proc.start()
        proc.join()

    def preloop(self):
        pass

    def postloop(self):
        pass

    def cmdloop(self):
        """Start the main loop of the interactive shell.

        The preloop() and postloop() methods are always run before and after the
        main loop, respectively.

        Returns:
            'root': Inform the parent shell to to keep exiting until the root
                shell is reached.
            'all': Exit all the way back the the command line shell.
            False, None, or anything that are evaluated as False: Exit this
                shell, enter the parent shell.
            An integer: The depth of the shell to exit to. 0 = root shell.

        History:

            _ShellBase histories are persistently saved to files, whose name matches
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
        new_delims = ''.join(list(set(old_delims) - set(_ShellBase._non_delims)))
        readline.set_completer_delims(new_delims)

        # Load the new completer function and start a new history buffer.
        readline.set_completer(self.__driver_stub)
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)

        # main loop
        try:
            # The exit_directive:
            #       True        Leave this shell, enter the parent shell.
            #       False       Continue with the loop.
            #       'root'      Exit to the root shell.
            #       'all'       Exit to the command line.
            #       an integer  The depth of the shell to exit to. 0 = root
            #                   shell. Negative number is taken as error.
            self.preloop()
            while True:
                exit_directive = False
                try:
                    if self.batch_mode:
                        line = self._pipe_end.recv()
                    else:
                        line = input(self.prompt).strip()
                except EOFError:
                    line = _ShellBase.EOF

                try:
                    exit_directive = self.__exec_line__(line)
                except:
                    self.stderr.write(traceback.format_exc())

                if type(exit_directive) is int:
                    if len(self._mode_stack) > exit_directive:
                        break
                    if len(self._mode_stack) == exit_directive:
                        continue
                if self._mode_stack and exit_directive == 'root':
                    break
                if exit_directive in { 'all', True, }:
                    break
        finally:
            self.postloop()
            # Restore the completer function, save the history, and restore old
            # delims.
            readline.set_completer(old_completer)
            readline.write_history_file(self.history_fname)
            readline.set_completer_delims(old_delims)

        self.print_debug("Leave subshell '{}': {}".format(self.prompt, exit_directive))

        return exit_directive

    def __exec_line__(self, line):
        r"""Execute the input line.

        emptyline: no-op
        unknown command: print error message
        known command: invoke the corresponding method

        The parser method, parse_line(), can be overriden in subclasses to
        apply different parsing rules. Please refer to the doc string of
        parse_line() for complete information.

        Arguments:
            line: A string, representing a line of input from the shell. This
                string is preprocessed by cmdloop() to convert the EOF character
                to '\x04', i.e., 'D' - 64, if the EOF character is the only
                character from the shell.
        """
        # Ignoe empty lines and lines starting with a pound sign.
        if not line or line.rstrip().startswith('#'):
            return

        cmd, args = ( '', [] )

        toks = shlex.split(line)
        if not toks:
            return

        if line == _ShellBase.EOF:
            # This is a hack to allow the EOF character to behave exactly like
            # typing the 'exit' command.
            readline.insert_text('exit\n')
            readline.redisplay()
            cmd = 'exit'
        elif toks and toks[0] in self._cmd_map_internal.keys():
            cmd = toks[0]
            args = toks[1:] if len(toks) > 1 else []
        else:
            cmd, args = self.parse_line(line)

        if not cmd in self._cmd_map_all.keys():
            self.stderr.write("{}: command not found\n".format(cmd))
            return

        func_name = self._cmd_map_all[cmd]
        func = getattr(self, func_name)
        return func(cmd, args)

    def parse_line(self, line):
        """Parse a line of input.

        The input line is tokenized using the same rules as the way bash shell
        tokenizes inputs. All quoting and escaping rules from the bash shell
        apply here too.

        The following cases are handled by __exec_line__():
            1.  Empty line.
            2.  The input line is completely made of whitespace characters.
            3.  The input line is the EOF character.
            4.  The first token, as tokenized by shlex.split(), is '!'.
            5.  Internal commands, i.e., commands registered with internal =
                    True

        Arguments:
            The line to parse.

        Returns:
            A tuple (cmd, args). The first element cmd must be a python3 string.
            The second element is, by default, a list of strings representing
            the arguments, as tokenized by shlex.split().

        How to overload parse_line():
            1.  The signature of the method must be the same.
            2.  The return value must be a tuple (cmd, args), where the cmd is
                a string representing the first token, and args is a list of
                strings.
        """
        toks = shlex.split(line)
        # Safe to index the 0-th element because this line would have been
        # parsed by __exec_line__ if toks is an empty list.
        return ( toks[0], [] if len(toks) == 1 else toks[1:] )

    def __driver_stub(self, text, state):
        """Display help messages or invoke the proper completer.

        The interface of helper methods and completer methods are documented in
        the helper() decorator method and the completer() decorator method,
        respectively.

        Arguments:
            text: A string, that is the current completion scope.
            state: An integer.

        Returns:
            A string used to replace the given text, if any.
            None if no completion candidates are found.

        Raises:
            This method is called via the readline callback. If this method
            raises an error, it is silently ignored by the readline library.
            This behavior makes debugging very difficult. For this reason,
            non-driver methods are run within try-except blocks. When an error
            occurs, the stack trace is printed to self.stderr.
        """
        origline = readline.get_line_buffer()
        line = origline.lstrip()
        if line and line[-1] == '?':
            self.__driver_helper(line)
        else:
            toks = shlex.split(line)
            return self.__driver_completer(toks, text, state)

    def __driver_completer(self, toks, text, state):
        """Driver level completer.

        Arguments:
            toks: A list of tokens, tokenized from the original input line.
            text: A string, the text to be replaced if a completion candidate is
                chosen.
            state: An integer, the index of the candidate out of the list of
                candidates.

        Returns:
            A string, the candidate.

        """
        if state != 0:
            return self.__completion_candidates[state]

        # Update the cache when this method is first called, i.e., state == 0.

        # If the line is empty or the user is still inputing the first token,
        # complete with available commands.
        if not toks or (len(toks) == 1 and text == toks[0]):
            try:
                self.__completion_candidates = self.__complete_cmds(text)
            except:
                self.stderr.write('\n')
                self.stderr.write(traceback.format_exc())
                self.__completion_candidates = []
            return self.__completion_candidates[state]

        # Otherwise, try to complete with the registered completer method.
        cmd = toks[0]
        args = toks[1:] if len(toks) > 1 else None
        if text and args:
            del args[-1]
        if cmd in self._completer_map.keys():
            completer_name = self._completer_map[cmd]
            completer_method = getattr(self, completer_name)
            try:
                self.__completion_candidates = completer_method(cmd, args, text)
            except:
                self.stderr.write('\n')
                self.stderr.write(traceback.format_exc())
                self.__completion_candidates = []
        else:
            self.__completion_candidates = []

        return self.__completion_candidates[state]

    def __complete_cmds(self, text):
        """Get the list of commands whose names start with a given text."""
        return [ name for name in self._cmd_map_visible.keys() if name.startswith(text) ]

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

        Looks for the help message in the following order:

            1.  The helper method registered with this command via the @helper
                decorator.
            2.  The doc string of the registered method.
            3.  A default help message basically saying 'no help found'.

        Arguments:
            toks: The list of command followed by its arguments.

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
            return helper_method(cmd, args)

        if cmd in self._cmd_map_all.keys():
            name = self._cmd_map_all[cmd]
            method = getattr(self, name)
            if method.__doc__:
                return textwrap.dedent(method.__doc__)

        return textwrap.dedent('''\
                       No help message is found for:
                       {}
                       '''.format(textwrap.indent(
                           subprocess.list2cmdline(toks), '    ')))


    ################################################################################
    # _build_XXX_map() methods are only used by _ShellBase.__init__() method.
    # TODO: The internal logic looks so similar. Should consider merging these
    # methods.
    ################################################################################

    @classmethod
    def __build_cmd_maps(cls):
        """Build the mapping from command names to method names.

        One command name maps to at most one method.
        Multiple command names can map to the same method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Returns:
            A tuple (cmd_map, hidden_cmd_map, internal_cmd_map).
        """
        cmd_map_all = {}
        cmd_map_visible = {}
        cmd_map_internal = {}
        for name in dir(cls):
            obj = getattr(cls, name)
            if iscommand(obj):
                for cmd in getcommands(obj):
                    if cmd in cmd_map_all.keys():
                        raise PyShellError("The command '{}' already has cmd"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, cmd_map_all[cmd], obj.__name__))
                    cmd_map_all[cmd] = obj.__name__
                    if isvisiblecommand(obj):
                        cmd_map_visible[cmd] = obj.__name__
                    if isinternalcommand(obj):
                        cmd_map_internal[cmd] = obj.__name__
        return cmd_map_all, cmd_map_visible, cmd_map_internal

    @classmethod
    def __build_helper_map(cls):
        """Build a mapping from command names to helper names.

        One command name maps to at most one helper method.
        Multiple command names can map to the same helper method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Raises:
            PyShellError: A command maps to multiple helper methods.
        """
        ret = {}
        for name in dir(cls):
            obj = getattr(cls, name)
            if ishelper(obj):
                for cmd in obj.__help_targets__:
                    if cmd in ret.keys():
                        raise PyShellError("The command '{}' already has helper"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, ret[cmd], obj.__name__))
                    ret[cmd] = obj.__name__
        return ret

    @classmethod
    def __build_completer_map(cls):
        """Build a mapping from command names to completer names.

        One command name maps to at most one completer method.
        Multiple command names can map to the same completer method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Raises:
            PyShellError: A command maps to multiple helper methods.
        """
        ret = {}
        for name in dir(cls):
            obj = getattr(cls, name)
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
