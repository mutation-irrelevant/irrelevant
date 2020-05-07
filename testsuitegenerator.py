import os
import tempfile
from testsuite import iterate_suites, GenTestSuite, EvoSuite
from killmap import Killmap
from d4jconstants import *
from datetime import datetime
from subprocess import CalledProcessError, TimeoutExpired


def generate_devsuite(suite):
    proj_name = suite.proj_name
    bug_id = suite.bug_id

    with d4j_opposed_checkout(proj_name, bug_id) as git_home:
        all_tests_path, failing_tests_path = d4j_run_tests(git_home, None)
        Killmap.initialize(suite, all_tests_path)


class SuiteGenerator:
    OUTPUT_DIR = "raw_tests"
    TIMEOUT = 15 * 60
    def __init__(self, suite_type):
        self.suite_type = suite_type


    def _get_generation_path(self, proj_name, bug_id):
        return os.path.join(SuiteGenerator.OUTPUT_DIR, proj_name, self.suite_type, "1")


    def _get_logpath(self, proj_name, bug_id):
        return os.path.join(SuiteGenerator.OUTPUT_DIR, "logs", self._get_log_filename(proj_name, bug_id))


    def _get_log_filename(self, proj_name, bug_id):
        raise Exception()
        return ""


    def _generate(self, proj_name, bug_id, log_fh):
        raise Exception()


    def _generate_raw(self, proj_name, bug_id):
        tarbz_name = GenTestSuite.get_tarbz_filename(proj_name, bug_id, self.suite_type)
        dest = os.path.join(self._get_generation_path(proj_name, bug_id), tarbz_name)
        if os.path.exists(dest):
            # the suite has been already generated.
            return dest

        if os.path.exists(self._get_logpath(proj_name, bug_id)):
            # the remained log means the generation failed.
            return None

        with tempfile.TemporaryFile("w+") as fh:
            try:
                self._generate(proj_name, bug_id, fh)
            except (CalledProcessError, TimeoutExpired) as e:
                print(e)
                print("generate() causes an exception - ", type(e))

                fh.seek(0)
                # Defects4j does not remove temporary data when an error occurs.
                # locate the temporary data from the log and remove them by ourselves.
                # format: Checking out 00fea9d8 to /tmp/run_evosuite.pl_19755_1556759859............. OK
                run_tmp_dir = fh.readline()

                try:
                    idx = run_tmp_dir.index(".", 45)
                    run_tmp_dir = run_tmp_dir[25:idx]
                    if os.path.exists(run_tmp_dir):
                        shutil.rmtree(run_tmp_dir)
                except ValueError:
                    #Do not care if the temporary directory cannot be located.
                    pass

        return dest if os.path.exists(dest) else None


    def generate(self, suite):
        proj_name = suite.proj_name
        bug_id = suite.bug_id

        if suite.is_suite_available():
            return

        generated_path = self._generate_raw(proj_name, bug_id)
        if generated_path is None:
            return

        print(datetime.now(), ": remove broken test cases")
        try:
            d4j_fix_suites(proj_name, bug_id, self.suite_type, os.path.split(generated_path)[0])
        except (subprocess.CalledProcessError, TimeoutExpired):
            print("Could not fix", suite)
            return


        print(datetime.now(), ": identify failing tests")
        try:
            with d4j_opposed_checkout(proj_name, bug_id) as git_home:
                all_tests_path, failing_tests_path = d4j_run_tests(git_home, generated_path)
                suite.register_trigger_tests(failing_tests_path)
                suite.register_suite(generated_path)
                Killmap.initialize(suite, all_tests_path)
        except subprocess.CalledProcessError:
            print("Identification failed.") 
            return        


class EvoSuiteGenerator(SuiteGenerator):
    def __init__(self, criterion):
        super().__init__("evosuite-{}".format(criterion))
        self.criterion = criterion


    def _generate(self, proj_name, bug_id, log_fh):
        d4j_run_evosuite(proj_name, bug_id, SuiteGenerator.OUTPUT_DIR, self.criterion, timeout=SuiteGenerator.TIMEOUT, log_fh=log_fh)


    def _get_log_filename(self, proj_name, bug_id):
        return "{}.{}.{}.1.log".format(proj_name, bug_id, self.criterion)


class RandoopGenerator(SuiteGenerator):
    def __init__(self):
        super().__init__("randoop")


    def _generate(self, proj_name, bug_id, log_fh):
        d4j_run_randoop(proj_name, bug_id, SuiteGenerator.OUTPUT_DIR, timeout=SuiteGenerator.TIMEOUT, log_fh=log_fh)


    def _get_log_filename(self, proj_name, bug_id):
        return "{}.{}.1.log".format(proj_name, bug_id)


from testsuite import DevTestSuite, RanSuite
def _generate(proj_name, bug_id, suite_type):
    if "evosuite" in suite_type:
        suite_type = suite_type[9:]
        EvoSuiteGenerator(suite_type).generate(EvoSuite(proj_name, bug_id, suite_type))
    elif suite_type == "randoop":
        RandoopGenerator().generate(RanSuite(proj_name, bug_id))
    elif suite_type == "dev":
        generate_devsuite(DevTestSuite(proj_name, bug_id))


def _main():
    import sys
    import locale
    import multiprocessing
    
    loc = locale.getdefaultlocale()[1]
    if loc != "UTF-8":
        raise Exception("non-utf8 ({}) langauge may cause an infinite loop.".format(loc))

    generators = {"evosuite-{}".format(t): EvoSuiteGenerator(t).generate for t in EvoSuite.CRITERIA}
    generators["randoop"] = RandoopGenerator().generate
    generators["dev"] = generate_devsuite

    tasks = []
    for proj_name in ["Math", "Chart", "Lang", "Time", "Closure"]:
        for suites in iterate_suites(proj_name):
            for s in suites:
                if not s.is_suite_available():
                    with open(os.path.join("mutations", proj_name, s.bug_id, "no_" + s.suite_type), "w"):
                        pass
                    tasks.append([s.proj_name, s.bug_id, s.suite_type])

    with multiprocessing.Pool(7) as pool:
        pool.starmap(_generate, tasks)


if __name__ == "__main__":
    _main()