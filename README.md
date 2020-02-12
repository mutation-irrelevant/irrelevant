# Overview
This repository aims to share the scripts used to conduct the study for "Investigating the correlation between mutation score and fault detection with irrelevant mutants"

# Requirements
- == Oracle JDK 1.7
- \>= python 3.6

# Usage
## Install dependencies
```
pip install -r requirements.txt
```

## Initialize defects4j
```
git submodule init
git submodule update
cd defects4j
cpanm --installdeps .
./init.sh
```

## Generate test suites
```
python testsuitegenerator.py
```

## Generate testcase-mutants kill matrix
```
python killmap.py
```

### Compute mutation scores
```
python correlation.py
```
