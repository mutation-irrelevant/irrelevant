import os
import subprocess
import itertools
import json
import random
import tempfile
import csv
import sys
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from scipy import stats
import numpy as np
import shutil
from patch import load_changes
from testsuite import iterate_suites
from killmap import Killmap
from collections import defaultdict, namedtuple

np.seterr(all='raise')


def read_lines(p):
    with open(p, "r") as fh:
        for line in fh:
            yield line


def _load_mutants(suite):
    l2m = defaultdict(set)
    l2l = defaultdict(lambda: defaultdict(set))
    cnt = 0

    try:
        for line in Killmap.iterate_mutants(suite):
            cnt += 1
            arguments = line.split(":")
            mid = int(arguments[0]) - 1
            method_name = arguments[4]
            line_no = int(arguments[5])

            line_key = method_name.split("@")[0]

            l2m[method_name].add(mid)
            l2l[line_key][line_no].add(mid)


        return l2m, l2l, cnt
    except:
        return None, None, None


empties = {
    "Math-34f-dev": {"org.apache.commons.math3.genetics.ListPopulation@iterator()"},
    "Math-58f-dev": {"org.apache.commons.math.optimization.fitting.GaussianFitter@fit()"},
    "Math-70f-dev": {"org.apache.commons.math.analysis.solvers.BisectionSolver@solve(org.apache.commons.math.analysis.UnivariateRealFunction,double,double,double)"},
    "Math-75f-dev": {"org.apache.commons.math.stat.Frequency@getPct(java.lang.Object)"},
    "Math-104f-dev": {"org.apache.commons.math.special.Gamma@regularizedGammaP(double,double)", "org.apache.commons.math.special.Gamma@regularizedGammaQ(double,double)"},
    "Lang-25f-dev": {"org.apache.commons.lang3.text.translate.EntityArrays@ISO8859_1_ESCAPE()", "org.apache.commons.lang3.text.translate.EntityArrays@ISO8859_1_UNESCAPE()"},
    "Lang-29f-dev": {"org.apache.commons.lang3.SystemUtils@toJavaVersionFloat(java.lang.String)"},
    "Lang-34f-dev": {"org.apache.commons.lang3.builder.ToStringStyle@getRegistry()"},
    "Lang-57f-dev": {"org.apache.commons.lang.LocaleUtils@isAvailableLocale(java.util.Locale)"},
    "Lang-64f-dev": {"org.apache.commons.lang.enums.ValuedEnum@getValueInOtherClassLoader(java.lang.Object)"},
    "Chart-8f-dev": {"org.jfree.data.time.Week@<init>(java.util.Date,java.util.TimeZone)"},
    "Closure-8f-dev": {"com.google.javascript.jscomp.CollapseVariableDeclarations@isNamedParameter(com.google.javascript.jscomp.Scope.Var)"},
    "Closure-16f-dev": {"com.google.javascript.jscomp.ScopedAliases$AliasedTypeNode@<init>(com.google.javascript.jscomp.ScopedAliases,com.google.javascript.rhino.Node,com.google.javascript.rhino.Node,java.lang.String)"},
    "Closure-26f-dev": {"com.google.javascript.jscomp.ProcessCommonJSModules$ProcessCommonJsModulesCallback@<init>(com.google.javascript.jscomp.ProcessCommonJSModules)"},
    "Closure-27f-dev": {"com.google.javascript.rhino.IR@blockUnchecked(com.google.javascript.rhino.Node)"},
    "Closure-146f-dev": {"com.google.javascript.rhino.jstype.JSType@getTypesUnderInequality(com.google.javascript.rhino.jstype.JSType)"}
}

IGNORED = {
    "Math": set([12, 77, 34, 58, 70, 75]),
    "Time": set([11]),
    "Lang": set([23, 29, 32, 57]),
    "Closure": set([28, 46, 112, 135, 137, 148, 158, 162, 163, 175]),
    "Chart": set([8])
}

