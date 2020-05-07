# Overview
This repository aims to share the scripts used to conduct the study for "Investigating the correlation between mutants and faults with respect to mutated code"

# Requirements
- == Oracle JDK 1.8
- \>= python 3.6

# Usage
## Install dependencies
```
pip install -r requirements.txt
```

## Extract experimental data

Following the Github's large file limitation, the data are distributed in the releases tab.

```
tar bz suites.tar.bz2 # generated using testsuitegenerator.py, killmap.py, and pit.py
tar bz changes.tar.bz2 # generated using patch.py
tar bz cov.tar.bz2 # generated using correlation.py and corr_pit.py
```

## Analyze data using jupyter
```
jupyter lab
```

# TODO
- generalize and refine script
