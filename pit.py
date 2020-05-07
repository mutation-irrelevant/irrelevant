from d4jconstants import d4j_checkout
import os
from subprocess import check_output, CalledProcessError, PIPE, STDOUT
import tarfile
import shutil
import tempfile
from config import d4j_check_output
import d4j
import time

# def get_classpath():
#     cwd = os.getcwd()
#     ant_bin = os.path.join(cwd, "defects4j/major/bin/ant")
#     build_xml = os.path.join(cwd, "build.xml")
#     try:
#         ant = subprocess.run([ant_bin, "-f", build_xml, "-Dbasedir={}".format(git_home), "classpath"], check=True,
#                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=git_home)
#     except subprocess.CalledProcessError as e:
#         print(e.stderr)
#         raise e


def _read_all_lines(p, need_strip):
    with open(p, "r") as fh:
        if need_strip:
            return [line.strip() for line in fh]
        else:
            return [line for line in fh]


def _read_all_lines_and_remove(p, need_strip):
    lines = _read_all_lines(p, need_strip)
    os.unlink(p)
    return lines


def _parse_tarbz_level(name):
    elems = name.split("-")
    size = len(elems)
    if size == 3:
        return elems[-1].split(".")[0]
    elif size == 4:
        return "_".join([elems[2], elems[3].split(".")[0]])

    raise Exception()


def _is_valid_method(lines):
    if lines is None:
        return False

    for x in lines:
        if "{}" in x:
            return False

    return True


def _write(out, lines):
    for line in lines:
        out.write(line)
        out.write("\n")


def _change_scaffolding_class(out_dir, level_suffix, class_path):
    lines = _read_all_lines(class_path, False)
    idx = 0
    new_name = None
    original_name = None
    while idx < len(lines):
        l = lines[idx]
        if "{" in l:
            class_name_elems = l.split(" ")
            original_name = class_name_elems[2]
            new_name = original_name + level_suffix
            class_name_elems[2] = new_name
            lines[idx] = " ".join(class_name_elems)
            idx += 1
            break

        idx += 1

    while idx < len(lines):
        l = lines[idx]
        lines[idx] = l.replace(original_name, new_name)
        idx += 1

    with open(os.path.join(out_dir, new_name + ".java"), 'w') as fh:
        for line in lines:
            fh.write(line)

    os.unlink(class_path)


def _separate_tests(out_dir, level_suffix, class_path):
    headers = []
    def_line = None
    with open(class_path, 'r') as fh:
        for line in fh:
            line = line.strip()
            if "{" in line:
                def_line = line.split(" ")
                def_line[2] += level_suffix
                def_line[4] += level_suffix
                annot = headers[-1]
                headers[-1] = annot[:-1] + ", separateClassLoader = true)"
                break

            headers.append(line)

        methods = None
        def _create_new(methods):
            if _is_valid_method(methods):
                elems = def_line.copy()
                method_name = methods[1].split(" ")[2][:-2]
                new_class_name = "_".join([elems[2], method_name])
                elems[2] = new_class_name
                with open(os.path.join(out_dir, new_class_name + ".java"), "w") as out:
                    _write(out, headers)
                    _write(out, [" ".join(elems)])
                    _write(out, methods)

        for line in fh:
            line = line.strip()
            if "@Test" == line:
                if methods is not None:
                    methods.append("}") # end of class
                    _create_new(methods)
                methods = []

            if methods is not None:
                methods.append(line)

        _create_new(methods)

    os.unlink(class_path)


def _parse_cp(st):
    lines = st.splitlines()
    for idx, line in enumerate(lines):
        line = line.strip()
        if line == "classpath:":
            return lines[idx + 1].split(" ")[-1], lines[idx + 2].split(" ")[-1],

    raise Exception(st)


