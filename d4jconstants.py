import os
import subprocess
import tempfile
import unidiff
import shutil
import psutil
import sys
from datetime import datetime
from contextlib import contextmanager

_D4J_HOME = "defects4j"
_PROJECTS_DIR_PATH = os.path.join(_D4J_HOME, "framework", "projects")
_EVOSUITE_BIN = os.path.join(_D4J_HOME, "framework", "bin", "run_evosuite.pl")
_RANDOOP_BIN = os.path.join(_D4J_HOME, "framework", "bin", "run_randoop.pl")
_D4J_BIN = os.path.join(_D4J_HOME, "framework", "bin", "defects4j")
_D4J_FIX_SUITE_BIN = os.path.join(_D4J_HOME, "framework", "util", "fix_test_suite.pl")
_NAMES = ("Math", "Lang", "Mockito", "Time", "Chart", "Closure",)


def _shell(*cmd, stdout=None, timeout = None, cwd=os.getcwd(), envs=os.environ):
    print(cmd)
    try:
        if stdout is None:
            with tempfile.TemporaryFile("w+") as fh:
                try:
                    subprocess.run(cmd, check=True, timeout=timeout, cwd=cwd, stdout=fh, stderr=fh, env=envs)
                except Exception as e:
                    fh.seek(0)
                    print(fh.read())
                    raise e
        else:
            subprocess.run(cmd, check=True, timeout=timeout, cwd=cwd, stdout=stdout, stderr=stdout, env=envs)
    finally:
        for ps in psutil.process_iter(["create_time", "cmdline"]):
            if "java" not in ps.info["cmdline"]:
                continue

            diff = datetime.now() - datetime.fromtimestamp(ps.info["create_time"])
            if diff.seconds > 60 * 10:
                try:
                    ps.kill()
                except:
                    pass



def d4j_iterate_relevant_tests(proj_name, bug_id):
    p = os.path.join(_PROJECTS_DIR_PATH, proj_name, "relevant_tests", bug_id[:-1])
    with open(p, "r") as fh:
        for line in fh:
            yield line.strip()


def d4j_compile(git_home):
    _shell(_D4J_BIN, "compile", "-w", git_home)


def d4j_checkout_into(proj_name, bug_id, tmp_dir):
    cnt = 0
    try:
        while True:
            cnt += 1
            if cnt > 10:
                raise Exception(proj_name + bug_id)

            try:
                _shell(_D4J_BIN, "checkout", "-w", tmp_dir, "-p", proj_name, "-v", bug_id)
                return
            except subprocess.CalledProcessError:
                continue
    except OSError as e:
        if e.errno == 39:
            print("Could not remove the check-outed directory")
            #workaround?


def d4j_opposed_checkout_into(proj_name, bug_id, tmp_dir):
    prefix = "f" if bug_id[-1] == "b" else "b"
    version = bug_id[:-1] + prefix
    return d4j_checkout_into(proj_name, version, tmp_dir)


def d4j_opposed_checkout(proj_name, bug_id):
    prefix = "f" if bug_id[-1] == "b" else "b"
    version = bug_id[:-1] + prefix
    return d4j_checkout(proj_name, version)


@contextmanager
def d4j_checkout(proj_name, bug_id):
    cnt = 0
    try:
        while True:
            cnt += 1
            if cnt > 10:
                raise Exception(proj_name + bug_id)

            with tempfile.TemporaryDirectory() as git_home:
                try:
                    _shell(_D4J_BIN, "checkout", "-w", git_home, "-p", proj_name, "-v", bug_id)
                except subprocess.CalledProcessError:
                    continue

                yield git_home
                break
    except OSError as e:
        if e.errno == 39:
            print("Could not remove the check-outed directory")
            #workaround?
        else:
            raise e


def d4j_test(git_home, suite_path = None):
    if suite_path is None:
        _shell(_D4J_BIN, "test", "-w", git_home, "-r")
    else:
        _shell(_D4J_BIN, "test", "-w", git_home, "-s", suite_path)


