import os
import tempfile
import json
import os
import subprocess
from collections import defaultdict

_ROOT = os.path.join("changes")


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


_BANNED = {
    "Closure": {"63", "93"},
    "Lang": {"2"},
    "Time": {"21"},
    "Math": {},
    "Chart": {}
}


def iterate_changes(proj_name):
    global _ROOT, _BANNED
    root_dir = os.path.join(_ROOT, proj_name)
    banned = _BANNED[proj_name]
    result = []
    total = 0
    for id in os.listdir(root_dir):
        id_raw = id[:-1]
        if id_raw in banned:
            continue

        total += 1
        lines, methods = load_changes(proj_name, id)
        if lines is None or methods is None:
            print(proj_name, id)
            print("XXX")
            continue

        result.append([int(id_raw), lines, methods])

    print("{}: Total {} instances".format(proj_name, total))
    result.sort(key=lambda x: x[0])
    for item in result:
        item[0] = str(item[0])
        yield item


def load_changes(proj_name, bug_id):
    global _ROOT

    root_dir = os.path.join(_ROOT, proj_name, bug_id)
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
    methods = set()
    file_ids = set(info.keys())
    for fid in file_ids:
        meta = defs[fid]
        exceptions = {int(k): v for k, v in info[fid].items()}
        positions = {int(k): v for k, v in meta["positions"].items()}
        for line_no in meta["lines"]:
            replaced = exceptions.get(line_no)
            if replaced is not None:
                if replaced == "ignore":
                    raise Exception(proj_name, bug_id)
                elif type(replaced) == list:
                    if len(replaced) == 0:
                        raise Exception(proj_name, bug_id, replaced)

                    op_type = replaced[0]
                    if op_type == "no_method":
                        lines[op_type].add(line_no)
                        methods.add(op_type)
                        continue
                    elif op_type == "replaced":
                        line_no = replaced[1]
                    else:
                        raise Exception(proj_name, bug_id, replaced)
                    # items = [items]

            pos = line_no
            desc = None
            while pos > 0:
                desc = positions.get(pos)
                if desc is not None:
                    break
                pos -= 1

            if desc is None:
                # print(line_no)
                print("??", proj_name, bug_id, fid, line_no)
                return None, None

            for names in desc:
                names = _check_symbol(names)
                methods.add("@".join(names))
                lines[names[0]].add(line_no)

    if len(lines) == 0:
        print("no lines", proj_name, bug_id)
        return None, None

    return lines, methods