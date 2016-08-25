import pprint
import shlex
import textwrap
import traceback

import easycompleter

from .base import command, helper, completer
from .basic_shell import BasicShell

class DebuggingShell(BasicShell):

    """Debugging shell.

    DISCLAIMER: This debugging shell is still highly experimental.

    Lexer is changed. For example, '  foo   dicj didiw  ' is tokenized as
            [ 'foo', '   dicj didiw  ' ]

    Available commands:
            p               Display object.
            e               Evaluate python code.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__python_completer = easycompleter.python_default.Completer()

    # TODO: This completer is not fully functional.
    @completer('p')
    def _complete_print(self, cmd, arg, text):
        return self.__python_completer.find_matches(text)

    # TODO: This method is not fully implemented yet.
    @command('p')
    def _do_print(self, cmd, args):
        """\
        Display symbols.
            p               Display names of inspectable objects.
            p <id>          Display the content of an object.
        """
        name = args[0].strip()
        if not name:
            self.stderr.write('TODO: Display names of inspectable objects.\n')
            return
        try:
            code = textwrap.dedent(r'''
                    self.stdout.write(name + ':\n' + textwrap.indent(pprint.pformat({}), '    ') + '\n')
                    ''').format(name).strip()
            eval(code, globals(), locals())
        except NameError:
            self.stderr.write("p: name '{}' is not defined\n".format(name))
        self.stdout.flush()


    # TODO: Use proper namespace for the dyncamic evaluation. According to the
    # current implementation existing variables may be overwritten.
    @command('e')
    def _do_eval(self, cmd, args):
        """\
        Evaluate python code.
            e <expr>        Evaluate <expr>.
        """
        code = args[0].lstrip()
        if not code:
            self.stderr.write('e: cannot evalutate empty expression\n')
            return
        try:
            eval(code)
        except:
            self.stderr.write('''When executing code '{}', the following error was raised:\n\n'''.format(code))
            self.stderr.write(textwrap.indent(traceback.format_exc(), '    '))


    def parse_line(self, line):
        """Parser for the debugging shell.

        Treat everything after the first token as one literal entity. Whitespace
        characters between the first token and the next first non-whitespace
        character are preserved.

        For example, '  foo   dicj didiw  ' is parsed as
            ( 'foo', '   dicj didiw  ' )

        Returns:
            A tuple (cmd, args), where the args is a list that consists of one
            and only one string containing everything after the cmd as is.
        """
        line = line.lstrip()
        toks = shlex.split(line)
        cmd = toks[0]
        arg = line[len(cmd):]
        return cmd, [ arg, ]