def d4j_patchset(proj_name, bug_id):
    p = os.path.join(_PROJECTS_DIR_PATH, proj_name, "patches", bug_id[:-1] + ".src.patch")
    with open(p, "r", errors="replace") as fh:
        return unidiff.PatchSet(fh)


def d4j_fix_suites(proj_name, bug_id, suite_type, suite_dir, tmp_dir = None):
    if tmp_dir is not None:
        _shell(_D4J_FIX_SUITE_BIN, "-p", proj_name, "-d", suite_dir, "-v", bug_id, "-D", "-t", tmp_dir ,"-s", suite_type, timeout=6 * 60)
    else:
        _shell(_D4J_FIX_SUITE_BIN, "-p", proj_name, "-d", suite_dir, "-v", bug_id, "-s", suite_type, timeout=6 * 60)


def d4j_run_evosuite(proj_name, bug_id, output_dir, criterion, timeout, log_fh):
    _shell(_EVOSUITE_BIN, "-p", proj_name, "-v", bug_id, "-n", "1", "-o", output_dir, "-b", "300", "-c", criterion, stdout=log_fh)


def d4j_run_randoop(proj_name, bug_id, output_dir, timeout, log_fh):
    _shell(_RANDOOP_BIN, "-p", proj_name, "-v", bug_id, "-n", "1", "-o", output_dir, "-b", "300", timeout=timeout, stdout=log_fh, envs=dict(os.environ, RANDOOP_CONFIG_FILE="randoop.config"))


def d4j_iterate_fixes(proj_name, is_fixed = True):
    relevant_tests_dir = os.path.join(_PROJECTS_DIR_PATH, proj_name, "relevant_tests")
    ids = set(os.listdir(relevant_tests_dir))
    max_id = max(*map(int, ids))
    suffix = "f" if is_fixed else "b"
    return (str(i) + suffix for i in range(1, max_id + 1))


def d4j_run_mutation(git_home, test_name, log_fh, timeout, suite_path = None):
    test_name = test_name.replace("$", "\\$")
    cmds = [_D4J_BIN, "mutation", "-w", git_home, "-t", test_name]
    if suite_path is not None:
        cmds.append("-s")
        cmds.append(suite_path)
    _shell(*cmds, timeout=timeout, stdout=log_fh)


def d4j_run_tests(git_home, suite_path):
    if suite_path is None:
        _shell(_D4J_BIN, "test", "-w", git_home, "-r")
    else:
        _shell(_D4J_BIN, "test", "-w", git_home, "-s", suite_path)

    failing_path = os.path.join(git_home, "failing_tests")
    all_path = os.path.join(git_home, "all_tests")
    return all_path, failing_path


def d4j_get_trigger_tests_path(proj_name, bug_id):
    p = os.path.join(_PROJECTS_DIR_PATH, proj_name, "trigger_tests", bug_id[:-1])
    return p if os.path.exists(p) else None


def d4j_iterate_failing_tests(p):
    with open(p, "r") as fh:
        for line in fh:
            if not line.startswith("---"):
                continue

            yield line[4:].strip()


def _diff_bytes(cmds, p, a):
    with open(p, "rb") as fh:
        buf = fh.read()

    if buf != a:
        raise Exception("{}: {} != {}", " ".join(cmds), buf, a)


def _check_env(env_path, *cmds):
    envs = os.environ
    p = subprocess.run(cmds, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=envs)
    stdout_path = env_path + ".stdout"
    stderr_path = env_path + ".stderr"
    if os.path.exists(env_path):
        _diff_bytes(cmds, stdout_path, p.stdout)
        _diff_bytes(cmds, stderr_path, p.stderr)
    else:
        with open(stdout_path, "wb") as fh:
            fh.write(p.stdout)
        
        with open(stderr_path, "wb") as fh:
            fh.write(p.stderr)