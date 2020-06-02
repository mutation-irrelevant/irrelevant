import os
import random
import csv
import numpy as np
import d4j
import json

np.seterr(all='raise')

def _parse_tarbz_level(name):
    elems = name.split("-")
    size = len(elems)
    if size == 3:
        return elems[-1].split(".")[0]
    elif size == 4:
        return "_".join([elems[2], elems[3].split(".")[0]])

    raise Exception()


def _map_evosuite(tarbz, m):
    level = "_" + _parse_tarbz_level(tarbz)
    def _assign(name):
        cls, _ = name.split("::")
        name = cls + level
        return m[name]

    return _assign



def compute_correlation(proj_name, bug_id, line_changes, method_changes, line_mutants, method_mutants, mutant_count):
    killmap = []
    trigger_tests = []
    fails = set()
    suite_dir = os.path.join("suites", proj_name, bug_id + "f")
    file_list = os.listdir(suite_dir)

    for file_name in filter(lambda x: x.endswith(".json"), file_list):
        with open(os.path.join(suite_dir, file_name)) as fh:
            timeout_list = json.load(fh).get("timeout", [])
            if len(timeout_list) > 0:
                print("timeout", proj_name, bug_id)
                return None, "timeout",

    for fail_file in filter(lambda x: x.endswith(".fails"), file_list):
        with open(os.path.join(suite_dir, fail_file), "r", encoding="utf8") as fh:
            for l in fh:
                l = l.strip()
                if l.startswith("---"):
                    name = l.strip()[4:]
                    fails.add(name)

    if len(fails) == 0:
        print(proj_name, bug_id, "No triggering tests found")
        return None, "no_fails",

    for killmap_file in filter(lambda x: x.endswith(".killmap.csv"), file_list):
        with open(os.path.join(suite_dir, killmap_file)) as fh:
            for line in fh:
                row = line.strip().split(",")
                kills = row[1:]
                # if all(x == '' for x in kills):
                #     continue

                try:
                    fails.remove(row[0])
                    trigger_tests.append(len(killmap))
                except KeyError:
                    pass

                subrow = [v in {"EXC", "FAIL"} for v in kills]
                if len(subrow) != mutant_count:
                    print(len(subrow), mutant_count, line)
                    return None, "error",
                killmap.append(subrow)

    test_size = len(killmap)
    expected = mutant_count * test_size
    if test_size < 532:
        print(proj_name, bug_id, "Not enough test cases: ", len(killmap))
        return None, "insufficient",

    if len(trigger_tests) == 0:
        print(proj_name, bug_id, "No trigger tests found: ", len(trigger_tests))
        return None, "no_fails",

    killmap = np.array(killmap, ndmin=2, dtype=bool)
    if killmap.size != expected:
        return None, "error",
    method_level_mutants = np.array(method_mutants, dtype=int)
    line_level_mutants = np.array(line_mutants, dtype=int)
    all_mask = np.array(range(mutant_count - 1))

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
                row = [proj_name, bug_id, size / test_size]
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
                row = [proj_name, bug_id, size]
                testset = np.random.choice(test_size, size=size)
                is_bug = len(np.intersect1d(testset, trigger_tests)) > 0
                covered = np.any(killmap[testset,:], axis=0)

                row.append(class_level(covered))
                row.append(method_level(covered))
                row.append(line_level(covered))
                row.append(is_bug)
                yield row

    return _generator, None,


def _main():
    from collections import defaultdict
    stats = defaultdict(lambda: defaultdict(int))
    total = defaultdict(int)
    import multiprocessing
    import pprint
    with multiprocessing.Pool(4) as pool:
        tasks = []
        for proj_name in d4j.NAMES:
#         for proj_name in ["Chart"]:
            for item in d4j.iterate_instance(proj_name):
                tasks.append(pool.apply_async(_run, (proj_name, item)))

        for k in tasks:
            t = k.get()
            t, name, bug_id = t
            stats[name][t] += 1
            total[t] += 1

    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(stats)
    pp.pprint(total)


def _run(proj_name, item):
    bug_id = item[0]

    generator, error = compute_correlation(proj_name, *item)
    if generator is None:
        return error, proj_name, item,

    out_root = os.path.join("cov", proj_name, bug_id)
    os.makedirs(out_root, exist_ok=True)
    for t in ["max20", "max50"]:
        out_file = os.path.join(out_root, "{}.csv".format(t))
        if not os.path.exists(out_file):
            print(proj_name, bug_id, t)
            try:
                with open(out_file, "w", newline='') as fh:
                    writer = csv.writer(fh)
                    for row in generator(t):
                        writer.writerow(row)
            except Exception as e:
                os.unlink(out_file)
                return "u", proj_name, bug_id,

    for ratio in range(25, 525, 25):
        out_file = os.path.join(out_root, "{}.csv".format(ratio))
        ratio /= 1000
        if not os.path.exists(out_file):
            print(proj_name, bug_id, ratio)
            try:
                with open(out_file, "w", newline='') as fh:
                    writer = csv.writer(fh)
                    for row in generator(ratio):
                        writer.writerow(row)
            except Exception as e:
                os.unlink(out_file)
                return "u", proj_name, bug_id,
    
    return "s", proj_name, bug_id,


if __name__ == "__main__":
    _main()
