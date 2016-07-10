import glob
import os

def find_matches(text):
    """Find matching files for text.

    For this completer to function in Unix systems, the readline module must not
    treat \\ and / as delimiters.
    """
    path = os.path.expanduser(text)
    if os.path.isdir(path) and not path.endswith('/'):
        return [ text + '/' ]

    pattern = path + '*'
    is_implicit_cwd = path.startswith('/') or path.startswith('./')
    if is_implicit_cwd:
        pattern = './' + pattern
    rawlist = glob.glob(pattern)
    if is_implicit_cwd:
        return [ fname[2:] for fname in rawlist ]
    else:
        return rawlist
