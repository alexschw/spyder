# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Utilities for version control systems"""

from __future__ import print_function

import os
import os.path as osp
import subprocess
import sys

# Local imports
from spyder.config.base import running_under_pytest
from spyder.utils import programs
from spyder.utils.misc import abspardir
from spyder.py3compat import PY3


SUPPORTED = [
    {
        'name': 'Mercurial',
        'rootdir': '.hg',
        'actions': dict(
            commit=(('thg', ['commit']),
                    ('hgtk', ['commit'])),
            browse=(('thg', ['log']),
                    ('hgtk', ['log'])),
            cstate=(('hg', ['status', '-A']), )
        )
    }, {
        'name': 'Git',
        'rootdir': '.git',
        'actions': dict(
            commit=(('git', ['gui' if os.name == 'nt' else 'cola']), ),
            browse=(('gitk', []), ),
            cstate=(('git', ['status', '--ignored', '--porcelain']), )
        )
    }]


class ActionToolNotFound(RuntimeError):
    """Exception to transmit information about supported tools for
       failed attempt to execute given action"""

    def __init__(self, vcsname, action, tools):
        RuntimeError.__init__(self)
        self.vcsname = vcsname
        self.action = action
        self.tools = tools


def get_vcs_info(path):
    """Return support status dict if path is under VCS root"""
    for info in SUPPORTED:
        vcs_path = osp.join(path, info['rootdir'])
        if osp.isdir(vcs_path):
            return info


def get_vcs_root(path):
    """Return VCS root directory path
    Return None if path is not within a supported VCS repository"""
    previous_path = path
    while get_vcs_info(path) is None:
        path = abspardir(path)
        if path == previous_path:
            return
        else:
            previous_path = path
    return osp.abspath(path)


def is_vcs_repository(path):
    """Return True if path is a supported VCS repository"""
    return get_vcs_root(path) is not None


def run_vcs_tool(path, action):
    """If path is a valid VCS repository, run the corresponding VCS tool
    Supported VCS actions: 'commit', 'browse'
    Return False if the VCS tool is not installed"""
    info = get_vcs_info(get_vcs_root(path))
    tools = info['actions'][action]
    for tool, args in tools:
        if programs.find_program(tool):
            if not running_under_pytest():
                programs.run_program(tool, args, cwd=path)
            else:
                return True
            return
    else:
        cmdnames = [name for name, args in tools]
        raise ActionToolNotFound(info['name'], action, cmdnames)


def get_vcs_status(path):
    """Return the commit status."""
    rootPath = get_vcs_root(path)
    if not rootPath:
        return []
    info = get_vcs_info(rootPath)
    # Status list (in Order): untracked, ignored, modified, added
    if info['name'] == 'Git':
        stat = ["??", "!!", "M", "A"]
        o = 3  # position at which the filename starts
    elif info['name'] == 'Mercurial':
        stat = ["?", "I", "M", "A"]
        o = 2
    for tool, args in info['actions']['cstate']:
        if programs.find_program(tool):
            if not running_under_pytest():
                proc = programs.run_program(tool, args, cwd=rootPath)
                out, err = proc.communicate()
                if proc.returncode >= 0 and err == b'':
                    oStr = out.decode("utf-8")[:-1]
                    vcsst = {}
                    for fString in (x for x in oStr.split("\n") if x):
                        try:
                            index = stat.index(fString[:o-1].strip())
                        except ValueError:
                            continue
                        vcsst[fString[o:]] = index
                    return vcsst
                else:
                    return None
            else:
                return True
            return


def is_hg_installed():
    """Return True if Mercurial is installed"""
    return programs.find_program('hg') is not None


def get_hg_revision(repopath):
    """Return Mercurial revision for the repository located at repopath
       Result is a tuple (global, local, branch), with None values on error
       For example:
           >>> get_hg_revision(".")
           ('eba7273c69df+', '2015+', 'default')
    """
    try:
        assert osp.isdir(osp.join(repopath, '.hg'))
        proc = programs.run_program('hg', ['id', '-nib', repopath])
        output, _err = proc.communicate()
        # output is now: ('eba7273c69df+ 2015+ default\n', None)
        # Split 2 times max to allow spaces in branch names.
        return tuple(output.decode().strip().split(None, 2))
    except (subprocess.CalledProcessError, AssertionError, AttributeError,
            OSError):
        return (None, None, None)


def get_git_revision(repopath):
    """
    Return Git revision for the repository located at repopath
    Result is a tuple (latest commit hash, branch), with None values on
    error
    """
    try:
        git = programs.find_program('git')
        assert git is not None and osp.isdir(osp.join(repopath, '.git'))
        commit = programs.run_program(git, ['rev-parse', '--short', 'HEAD'],
                                      cwd=repopath).communicate()
        commit = commit[0].strip()
        if PY3:
            commit = commit.decode(sys.getdefaultencoding())

        # Branch
        branches = programs.run_program(git, ['branch'],
                                        cwd=repopath).communicate()
        branches = branches[0]
        if PY3:
            branches = branches.decode(sys.getdefaultencoding())
        branches = branches.split('\n')
        active_branch = [b for b in branches if b.startswith('*')]
        if len(active_branch) != 1:
            branch = None
        else:
            branch = active_branch[0].split(None, 1)[1]

        return commit, branch
    except (subprocess.CalledProcessError, AssertionError, AttributeError,
            OSError):
        return None, None


def get_git_refs(repopath):
    """
    Return Git active branch, state, branches (plus tags).
    """
    tags = []
    branches = []
    branch = ''
    files_modifed = []

    if os.path.isfile(repopath):
        repopath = os.path.dirname(repopath)

    try:

        git = programs.find_program('git')

        # Files modified
        out, err = programs.run_program(
            git, ['status', '-s'],
            cwd=repopath,
        ).communicate()

        if PY3:
            out = out.decode(sys.getdefaultencoding())
        files_modifed = [line.strip() for line in out.split('\n') if line]

        # Tags
        out, err = programs.run_program(
            git, ['tag'],
            cwd=repopath,
        ).communicate()

        if PY3:
            out = out.decode(sys.getdefaultencoding())
        tags = [line.strip() for line in out.split('\n') if line]

        # Branches
        out, err = programs.run_program(
            git, ['branch', '-a'],
            cwd=repopath,
        ).communicate()

        if PY3:
            out = out.decode(sys.getdefaultencoding())

        lines = [line.strip() for line in out.split('\n') if line]
        for line in lines:
            if line.startswith('*'):
                line = line.replace('*', '').strip()
                branch = line

            branches.append(line)

    except (subprocess.CalledProcessError, AttributeError, OSError):
        pass

    return branches + tags, branch, files_modifed
