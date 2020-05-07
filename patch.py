import os
import tempfile
import json
import os
import javalang
import shutil
import subprocess
from collections import defaultdict
from d4jconstants import d4j_iterate_fixes, d4j_checkout, d4j_patchset, d4j_compile, d4j_checkout_into


def _check_symbol(names):
    cls_name = names[0]
    try:
        while True:
            start = cls_name.index("<")
            end = cls_name.index(">")
            cls_name = cls_name[:start] + cls_name[end + 1:]
    except ValueError:
        pass

    names[0] = cls_name
    desc = names[1].replace("...", "[]")
    param_start_index = desc.index("(")
    names[1] = desc[:param_start_index] + desc[param_start_index:].replace("$", ".")
    return names


def load_changes(proj_name, bug_id):
    root_dir = _get_changes_root(proj_name, bug_id)
    info_path = os.path.join(root_dir, "info.json")
    if not os.path.exists(info_path):
        return None, None
    
    with open(info_path, "r") as fh:
        info = json.load(fh)

    defs_path = os.path.join(root_dir, "defs.json")
    if not os.path.exists(info_path):
        return None, None

    with open(defs_path, "r") as fh:
        defs = json.load(fh)

    lines = defaultdict(set)
    methods = []
    file_ids = set(info.keys())
    visited = []
    for fid in file_ids:
        meta = defs[fid]
        exceptions = {int(k): v for k, v in info[fid].items()}
        positions = {int(k): v for k, v in meta["positions"].items()}
        for line_no in meta["lines"]:
            items = exceptions.get(line_no)
            if items is None:
                items = [[line_no, "method"]]
            elif items == "ignore":
                items = []
            elif len(items) > 0 and not isinstance(items[0], list):
                items = [items]

            for line_no, exc_type in items:
                if exc_type == "class":
#                     print(proj_name, bug_id, "has class-level changes")
                    return None

                pos = line_no
                while pos > 0:
                    desc = positions.get(pos)
                    if desc is not None:
                        break
                    pos -= 1

                if desc is None:
                    print(line_no)
                    return None, None

                for names in desc:
                    names = _check_symbol(names)
                    methods.append("@".join(names))
                    lines[names[0]].add(line_no)

    return lines, methods
        



def _get_changes_root(proj_name, bug_id):
    out = os.path.join("changes", proj_name, bug_id)
    os.makedirs(out, exist_ok=True)
    return out


def _parse_ant_echo(line):
    return line.split(b" ")[-1].decode("utf-8")


