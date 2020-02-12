import os
import subprocess
import itertools
import tempfile
import csv
import shutil
import itertools
from datetime import datetime
from collections import defaultdict
from d4jconstants import *
from patch import load_changes
from contextlib import AbstractContextManager
import multiprocessing
import time
import json
import tarfile
import testsuite as ts


class MutantsUnknownException(Exception):
    pass


class Killmap(AbstractContextManager):
    COVERED = "covered"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNKNOWN = "unknown"
    ROOT_DIR = "mutations"


    def __str__(self):
        return "Killmap({})".format(self.suite)


    def available(self):
        has_unknown = False
        for v in self._methods.values():
            if v == Killmap.TIMEOUT:
                return False

            has_unknown |= v == Killmap.UNKNOWN

        return None if has_unknown else True


    @staticmethod
    def _load_mutants(suite):
        p = Killmap._get_mutants_path(suite)
        if os.path.exists(p):
            with open(p, "r") as fh:
                return [l.strip() for l in fh]
        
        return None


    @staticmethod
    def _iterate_killmap(suite):
        p = Killmap._get_killmap_path(suite)
        if os.path.exists(p):
            with open(p, "r") as fh:
                for row in csv.reader(fh):
                    yield row


    @staticmethod
    def _iterate_methods(suite):
        p = Killmap._get_list_path(suite)
        if not os.path.exists(p):
            raise Exception(p)

        try:
            with open(p, "r") as fh:
                obj = json.load(fh)
        except json.JSONDecodeError:
            os.unlink(p)
            obj = {}

        for t, methods in obj.items():
            for m in methods:
                yield m, t

    
    def remove(self, m):
        if m in self._methods:
            try:
                del self._methods[m]
                self._dirty = True
                del self._killmap[m]
                return True
            except:
                pass

        return False
            


    def _update(self, m, t):
        if self._methods.get(m) != t:
            self._methods[m] = t
            self._dirty = True


    @staticmethod
    def iterate_mutants(suite):
        p = Killmap._get_mutants_path(suite)
        if os.path.exists(p):
            with open(p, "r") as fh:
                for l in fh:
                    yield l.strip()
        else:
            raise MutantsUnknownException()


    @staticmethod
    def _get_mutants_path(suite):
        return os.path.join(suite.suite_root, "mutants")


    @staticmethod
    def _get_list_path(suite):
        return suite.get_filepath("json")


    @staticmethod
    def _get_killmap_path(suite):
        return suite.get_filepath("killmap.csv")


    @staticmethod
    def parse_all_tests(p):
        names = set()
        with open(p, "r") as fh:
            for line in fh:
                try:
                    method_name, cls_name = line.split("(")
                except ValueError:
                    #Unknown test.
                    cls_name, method_name = line.split(":")
                    names.add(cls_name + "::" + method_name)
                    continue

                try:
                    #parameterized testcases.
                    method_name = method_name[:method_name.index("[")]
                except ValueError:
                    pass

                cls_name = cls_name[:cls_name.index(")")]
                names.add(cls_name + "::" + method_name)

        return names


    @staticmethod
    def initialize(suite, all_tests):
        names = Killmap.parse_all_tests(all_tests)
        p = Killmap._get_list_path(suite)
        
        if os.path.exists(p):
            force_write = False
            print("Update killmap")
            km = Killmap(suite)
            removes = set(name for name in km._methods if name not in names)
            for name in removes:
                print("Remove", name)
                try:
                    del km._methods[name]
                    force_write = True
                    del km._killmap[name]
                except:
                    pass

            for name in (name for name in names if km.get_status(name) is None):
                print("Add", name)
                km.add(name)

            km.write(force_write=force_write)
        else:
            print("Initialize killmap for", suite)
            with open(p, "w") as fh:
                json.dump({Killmap.UNKNOWN: list(names)}, fh)


    def __init__(self, suite):
        self._dirty = False
        self._updated_killmap = set()
        self.suite = suite

        mutants = self.mutants = Killmap._load_mutants(suite)
        methods = self._methods = {m: t for m, t in Killmap._iterate_methods(suite)}
        killmap = self._killmap = {}

        need_rewrite_killmap = False
        for row in Killmap._iterate_killmap(suite):
            if mutants is not None and len(row) - 1 != len(mutants):
                need_rewrite_killmap = True
                continue

            name = row[0]
            t = methods.get(name)
            if t is None:
                need_rewrite_killmap = True
                continue

            killmap[name] = row
            if t == Killmap.UNKNOWN:
                self._update(name, Killmap.COVERED)

        unknowns = set()
        for m, t in methods.items():
            if m not in killmap and t == Killmap.COVERED:
                unknowns.add(m)

        if len(unknowns) > 0:
            print("Found inconsistency between killmap and json in", suite)
            for m in unknowns:
                self._update(m, Killmap.UNKNOWN)

        self.write(force_write=need_rewrite_killmap)


    def __enter__(self):
        return self


    def count(self):
        return len(self._methods)


    @property
    def testnames(self):
        return set(self._methods.keys())

    
    def snapshot(self):
        result = defaultdict(list)
        for name, status in self._methods.items():
            result[status].append(name)

        return result


    def items(self):
        return self._methods.items()


    def iterate_killmap(self):
        for v in self._killmap.values():
            yield v


    def add(self, name):
        if name not in self._methods:
            self._update(name, Killmap.UNKNOWN)
            return True

        return False


    def add_timeout(self, name):
        self._update(name, Killmap.TIMEOUT)


    def add_error(self, name):
        self._update(name, Killmap.ERROR)


    def get_status(self, name):
        return self._methods.get(name)


    def append_d4j_killmap(self, name, killmap_path, mutants_path):
        if not os.path.exists(mutants_path) or not os.path.exists(killmap_path):
            return

        p = Killmap._get_mutants_path(self.suite)
        if self.mutants is None:
            shutil.copy(mutants_path, p)
            self.mutants = Killmap._load_mutants(self.suite)
        else:
            with open(mutants_path, "r") as fh:
                for idx, line in enumerate(fh):
                    if self.mutants[idx] != line.strip():
                        shutil.copy(mutants_path, p + ".different")
                        raise Exception("Inconsistent mutants")

        row = [name]
        with open(killmap_path, "r") as fh:
            fh.readline()
            for line in fh:
                idx, result = line.strip().split(",")
                idx = int(idx)
                empties = idx - len(row)
                row.extend([None] * empties)
                row.append(result)

        empties = len(self.mutants) - len(row) + 1
        row.extend([None] * empties)

        if len(row) - 1 != len(self.mutants):
            raise Exception()

        self._update(name, Killmap.COVERED)
        self._killmap[name] = row
        self._updated_killmap.add(name)


    def write(self, force_write = False):
        if not (force_write or self._dirty):
            return

        if len(self._updated_killmap) > 0:
            km = self._killmap
            with open(Killmap._get_killmap_path(self.suite), "a") as fh:
                writer = csv.writer(fh)
                for name in self._updated_killmap:
                    writer.writerow(km[name])

        with open(Killmap._get_list_path(self.suite), "w") as fh:
            json.dump(self.snapshot(), fh, indent=2)

        self._updated_killmap = set()


    def __exit__(self, exc_type, exc_value, traceback):
        # isinstance seems not working as expected within the forked thread.
        if (exc_type is None or exc_type.__name__ == "KeyboardInterrupt"):
            self.write()

        return False