method_out = set()
statement_out = set()
def compute_correlation(suites):
    global empties, method_out, statement_out
    suite = suites[0]
    print(suite)
    line_changes, method_changes = load_changes(suite.proj_name, suite.bug_id)
    if line_changes is None or method_changes is None:
        method_out.add(str(suite))
        print("Changes are not perfect.")
        return
    
    mutants_by_methods, mutants_by_line, mutants_size = _load_mutants(suite)
    killmap = []
    trigger_tests = []
    method_level_mutants = []
    line_level_mutants = []

    for method_name in method_changes:
        selected = mutants_by_methods.get(method_name)
        if selected is None:
            if str(suite) not in empties or method_name not in empties[str(suite)]:
                print("Should confirm that", method_name, "has no mutants")
                return
        else:
            method_level_mutants.extend(selected)
            
    for key, lines in line_changes.items():
        l = mutants_by_line.get(key)
        if l is None:
            continue
            
        for line_no in lines:
            result = l.get(line_no)
            if result is not None:
                line_level_mutants.extend(result)

    if len(method_level_mutants) == 0:
        method_out.add(str(suite))
        print("No method-level mutant exists")
        return None  
    
    if len(line_level_mutants) == 0:
        statement_out.add(str(suite))
        print("No line-level mutant exists")
        return None

    fails = set()
    for suite in suites:
        if suite.trigger_tests is not None:
            fails |= suite.trigger_tests
        
    if len(fails) == 0:
        print("No triggering tests found----------------------.")
        return None

    for suite in suites:
        km = Killmap(suite)
        tests = km.snapshot()
        if len(tests[Killmap.UNKNOWN]) > 0:
            print("every test is not confirmed")
            return

        for row in km.iterate_killmap():
            method_name = row[0]
            if len(row) -1 != mutants_size:
                raise Exception("rowsize in killmap != # of mutants")

            try:
                fails.remove(method_name)
                trigger_tests.append(len(killmap))
            except KeyError:
                pass

            subrow = [row[i] in {"EXC", "FAIL"} for i in range(1, len(row))]
            killmap.append(subrow)

    killmap = np.array(killmap, dtype=bool)
    test_size = killmap.shape[0]
    if test_size < 532:
        print("TestSize is too small: " + str(test_size))
        return

    method_level_mutants = np.array(method_level_mutants, dtype=int)
    line_level_mutants = np.array(line_level_mutants, dtype=int)
    all_mask = np.array(range(mutants_size - 1))

    def _add_to(mask):
        def _add(covers):
            covers = covers[mask]
            try:
                return np.sum(covers) / len(covers)
            except Exception:
                print("Ignore covers that have only ", np.unique(covers))
                return None

        return _add

    def _generator(ratio):
        class_level = _add_to(all_mask)
        method_level = _add_to(method_level_mutants)
        line_level = _add_to(line_level_mutants)

        is_type = isinstance(ratio, str)
        if ratio is None or is_type:
            if ratio == "max20":
                max_size = int(test_size * 0.2)
            elif ratio == "max50":
                max_size = int(test_size * 0.5)
            else:
                max_size = test_size
                    
            for _ in range(10000):
                size = random.randint(1, max_size)
                row = [suite.proj_name, suite.bug_id, size / test_size]
                testset = np.random.choice(test_size, size=size)
                is_bug = len(np.intersect1d(testset, trigger_tests)) > 0
                covered = np.any(killmap[testset,:], axis=0)

                row.append(class_level(covered))
                row.append(method_level(covered))
                row.append(line_level(covered))
                row.append(is_bug)
                yield row
        else:
            size = int(ratio * test_size)                
            for _ in range(10000):
                row = [suite.proj_name, suite.bug_id, size]
                testset = np.random.choice(test_size, size=size)
                is_bug = len(np.intersect1d(testset, trigger_tests)) > 0
                covered = np.any(killmap[testset,:], axis=0)

                row.append(class_level(covered))
                row.append(method_level(covered))
                row.append(line_level(covered))
                row.append(is_bug)
                yield row

    return _generator


def _main():
    global IGNORED, method_out, statement_out
    size_out = 0
    timeout = 0
    total = 0
    selected = defaultdict(int)
    for suites in (suites for proj_name in ["Math", "Closure", "Lang", "Time", "Chart"] for suites in iterate_suites(proj_name)):
        total += 1
        suites = list(filter(lambda x: x.available(), suites))
        if len(suites) == 0:
            timeout += 1
            continue

        dev = suites[0]
        proj_name = dev.proj_name
        bug_id = dev.bug_id
        
        if int(bug_id[:-1]) in IGNORED[proj_name]:
            method_out.add(proj_name + bug_id)
            continue

        out_root = os.path.join("cov", proj_name, bug_id)
        os.makedirs(out_root, exist_ok=True)

        total_size = 0
        failed = 0
        for suite in suites:
            km = Killmap(suite)
            snapshot = km.snapshot()
            if len(snapshot.get("unknown", [])) > 0:
                print(dev, ": incomplete")
                total_size = -1
                failed = -1
                timeout += 1
                break
            elif len(snapshot.get("timeout", [])) > 0:
                print(dev, ": timeout")
                total_size = -1
                failed = -1
                timeout += 1
                break

            size = len(snapshot.get("covered", []))
            if size > 0:
                total_size += size
                if suite.trigger_tests is not None:
                    failed += len(suite.trigger_tests)
        
        if failed == -1 and total_size == -1:
            continue

        if failed == 0 or total_size < 532:
            print(dev, ": testSize is too small or no failed test cases found - " + str(total_size))
            size_out += 1
            continue

        generator = compute_correlation(suites)
        if generator is None:
            continue
        
        for t in ["max20", "max50"]:
            out_file = os.path.join(out_root, "{}.csv".format(t))
            if not os.path.exists(out_file):
                try:
                    with open(out_file, "w") as fh:
                        writer = csv.writer(fh)
                        for row in generator(t):
                            writer.writerow(row)
                except Exception as e:
                    os.unlink(out_file)
                    raise e

        for ratio in range(25, 525, 25):
            out_file = os.path.join(out_root, "{}.csv".format(ratio))
            ratio /= 1000
            if not os.path.exists(out_file):
                try:
                    with open(out_file, "w") as fh:
                        writer = csv.writer(fh)
                        for row in generator(ratio):
                            writer.writerow(row)
                except Exception as e:
                    os.unlink(out_file)
                    raise e
                    
        selected[proj_name] += 1
        
    print(selected)
    print(size_out)
    print(len(method_out))
    print(len(statement_out))
    print(timeout)
    print(total)


if __name__ == "__main__":
    _main()
