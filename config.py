from subprocess import check_output, STDOUT
import os

_ANT_HOME = "/home/mingwan/apache-ant-1.10.7"
D4J_HOME = "defects4j"
D4J_BIN = os.path.join(D4J_HOME, "framework", "bin", "defects4j")

import subprocess

def d4j_check_output(*argv, timeout = None, **kargs):
    env = kargs.get("env")
    kargs["stderr"] = subprocess.STDOUT
    kargs["stdout"] = subprocess.PIPE
    if env is None:
        env = os.environ.copy()
        kargs["env"] = env

    env["PATH"] = ":".join([os.path.join(_ANT_HOME, "bin"), *env["PATH"].split(":")])
    env["ANT_HOME"] = _ANT_HOME
    env["TZ"] = "America/Los_Angeles"
    proc = subprocess.Popen(*argv, **kargs)
    try:
        outs, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        outs, _ = proc.communicate(timeout=10)
        return None

    return outs.decode("utf-8"), proc.returncode == 0,


def _verify_ant():
    global _ANT_HOME
    if not os.path.exists(_ANT_HOME):
        return

    ant_home_verified = None
    ant_lib_verified = None
    out, _ = d4j_check_output(["ant", "-diagnostics"])
    for line in out.splitlines():
        if ant_home_verified and ant_lib_verified:
            break

        if line.startswith("ant.home: "):
            ant_home_verified = line.split(" ")[-1]
        elif line.startswith("ant.library.dir"):
            ant_lib_verified = os.path.split(line.split(" ")[-1])[0]

    if not (ant_home_verified == _ANT_HOME and ant_lib_verified == _ANT_HOME):
        raise Exception("ant_home: {}\nant_lib: {}".format(ant_home_verified, ant_lib_verified))


_verify_ant()
print(d4j_check_output(["java", "-version"]))