def _analyze(git_home, killmap, candidates, timeout):
    mutants_log_path = os.path.join(git_home, "mutants.log")
    kill_csv = os.path.join(git_home, "kill.csv")

    with killmap:
        for m in candidates:
            if killmap.get_status(m) == Killmap.COVERED:
                continue
        
            print(multiprocessing.current_process(), ":", datetime.now(),":", m)
            with tempfile.TemporaryFile() as fh:
                try:
                    d4j_run_mutation(git_home, m, fh, suite_path=killmap.suite.suite_path, timeout=timeout)
                    killmap.append_d4j_killmap(m, kill_csv, mutants_log_path)
                except subprocess.TimeoutExpired:
                    print(datetime.now(), "Mutation timeout from {} in {} with timeout {:.2f}".format(m, killmap.suite, timeout))
                    killmap.add_timeout(m)
                    break
                except subprocess.CalledProcessError:
                    print(m)
                    # This method causes exception in defects4j.mutation.
                    fh.seek(0)
                    for line in fh:
                        print(line)

                    killmap.add_error(m)
                    continue


def _generate_map(args):
    timeout, suites, killmaps = args
    devsuite = suites[0]
    proj_name = devsuite.proj_name
    bug_id = devsuite.bug_id

    with d4j_checkout(proj_name, bug_id) as git_home:
        for idx, km in enumerate(killmaps):
            snapshot = km.snapshot()
            print(multiprocessing.current_process(), ":", datetime.now(),":", km)
            if idx == 0:
                _analyze(git_home, km, snapshot[Killmap.ERROR], timeout)

            _analyze(git_home, km, snapshot[Killmap.UNKNOWN], timeout)
            

def _hastask(suites):
    killmaps = []
    cnt = 0
    failed = False
    for idx, suite in enumerate(suites):
        if not suite.available():
            continue

        km = Killmap(suite)

        snapshot = km.snapshot()
        if len(snapshot[Killmap.TIMEOUT]) > 0:
            failed = True
            break

        if idx == 0:
            cnt += len(snapshot[Killmap.UNKNOWN]) + len(snapshot[Killmap.ERROR])
        else:
            cnt += len(snapshot[Killmap.UNKNOWN])
        killmaps.append(km)

    if cnt == 0:
        return None
    elif not failed:
        devsuite = suites[0]
        a, b = load_changes(devsuite.proj_name, devsuite.bug_id)
        if a is not None and b is not None:
            print(devsuite)
            return suites, killmaps,
        else:
            return None


def _main():
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=18000)
    args = parser.parse_args(sys.argv[1:])
    tasks = itertools.chain.from_iterable(ts.iterate_suites(name) for name in ["Math", "Closure", "Chart", "Lang", "Time"])
    tasks = filter(None, map(_hastask, tasks))

    with multiprocessing.Pool(args.thread) as p:
        p.map(_generate_map, ((args.timeout, *task) for task in tasks))


if __name__ == "__main__":
    _main()