def _get_classes_path(git_home):
    cwd = os.getcwd()
    ant_bin = os.path.join(cwd, "defects4j/major/bin/ant")
    build_xml = os.path.join(cwd, "build.xml")
    try:
        ant = subprocess.run([ant_bin, "-f", build_xml, "-Dbasedir={}".format(git_home), "classpath"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=git_home)
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        raise e

    lines = ant.stdout.splitlines()
    for idx, line in enumerate(lines):
        line = line.strip()
        if line == b"classpath:":
            buildpath = _parse_ant_echo(lines[idx + 1])
            classpaths = _parse_ant_echo(lines[idx + 2])
            return classpaths + ":" + os.path.join(git_home, buildpath), buildpath # Some project do not include build output dir into classpaths.

class LineReader:
    TARGET_TYPE = set([b"class", b"enum", b"interface"])
    def __init__(self, lines, filename):
        self._lines = lines
        self._idx = 0
        self._classname = None
        self._line = None
        self._filename = filename


    def next(self):
        if self.available():
            line = self._line
            self._line = None
            return self._classname, line

        return None, None


    def _next_class(self, line):
        #This method assumes that line is 'Compiled from' and self._idx indicates the next line.
        idx = self._idx
        lines = self._lines
        
        while True:
            check = line.split(b" ")[-1][1:-1].decode("utf-8")
            line = lines[idx].strip()
            idx += 1
            if self._filename == check:
                class_defline = line.split(b" ")
                for i, elem in enumerate(class_defline):
                    if elem in LineReader.TARGET_TYPE:
                        self._classname = class_defline[i + 1].decode("utf-8")
                        self._idx = idx
                        return

                raise Exception(class_defline)

            while not line.startswith(b"Compiled from"):
                if idx >= len(lines):
                    self._idx = idx
                    return

                line = lines[idx].strip()
                idx += 1

        return None


    def available(self):
        if self._line is None:
            lines = self._lines
            idx = self._idx

            if idx >= len(lines):
                return False

            line = lines[idx].strip()
            self._idx += 1
            if line.startswith(b"Compiled from"):
                self._next_class(line)
            else:
                self._line = line

            return self.available()

        if self._classname is None:
            raise Exception()
       
        return True

        
    def read_startline(self):
        idx = self._idx
        lines = self._lines
        line = lines[idx]
        result = None
        if b"LineNumberTable" in line:
            idx += 1
            line = lines[idx].strip()
            result = int(line.split(b" ")[1][:-1])

        while len(line) > 0 and line.strip() != b'}':
            # Skip entire Tables
            idx += 1
            line = lines[idx].strip()

        self._idx = idx + 1

        return result


def _iterate_jsonp_result(lines, filename):
    # Compiled from "test.java"
    #     final class X extends java.lang.Enum<X> {
    #     public static final X A;

    #     private static final X[] $VALUES;

    #     public static X[] values();
    #         LineNumberTable:
    #         line 3: 0

    #     public static X valueOf(java.lang.String);
    #         LineNumberTable:
    #         line 3: 0

    #     private X();
    #         LineNumberTable:
    #         line 3: 0

    #     public static void y(int, int);
    #         LineNumberTable:
    #         line 10: 0

    #     static {};
    #         LineNumberTable:
    #         line 4: 0
    #         line 3: 13
    #     }

    reader = LineReader(lines, filename)
    while reader.available():
        class_fullname, line = reader.next()
        if b"(" in line:
            line = line.decode("utf-8")
            name, desc = line.split("(")
            name = name.split(" ")[-1]
            desc = desc.split(")")[0].replace(" ", "") + ")" # remove throws ~
            signature = name + "(" + desc
            
            startline = reader.read_startline()
            if startline is not None:
                yield class_fullname, signature, startline


def _read_definitions(classpaths, build_path, changed_file_path):
    filename = os.path.split(changed_file_path)[1]
    classes = _get_candidate_classes(changed_file_path, build_path)
    classes = map(lambda n: "{}".format(n), classes)

    defs = defaultdict(list)
    cmds = ["javap", "-l", "-p", "-classpath", classpaths, *classes]
    javap = subprocess.run(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if len(javap.stderr) > 0:
        raise Exception(javap.stderr.decode("utf-8"))

    for class_name, signature, line_no in _iterate_jsonp_result(javap.stdout.splitlines(), filename):
        bracket_idx = signature.index("(")
        if signature[:bracket_idx] == class_name:
            method_fullname = "<init>" + signature[bracket_idx:]
        else:
            method_fullname = signature

        defs[line_no].append([class_name, method_fullname])

    return defs


def _get_candidate_classes(changed_path, build_path):
    with open(changed_path, "r", errors="replace") as fh:
        buf = fh.read()

    tree = javalang.parse.parse(buf)
    package_name = tree.package.name
    if len(tree.types) != 1:
        raise Exception(changed_path)

    class_name = tree.types[0].name
    if class_name + ".java" != os.path.split(changed_path)[1]:
        raise Exception(changed_path)

    root_name = package_name + "." + class_name
    package_path = os.path.join(build_path, *package_name.split("."))
    candidates = list(name for name in os.listdir(package_path) if name.endswith(".class"))
    candidates = set(map(lambda n: package_name + "." + n[:-len(".class")], candidates))
    if root_name not in candidates:
        raise Exception()

    return candidates


def diff(proj_name, bug_id):
    output_dir = _get_changes_root(proj_name, bug_id)
    info_path = os.path.join(output_dir, "info.json")
    # if os.path.exists(info_path):
    #     return

    print(proj_name, bug_id)
    
    patchset = d4j_patchset(proj_name, bug_id)
    defs = {}

    # Assume that
    # each source has only one root class
    # the names of other classes such as anonymous or inner classes start with the name of the root class.
    with d4j_checkout(proj_name, bug_id) as git_home:
    # with tempfile.TemporaryFile():
    #     git_home = "/tmp/a"
        # d4j_checkout_into(proj_name, bug_id, git_home)
        class_paths, build_path = _get_classes_path(git_home)
        build_path = os.path.join(git_home, build_path)

        for patch in patchset:
            changed_source_path = os.path.join(git_home, patch.path)
            rel_path = os.path.relpath(changed_source_path, git_home).split("/")
            partial = min(4, len(rel_path))
            file_id = ".".join(rel_path[-partial:])
            if file_id in defs:
                raise Exception()

            added = {}
            removed = set()

            for h in patch:
                for line in h:
                    if line.is_added:
                        #added line has no source_line_no
                        if line_no not in added:
                            added[line_no] = [line]
                        else:
                            added[line_no].append(line)
                    else:
                        line_no = line.source_line_no
                        if line.is_removed:
                            removed.add(line_no)

            positions = _read_definitions(class_paths, build_path, changed_source_path)
            with open(changed_source_path, "r", errors="replace") as rfh, open(os.path.join(output_dir, file_id), "w") as ofh:
                for line_no, line in enumerate(rfh):
                    line_no += 1
                    marker = ("!" if line_no in positions else " ") * 2
                    changed = ("@" if line_no in removed else " ") * 3

                    ofh.write("{} {}{} {}".format(line_no, changed, marker, line))

                    if line_no in added:
                        for added_line in added[line_no]:
                            ofh.write("{} +++ {}".format(line_no, added_line))

            defs[file_id] = {"positions": positions, "lines": list(removed)}

    with open(os.path.join(output_dir, "defs.json"), "w") as fh:
        json.dump(defs, fh, indent=2)

    if not os.path.exists(info_path):
        with open(info_path, "w") as fh:
            json.dump({fid: {l: None for l in pos["lines"]} for fid, pos in defs.items()}, fh, indent=2)


if __name__ == "__main__":
    for proj_name in ["Time", "Closure", "Lang", "Math", "Chart"]:
        for bug_id in d4j_iterate_fixes(proj_name):
            diff(proj_name, bug_id)