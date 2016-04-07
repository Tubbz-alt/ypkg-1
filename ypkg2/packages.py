#!/bin/true
# -*- coding: utf-8 -*-
#
#  This file is part of ypkg2
#
#  Copyright 2015-2016 Ikey Doherty <ikey@solus-project.com>
#
#  Many portions of this are related to autospec, concepts included
#
#  Copyright (C) 2016 Intel Corporation
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from . import console_ui
from .stringglob import StringPathGlob

import os

PRIORITY_DEFAULT = 0    # Standard internal priority for a pattern
PRIORITY_USER = 100     # Priority for a user pattern, do what they say.


class DefaultPolicy(StringPathGlob):

    def __init__(self):
        StringPathGlob.__init__(self, "a")
        pass

class Package:

    patterns = None
    files = None
    excludes = None

    # Symbols provided by this package
    provided_symbols = None

    # Symbols depended upon by this package
    depend_symbols = None

    # pkgconfigs provided by this package
    provided_pkgconfig = None

    # pkgconfig32's provided by this package
    provided_pkgconfig32 = None

    # pkgconfig's we depend on
    depend_pkgconfig = None

    # pkgconfig32's we probably depend on
    depend_pkgconfig32 = None

    def __init__(self, name):
        self.name = name
        self.patterns = dict()
        self.files = set()
        self.excludes = set()

        self.provided_symbols = set()
        self.provided_pkgconfig = set()
        self.provided_pkgconfig32 = set()

        self.depend_symbols = set()
        self.depend_pkgconfig = set()
        self.depend_pkgconfig32 = set()
        self.default_policy = DefaultPolicy()

    def get_pattern(self, path):
        """ Return a matching pattern for the given path.
            This is ordered according to priority to enable
            multiple layers of priorities """
        matches = [p for p in self.patterns if p.match(path)]
        if len(matches) == 0:
            return self.default_policy

        matches = sorted(matches, key=StringPathGlob.get_priority,
                         reverse=True)
        return matches[0]

    def add_file(self, pattern, path):
        """ Add a file by a given pattern to this package """
        if pattern is None:
            pattern = self.default_policy
        if pattern not in self.patterns:
            self.patterns[pattern] = set()
        self.patterns[pattern].add(path)
        self.files.add(path)

    def remove_file(self, path):
        """ Remove a file from this package if it owns it """
        pat = self.get_pattern(path)
        if not pat:
            return
        if path in self.patterns[pat]:
            self.patterns[pat].remove(path)
        if path in self.files:
            self.files.remove(path)

    def exclude_file(self, path):
        """ Exclude a file from this package if it captures it """
        pat = self.get_pattern(path)
        if not pat:
            return
        if path in self.files:
            self.files.remove(path)
        self.excludes.add(path)

    def emit_files(self):
        """ Emit actual file lists, vs the globs we have """
        ret = set()
        for pt in self.patterns:
            adds = [x for x in self.patterns[pt] if x not in self.excludes]
            ret.update(adds)
        return sorted(ret)

    def emit_files_by_pattern(self):
        """ Emit file lists, using the globs though. Note that eopkg has no
            exclude concept, this is left for us to handle as we build the
            resulting eopkg ourselves """
        ret = set()
        for pt in self.patterns:
            pat = self.patterns[pt]

            tmp = set([x for x in pat if x not in self.excludes])
            if len(tmp) == 0:
                continue
            # Default policy, just list all the files
            if isinstance(pt, DefaultPolicy):
                ret.update(tmp)
            else:
                ret.add(str(pt))
        return sorted(ret)


class PackageGenerator:

    patterns = None
    packages = None

    def __init__(self):
        self.patterns = dict()
        self.packages = dict()

        # TODO: Make this come from a config file!
        self.add_pattern("/usr/lib64/lib*.so", "devel")
        self.add_pattern("/usr/lib64/lib*.a", "devel")
        self.add_pattern("/usr/lib/lib*.so", "devel")
        self.add_pattern("/usr/lib/lib*.a", "devel")
        self.add_pattern("/usr/lib/pkgconfig/*.pc", "devel")
        self.add_pattern("/usr/lib64/pkgconfig/*.pc", "devel")
        self.add_pattern("/usr/include/", "devel")
        self.add_pattern("/usr/share/man3/", "devel")

        self.add_pattern("/usr/lib32/lib*.so", "32bit-devel")
        self.add_pattern("/usr/lib32/lib*.a", "32bit-devel")
        self.add_pattern("/usr/lib32/pkgconfig/*.pc", "32bit-devel")
        self.add_pattern("/usr/lib32/lib*.so.*", "32bit")

    def add_file(self, path):
        """ Add a file path to the owned list and place it into the correct
            package (main or named subpackage) according to the highest found
            priority pattern rule, otherwise it shall fallback under default
            policy into the main package itself.

            This enables a fallback approach, whereby subpackages "steal" from
            the main listing, and everything that is left is packaged into the
            main package (YpkgSpec::name), making "abandoned" files utterly
            impossible. """

        target = "main"  # default pattern name
        pattern = self.get_pattern(path)
        if pattern:
            target = self.patterns[pattern]

        if target not in self.packages:
            self.packages[target] = Package(target)
        self.packages[target].add_file(pattern, path)

    def remove_file(self, path):
        """ Remove a file from our set, in any of our main or sub packages
            that may currently own it. """

        for pkg in self.packages:
            self.packages[pkg].remove_file(path)

    def get_pattern(self, path):
        """ Return a matching pattern for the given path.
            This is ordered according to priority to enable
            multiple layers of priorities """
        matches = [p for p in self.patterns if p.match(path)]
        if len(matches) == 0:
            return None

        matches = sorted(matches, key=StringPathGlob.get_priority,
                         reverse=True)
        return matches[0]

    def add_pattern(self, pattern, pkgName, priority=PRIORITY_DEFAULT):
        """ Add a pattern to the internal map according to the
            given priority. """

        obj = None
        is_prefix = False
        if pattern.endswith(os.sep):
            if not StringPathGlob.is_a_pattern(pattern):
                is_prefix = True

        obj = StringPathGlob(pattern, prefixMatch=is_prefix, priority=priority)
        self.patterns[obj] = pkgName

    def emit_packages(self):
        """ Ensure we've finalized our state, allowing proper theft and
            exclusion to take place, and then return all package objects
            that we've managed to generate. There is no gaurantee that
            a "main" package will be generated, as patterns may omit
            the production of one. """

        for package in self.packages:
            for comparison in self.packages:
                if comparison == package:
                    continue
                for file in self.packages[comparison].emit_files():
                    self.packages[package].exclude_file(file)

        return []
