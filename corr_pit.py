import os
import random
import csv
import numpy as np
import d4j
import xml.sax as sax
from collections import defaultdict
import json
import gzip

np.seterr(all='raise')


class PitParser(sax.handler.ContentHandler):
    def __init__(self, test_size, method_changes, line_changes):
        self._method_name = None
        self._class_name = None
        self.killmap = {}
        self.mutants = {}
        self.method_mutants = []
        self._freeze = False
        self.stmt_mutants = []
        self._mutator = None
        self._index = None
        self._block = None
        self._test_size = test_size
        self._content = ""
        self._warn = set()
        self._method_changes = set()
        for m in method_changes:
            if m == "org.apache.commons.math.optimization.univariate.MultiStartUnivariateRealOptimizer@optimize(FUNC,org.apache.commons.math.optimization.GoalType,double,double)":
                m = m.replace("FUNC", "org.apache.commons.math.analysis.UnivariateRealFunction")
            else:
                try:
                    idx = 0
                    while True:
                        pos = m.find("<", idx)
                        if pos < 0:
                            m = m.replace("T[]", "java.lang.Object[]")
                            break

                        end = m.find(">", pos + 1)
                        target = m[pos:end + 1]
                        if target == "<init>":
                            idx = end + 1
                            continue

                        m = m.replace(target, "")
                except:
                    pass
            self._method_changes.add(m)

        self._line_changes = line_changes


    # def setDocumentLocator(self, locator):
    #     super().setDocumentLocator(locator)

    # def startDocument(self):
    #     super().startDocument()

    def endDocument(self):
        super().endDocument()
        killmap = self.killmap
        for i in range(self._test_size - len(killmap)):
            killmap[str(i)] = []

    # def startPrefixMapping(self, prefix, uri):
    #     super().startPrefixMapping(prefix, uri)

    # def endPrefixMapping(self, prefix):
    #     super().endPrefixMapping(prefix)

    # def startElement(self, name, attrs):
    #

    def endElement(self, name):
        content = self._content
        self._content = ""
        if name == "mutatedClass":
            self._class_name = content
        elif name == "mutatedMethod":
            self._method_name = content.replace("$", ".")
        elif name == "methodDescription":
            self._method_desc = _parse_desc(content.replace("$", "."))
        elif name == "lineNumber":
            self._line = int(content)
        elif name == "mutator":
            self._mutator = content
        elif name == "index":
            self._index = int(content)
        elif name == "block":
            self._block = int(content)
        elif name == "killingTests":
            idx = len(self.mutants)
            for name in content.split("|"):
                if len(name) == 0:
                    continue

                x = self.killmap.get(name)
                if x is None:
                    x = []
                    self.killmap[name] = x

                x.append(idx)
        elif name == "mutation":
            mutant_key = (self._class_name, self._method_name, self._line, self._mutator, self._method_desc, self._block, self._index,)
            idx = self.mutants.get(mutant_key)
            if idx is None:
                idx = len(self.mutants)
                self.mutants[mutant_key] = idx

                if self._line in self._line_changes[self._class_name]:
                    self.stmt_mutants.append(idx)

                total_name = self._class_name + "@" + self._method_name + self._method_desc
                if total_name in self._method_changes:
                    self.method_mutants.append(idx)

    # def startElementNS(self, name, qname, attrs):
    #     super().startElementNS(name, qname, attrs)
    #
    # def endElementNS(self, name, qname):
    #     super().endElementNS(name, qname)

    def characters(self, content):
        self._content += content

    def freeze(self):
        self._freeze = True


    # def ignorableWhitespace(self, whitespace):
    #     super().ignorableWhitespace(whitespace)

    # def processingInstruction(self, target, data):
    #     super().processingInstruction(target, data)
    #
    # def skippedEntity(self, name):
    #     super().skippedEntity(name)


def _parse_tarbz_level(name):
    elems = name.split("-")
    size = len(elems)
    if size == 3:
        return elems[-1].split(".")[0]
    elif size == 4:
        return "_".join([elems[2], elems[3].split(".")[0]])

    raise Exception()


def _map_evosuite(tarbz):
    level = "_" + _parse_tarbz_level(tarbz)
    def _assign(name):
        cls_name, method_name = name.split("::")
        return cls_name + level + "_" + method_name

    return _assign


def _load_testmap(suite_dir, filelist):
    result = {}
    for file_name in filter(lambda x: x.endswith(".map"), filelist):
        tarbz = file_name[:-4]
        with open(os.path.join(suite_dir, file_name), "r") as fh:
            result[tarbz] = json.load(fh)

    return result


def _load_xml(suite_dir, test_size, method_changes, line_changes):
    parser = PitParser(test_size, method_changes, line_changes)
    count = 0
    for file in os.listdir(suite_dir):
        if not file.endswith(".xml.gz"):
            continue

        with gzip.GzipFile(os.path.join(suite_dir, file), 'rb') as fh:
            sax.parse(fh, parser)

        parser.freeze()
        count += 1

    if count < 2:
        return None


    return parser


def _mask_from_array(indices, size):
    row = np.zeros(size, dtype=bool)
    row[indices] = 1
    return row


