import os
import csv
from collections import defaultdict, namedtuple
import pandas as pd
import matplotlib.pyplot as plt
import d4j
import numpy as np

flierprops = {'marker': 'x', 'markersize': 3}
boxprops = dict(linestyle='-', linewidth=1)
colorprops=dict(boxes='black', whiskers='black', caps='black', medians='black')
medianprops = dict(linestyle='-', linewidth=1)

np.seterr(all='print')
plt.rcParams["font.family"] = "sans-serif"

def load_pit(proj_name, bug_id = None, ratio = None):
    data = []
    target_dir = os.path.join("cov_pit", proj_name)
    if bug_id is not None:
        target_dir = os.path.join(target_dir, bug_id)

    for root, dirs, files in os.walk(target_dir):
        if bug_id is None:
            bug_id = os.path.split(root)[1]

        for filename in files:
            if not filename.endswith(".csv"):
                continue
            if os.path.split(root)[1].startswith("."):
                continue

            ratio_type = filename.split(".")[0]
            try:
                ratio_type = float(ratio_type) / 1000.0
            except ValueError:
                pass                
                
            if ratio is not None and ratio != ratio_type:
                continue

            lines = []
            with open(os.path.join(root, filename), "r") as fh:
                for line in fh:
                    line = line.strip()
                    if len(line) == 0:
                        continue
                    lines.append(line)
                    
            reader = csv.reader(lines)
            for row in reader:
                row[2] = float(row[2])
                row[3] = float(row[3])
                row[4] = float(row[4])
                row[5] = float(row[5])

                data.append(row)

    if len(data) == 0:
        print("Ignore empty", proj_name, bug_id, ratio)
        return None

    data = pd.DataFrame(data)
    data.columns = ["name", "bug_id", "ratio", "cls_level", "method_level", "stmt_level", "is_bug"]
    data = data.loc[data["cls_level"].notnull() & data["method_level"].notnull() & data["stmt_level"].notnull(), :]
    for name in ["cls_level", "method_level", "stmt_level", "is_bug"]:
        if len(np.unique(data[name])) == 1:
            print("Ignore constant value", proj_name, bug_id, ratio, name)
            return None

    return data

def load(proj_name, bug_id = None, ratio = None):
    data = []
    target_dir = os.path.join("cov", proj_name)
    if bug_id is not None:
        target_dir = os.path.join(target_dir, bug_id)

    for root, dirs, files in os.walk(target_dir):
        if bug_id is None:
            bug_id = os.path.split(root)[1]

        for filename in files:
            if not filename.endswith(".csv"):
                continue
            if os.path.split(root)[1].startswith("."):
                continue

            ratio_type = filename.split(".")[0]
            try:
                ratio_type = float(ratio_type) / 1000.0
            except ValueError:
                pass                
                
            if ratio is not None and ratio != ratio_type:
                continue

            lines = []
            with open(os.path.join(root, filename), "r") as fh:
                for line in fh:
                    line = line.strip()
                    if len(line) == 0:
                        continue
                    lines.append(line)
                    
            reader = csv.reader(lines)
            for row in reader:
                row[2] = float(row[2])
                row[3] = float(row[3])
                row[4] = float(row[4])
                row[5] = float(row[5])

                data.append(row)

    if len(data) == 0:
        print("Ignore empty", proj_name, bug_id, ratio)
        return None

    data = pd.DataFrame(data)
    data.columns = ["name", "bug_id", "ratio", "cls_level", "method_level", "stmt_level", "is_bug"]
    data = data.loc[data["cls_level"].notnull() & data["method_level"].notnull() & data["stmt_level"].notnull(), :]
    for name in ["cls_level", "method_level", "stmt_level", "is_bug"]:
        unq = np.unique(data[name])
        if len(unq) == 1:
            print("Ignore constant value", proj_name, bug_id, ratio, unq)
            return None

    return data