def _compile(ant, git_root, compile_cmd, tmp_dir = None):
    cmd = [ant,
           "-f", "/home/mingwan/suitesize/defects4j/framework/projects/defects4j.build.xml",
           "-Dd4j.home=/home/mingwan/suitesize/defects4j",
           "-Dd4j.dir.projects=/home/mingwan/suitesize/defects4j/framework/projects",
           "-Dbasedir=" + git_root]

    if tmp_dir is None:
        cmd.append("-Dbuild.compiler=javac1.7")
    else:
        cmd.append("-Dd4j.test.dir=" + tmp_dir)

    cmd.append("clean")
    cmd.append(compile_cmd)
    cmd.append("classpath")

    st, no_error = d4j_check_output(cmd, cwd=git_root)
    if not no_error:
        raise Exception(" ".join(cmd) + "\n" + st)

    return _parse_cp(st)



def _compile_dev(git_root, proj_root, bug_id):
    relevant_root = os.path.join(proj_root, "relevant_tests")

    tests = set()
    for line in _read_all_lines(os.path.join(relevant_root, bug_id), True):

        if "ToStringBuilderTest" not in line:   # ToStringBuilderTest in Lang caused Exception.
            tests.add(line)
            tests.add(line + "$*")

    for root, dirs, files in os.walk(git_root):
        for file_name in files:
            if not file_name.endswith(".java"):
                continue

            out = os.path.join(root, file_name)
            lines = []
            need_write = False
            with open(out, "rb") as fh:
                for line in fh:
                    if not line.strip().startswith(b"suite.setName"):   # PITest should not use setName in JUnit3.
                        lines.append(line)
                        need_write = True

            if need_write:
                with open(out, "wb") as fh:
                    fh.writelines(lines)

    a, b = _compile("/home/mingwan/suitesize/defects4j/major/bin/ant", git_root, "compile.tests")
    return a, b, tests,


def _compile_gen(git_root, artifact_root):
    tests = set()
    if os.path.basename(git_root) == "Lang":
        p = os.path.join(git_root, "src/test/java/org/apache/commons/lang3/reflect/TypeUtilsTest.java")
        if os.path.exists(p):
            os.remove(p)

    with tempfile.TemporaryDirectory() as tmp_dir:
        for name in filter(lambda x: x.endswith(".tar.bz2"), os.listdir(artifact_root)):
            tarbz = os.path.join(artifact_root, name)
            if "evosuite" in name:
                candidate = tarbz + ".origin"
                if os.path.exists(tarbz):
                    tarbz = candidate

            tar = tarfile.open(tarbz, "r:bz2")
            try:
                tar.extractall(tmp_dir)
            finally:
                tar.close()

            level_suffix = "_" + _parse_tarbz_level(name)
            for root, dirs, files in os.walk(tmp_dir):
                for file_name in files:
                    if "_evosuite_" in file_name:
                        # This suite was already parsed.
                        continue

                    if file_name.endswith(".java"):
                        if "scaffolding" in file_name:
                            _change_scaffolding_class(root, level_suffix, os.path.join(root, file_name))
                        elif "ESTest" in file_name:
                            _separate_tests(root, level_suffix, os.path.join(root, file_name))


        for root, dirs, files in os.walk(tmp_dir):
            for file in files:
                if not file.endswith(".java"):
                    continue

                class_name = file[:-5]
                packages = os.path.relpath(root, tmp_dir)
                if packages != ".":
                    packages = packages.split(os.path.sep)
                    packages.append(class_name)
                    class_name = ".".join(packages)

                if not class_name.endswith("_scaffold"):
                    tests.add(class_name)

        a, b = _compile("ant", git_root, "compile.gen.tests", tmp_dir)
        return a, b, tests,


