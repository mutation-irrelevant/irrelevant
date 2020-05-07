import os
from datetime import datetime
import shutil
from d4jconstants import *
from collections import defaultdict
from contextlib import contextmanager, AbstractContextManager
from subprocess import CalledProcessError, run, DEVNULL, TimeoutExpired
import tempfile
import json
import shutil
import tarfile
import javalang
import patch


class ListNotFoundException(Exception):
    pass


class TestSuite:
    FAILED_MARK = "failed"


    def get_faillist_path(self):
        return self.get_filepath("fails")


    def is_trigger_tests_available(self):
        return os.path.exists(self.get_faillist_path())


    @property
    def changes(self):
        if self._changes is None:
            self._changes = patch.load_changes(self.proj_name, self.bug_id)

        return self._changes


    @staticmethod
    def parse_failing_tests(p):
        triggers = set()
        with open(p, "r") as fh:
            for l in fh:
                if l.startswith("---"):
                    triggers.add(l.strip()[4:])

        return triggers
        

    @property
    def trigger_tests(self):
        if self._triggers is None:
            self._triggers = TestSuite.parse_failing_tests(self.get_faillist_path())

        return None if not self._triggers else self._triggers


    def available(self):
        return self.is_trigger_tests_available() and self.is_suite_available() and self.changes is not None and len(self.changes) > 0


    def register_suite(self, p):
        if self.suite_path is None or os.path.exists(self.suite_path):
            raise Exception()

        shutil.move(p, self.suite_path)


    def mark_trigger_tests_unavailable(self):
        with open(self.get_faillist_path(), "w") as fh:
            fh.write(TestSuite.FAILED_MARK)


    def __init__(self, proj_name, bug_id, suite_name, suite_type):
        self.proj_name = proj_name
        self.bug_id = bug_id
        self.suite_type = suite_type
        self.suite_name = suite_name
        self.suite_root = suite_root = os.path.join("suites", proj_name, bug_id)
        self.suite_path = None
        self._triggers = None
        self._changes = None

        os.makedirs(suite_root, exist_ok=True)


    def get_filepath(self, ext):
        return os.path.join(self.suite_root, self.suite_name + "." + ext)


    def __str__(self):
        return self.suite_name


    def _prepare_testcases(self):
        raise Exception()


    def _iterate_classes(self, db):
        raise Exception()


    def is_suite_available(self):
        raise Exception()


    def register_trigger_tests(self, list_path):
        p = self.get_faillist_path()
        if list_path is None:
            with open(p, "w") as fh:
                fh.write()
        else:
            shutil.copy(list_path, self.get_faillist_path())


    def _is_relevant_testcases(self, cls_name, method_name):
        raise Exception()


    def get_testnames(self):
        result = set()
        with d4j_checkout(self.proj_name, self.bug_id) as git_home:
            d4j_test(git_home, self.suite_path)
            p = os.path.join(git_home, "all_tests")
            if os.path.exists(p):
                with open(p, "r") as fh:
                    for line in fh:
                        try:
                            method_name, cls_name = line.split("(")
                        except ValueError:
                            #Unknown test.
                            cls_name, method_name = line.split(":")
                            result.add(cls_name + "::" + method_name)
                            continue

                        try:
                            #parameterized testcases.
                            method_name = method_name[:method_name.index("[")]
                        except ValueError:
                            pass

                        cls_name = cls_name[:cls_name.index(")")]
                        if self._is_relevant_testcases(cls_name, method_name):
                            result.add(cls_name + "::" + method_name)

        return result


class DevTestSuite(TestSuite):
    def __init__(self, proj_name, bug_id):
        suite_name = "{}-{}-dev".format(proj_name, bug_id)
        super().__init__(proj_name, bug_id, suite_name, "dev")
        self._testnames = None


    def _is_relevant_testcases(self, cls_name, method_name):
        if self._testnames is None:
            self._testnames = set(d4j_iterate_relevant_tests(self.proj_name, self.bug_id))

        return cls_name in self._testnames


    def is_suite_available(self):
        return True


class GenTestSuite(TestSuite):
    @staticmethod
    def get_tarbz_filename(proj_name, bug_id, suite_type):
        return "{}-{}-{}.1.tar.bz2".format(proj_name, bug_id, suite_type)


    def __init__(self, proj_name, bug_id, suite_type):
        tarbz_name = GenTestSuite.get_tarbz_filename(proj_name, bug_id, suite_type)
        super().__init__(proj_name, bug_id, tarbz_name, suite_type)

        self._removed = None
        self.suite_path = os.path.join(self.suite_root, tarbz_name)



    def _is_relevant_testcases(self, cls_name, method_name):
        if self._removed is None:
            self._removed = defaultdict(set)
            with tempfile.TemporaryDirectory() as tmp_dir:
                tar = tarfile.open(self.suite_path)
                tar.extractall(tmp_dir)
                tar.close()

                for root, dirs, files in os.walk(tmp_dir):
                    for name in files:
                        if not name.endswith(".java"):
                            continue

                        with open(os.path.join(root, name)) as fh:
                            buf = fh.read()

                        tree = javalang.parse.parse(buf)
                        package_name = tree.package.name + "." if tree.package else ""
                        for path, node in tree.filter(javalang.tree.MethodDeclaration):
                            class_name = package_name + path[2].name
                            if len(node.body) == 0:
                                self._removed[class_name].add(node.name)

        return method_name not in self._removed[cls_name]


    def is_suite_available(self):
        return os.path.exists(self.suite_path)


class EvoSuite(GenTestSuite):
    CRITERIA = {"branch", "strongmutation", "weakmutation"}
    def __init__(self, proj_name, bug_id, criterion):
        if criterion not in EvoSuite.CRITERIA:
            raise Exception(criterion)

        suite_type = "evosuite-{}".format(criterion)
        super().__init__(proj_name, bug_id, suite_type)


class RanSuite(GenTestSuite):
    def __init__(self, proj_name, bug_id):
        super().__init__(proj_name, bug_id, "randoop")


def iterate_suites(proj_name):
    min_idx, max_idx = -1, 9999
    if ":" in proj_name:
        proj_name, min_idx, max_idx = proj_name.split(":")
        min_idx = int(min_idx)
        max_idx = int(max_idx)

    for bug_id in d4j_iterate_fixes(proj_name):
        if not (min_idx <= int(bug_id[:-1]) <= max_idx):
            continue

        yield (DevTestSuite(proj_name, bug_id), RanSuite(proj_name, bug_id), *map(lambda c: EvoSuite(proj_name, bug_id, c), EvoSuite.CRITERIA),)