def compute_correlation(proj_name, bug_id, line_changes, method_changes, u1, u2, u3):
    # print(proj_name, bug_id)
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
                return None, "timeout"

    for fail_file in filter(lambda x: x.endswith(".fails"), file_list):
        tarbz = fail_file[:-6]
        if "evosuite" in fail_file:
            mapper = _map_evosuite(tarbz)
        else:
            mapper = lambda n: n

        with open(os.path.join(suite_dir, fail_file), "r", encoding='UTF8') as fh:
            for l in fh:
                l = l.strip()
                if l.startswith("---"):
                    name = l.strip()[4:]
                    try:
                        name = mapper(name)
                    except KeyError:
                        print(tarbz, name)
                        return None, "unknown",

                    fails.add(name)

    if len(fails) == 0:
        print(proj_name, bug_id, "No triggering tests found")
        return None, "no_fails",

    # print(fails)
    test_size = 0
    for killmap_file in filter(lambda x: x.endswith(".killmap.csv"), file_list):
        with open(os.path.join(suite_dir, killmap_file)) as fh:
            for line in fh:
                if len(line.strip()) == 0:
                    continue

                test_size += 1

    if test_size < 532:
        print(proj_name, bug_id, "Not enough test cases: ", test_size)
        return None, "insufficient",

    pit_result = _load_xml(suite_dir, test_size, method_changes, line_changes)
    if pit_result is None:
        print(proj_name, bug_id, "No PIT result")
        return None, "mutation_error",

    if len(pit_result.stmt_mutants) == 0:
        print("No statement mutants", proj_name, bug_id)
        for key, lines in pit_result._line_changes.items():
            for mutant in pit_result.mutants:
                if key in mutant:
                    t = mutant[2]
                    if t in lines:
                        print(key, lines, mutant)
        return None, "no_stmt_mutants",
    if len(pit_result.method_mutants) == 0:
        print("No methods mutants", proj_name, bug_id)
        for name in pit_result._method_changes:
            print("==============", name)
            name, desc = name.split("@")[1].split("(")
            for mutant in pit_result.mutants:
                if name in mutant:
                    print(mutant)
        return None, "no_method_mutants",

    killmap = []
    total_count = len(pit_result.mutants) + 1
    has_dev_fail = False
    for test_name, indices in pit_result.killmap.items():
        idx = test_name.find("(")
        if idx >= 0:
            test_name = test_name[:idx]

        idx = test_name.rfind(".")
        test_name = test_name[:idx] + "::" + test_name[idx + 1:]
        try:
            fails.remove(test_name)
            trigger_tests.append(len(killmap))
            has_dev_fail |= "ESTest" not in test_name or "Regression" not in test_name
        except KeyError:
            pass

        killmap.append(_mask_from_array(indices, total_count))

    if not has_dev_fail:
        print(proj_name, bug_id, "has no dev failure")
        return None, "no_fails",

    if len(trigger_tests) == 0:
        print(proj_name, bug_id, "No trigger tests found: ", len(trigger_tests))
        return None, "no_fails",

    killmap = np.stack(killmap)
    method_level_mutants = np.array(pit_result.method_mutants, dtype=int)
    line_level_mutants = np.array(pit_result.stmt_mutants, dtype=int)
    all_mask = np.array(range(total_count - 1))

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


def _run(proj_name, item):
    bug_id = item[0]
    try:
        generator, error = compute_correlation(proj_name, *item)
        if generator is None:
            return error, proj_name, item,

        out_root = os.path.join("cov_pit", proj_name, bug_id)
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
                    raise e

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
                    raise e
        return None
    except Exception as e:
        print(proj_name, bug_id, e)
        return "unknown", proj_name, bug_id,


def _main():
    stats = defaultdict(lambda: defaultdict(int))
    total = defaultdict(int)
    import multiprocessing
    import pprint
    with multiprocessing.Pool(8) as pool:
        tasks = []
        for proj_name in d4j.NAMES:
            for item in d4j.iterate_instance(proj_name):
                tasks.append(pool.apply_async(_run, (proj_name, item)))

        for k in tasks:
            t = k.get()
            if t is not None:
                t, name, bug_id = t
                stats[name][t] += 1
                total[t] += 1

    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(stats)
    pp.pprint(total)


type_map = {
    "I": "int",
    "J": "long",
    "S": "short",
    "B": "byte",
    "C": "char",
    "F": "float",
    "D": "double",
    "Z": "boolean",
    "V": "void"
}
def _parse_desc(change):
    global type_map
    suffix = ""
    params = []

    idx = 1
    while idx < len(change):
        c = change[idx]
        idx += 1
        if c == ")":
            break
        elif c == "[":
            suffix = "[]"
        elif c == "L":
            end = change.find(";", idx)
            type_name = change[idx:end].replace("/", ".")
            params.append(type_name + suffix)
            suffix = ""
            idx = end + 1
        else:
            t = type_map[c]
            params.append(t + suffix)
            suffix = ""

    return "(" + ",".join(params) + ")"


if __name__ == "__main__":
    _main()