import gzip
def _run_pit(git_root, classes, ctx, dest, ignore_failing):
    source_dir, cp_str, tests = ctx
    pitpath = {os.path.join("/home/mingwan/suitesize/pit", name) for name in ("pitest-1.5.1.jar","pitest-entry-1.5.1.jar","pitest-command-line-1.5.1.jar", "xmlpull-1.1.3.1.jar",)}
    cp = {"/home/mingwan/suitesize/defects4j/framework/projects/lib/junit-4.13.jar"}
    if source_dir == "${source.home}":
        source_dir = "src"

    for elem in cp_str.split(":"):
        if "junit" in elem:
            if "4.13" not in elem:
                continue

        cp.add(elem)

    cmd = ["java",
           "-cp", ":".join(pitpath),
           "org.pitest.mutationtest.commandline.MutationCoverageReport",
           "--classPath", ",".join(cp),
           "--sourceDirs", source_dir,
           "--targetTests", ",".join(tests),
           "--targetClasses", ",".join(classes),
           "--reportDir", "matrix",
           "--threads", "3",
           "--fullMutationMatrix", "true",
           "--outputFormats", "XML"
           ]

    if ignore_failing:
        cmd.append("--skipFailingTests")
        cmd.append("true")

    print(" ".join(cmd))

    st, no_error = d4j_check_output(cmd, cwd=git_root)
    if not no_error:
        raise Exception(" ".join(cmd) + "\n" + st)

    result = None
    for root, dirs, files in os.walk(os.path.join(git_root, "matrix")):
        for file in files:
            if file.endswith(".xml"):
                if result is not None:
                    raise Exception()

                with open(os.path.join(root, file), "rb") as fh:
                    buf = fh.read()

                with gzip.GzipFile(dest ,'wb') as fh:
                    fh.write(buf)


def _main():
    import multiprocessing
    r = []
    with multiprocessing.Pool(4) as pool:
        for name in d4j.NAMES:
            for x in d4j.iterate_instance(name):
                bug_id = x[0]
                # if name == "Lang" and int(bug_id) in [41, 51]:
                #     r.append(pool.apply_async(_run, (name, bug_id,)))
                # if name == "Math" and int(bug_id) >= 37:
                r.append(pool.apply_async(_run, (name, bug_id,)))

        for x in r:
            x.wait()


def _run(name, bug_id):
    proj_root = os.path.join("defects4j", "framework", "projects", name)
    result_root = os.path.join("suites", name)
    bug_out_root = os.path.join(result_root, bug_id + "f")

    print(name, bug_id)

    modified_classes = os.path.join(proj_root, "modified_classes")
    classes = set()
    for line in _read_all_lines(os.path.join(modified_classes, bug_id + ".src"), True):
        classes.add(line)
        classes.add(line + "$*")

    dest_dev = os.path.join(bug_out_root, "matrix_dev.xml.gz")
    dest_gen = os.path.join(bug_out_root, "matrix_gen.xml.gz")

    err_dev = os.path.join(bug_out_root, "pit_error_dev.log")
    err_gen = os.path.join(bug_out_root, "pit_error_gen.log")

    dev_exist = os.path.exists(dest_dev)
    gen_exist = os.path.exists(dest_gen)
    # if dev_exist and gen_exist:
    #     if os.path.exists(err_dev):
    #         os.unlink(err_dev)
    #     if os.path.exists(err_gen):
    #         os.unlink(err_gen)
    #     return

    with d4j_checkout(name, bug_id + 'f') as git_root:
        if not dev_exist:
            try:
                start = time.time()
                ctx = _compile_dev(git_root, proj_root, bug_id)
                _run_pit(git_root, classes, ctx, dest_dev, False)
                if os.path.exists(err_dev):
                    os.unlink(err_dev)
                print(name, bug_id, "dev", time.time() - start)
            except Exception as e:
                print("Error(dev):", name, bug_id)
                with open(err_dev, "w") as fh:
                    fh.write(str(e))

        # if not gen_exist:
        try:
            start = time.time()
            ctx = _compile_gen(git_root, bug_out_root)
            _run_pit(git_root, classes, ctx, dest_gen, True)
            if os.path.exists(err_gen):
                os.unlink(err_gen)
            print(name, bug_id, "gen", time.time() - start)
        except Exception as e:
            print("Error(gen):", name, bug_id)
            with open(err_gen, "w") as fh:
                fh.write(str(e))


if __name__ == "__main__":
    _main()
