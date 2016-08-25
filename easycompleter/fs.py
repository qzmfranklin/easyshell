import glob
import os

def find_matches(text):
    r"""Find matching files for text.

    For this completer to function in Unix systems, the readline module must not
    treat \ and / as delimiters.
    """
    path = os.path.expanduser(text)
    if os.path.isdir(path) and not path.endswith('/'):
        return [ text + '/' ]

    pattern = path + '*'
    is_implicit_cwd = not (path.startswith('/') or path.startswith('./'))
    if is_implicit_cwd:
        pattern = './' + pattern
    rawlist = glob.glob(pattern)
    ret = []
    for fname in rawlist:
        if is_implicit_cwd:
            fname = fname[2:]
        if os.path.isdir(fname):
            ret.append(fname + '/')
        else:
            ret.append(fname)
    return ret
