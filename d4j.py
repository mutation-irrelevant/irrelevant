import patch
import os
from collections import defaultdict
import json

NAMES = ("Time","Closure","Lang", "Math", "Chart",)


_empties = {
    "Math-14f": {"org.apache.commons.math3.optim.nonlinear.vector.Weight@<init>(double[])"},
    "Math-34f": {"org.apache.commons.math3.genetics.ListPopulation@iterator()"},
    "Math-58f": {"org.apache.commons.math.optimization.fitting.GaussianFitter@fit()"},
    "Math-70f": {"org.apache.commons.math.analysis.solvers.BisectionSolver@solve(org.apache.commons.math.analysis.UnivariateRealFunction,double,double,double)"},
    "Math-75f": {"org.apache.commons.math.stat.Frequency@getPct(java.lang.Object)"},
    "Math-104f": {"org.apache.commons.math.special.Gamma@regularizedGammaP(double,double)", "org.apache.commons.math.special.Gamma@regularizedGammaQ(double,double)"},
    "Lang-25f": {"org.apache.commons.lang3.text.translate.EntityArrays@ISO8859_1_ESCAPE()", "org.apache.commons.lang3.text.translate.EntityArrays@ISO8859_1_UNESCAPE()"},
    "Lang-29f": {"org.apache.commons.lang3.SystemUtils@toJavaVersionFloat(java.lang.String)"},
    "Lang-34f": {"org.apache.commons.lang3.builder.ToStringStyle@getRegistry()"},
    "Lang-57f": {"org.apache.commons.lang.LocaleUtils@isAvailableLocale(java.util.Locale)"},
    "Lang-64f": {"org.apache.commons.lang.enums.ValuedEnum@getValueInOtherClassLoader(java.lang.Object)"},
    "Chart-8f": {"org.jfree.data.time.Week@<init>(java.util.Date,java.util.TimeZone)"},
    "Closure-8f": {"com.google.javascript.jscomp.CollapseVariableDeclarations@isNamedParameter(com.google.javascript.jscomp.Scope.Var)"},
    "Closure-16f": {"com.google.javascript.jscomp.ScopedAliases$AliasedTypeNode@<init>(com.google.javascript.jscomp.ScopedAliases,com.google.javascript.rhino.Node,com.google.javascript.rhino.Node,java.lang.String)"},
    "Closure-26f": {"com.google.javascript.jscomp.ProcessCommonJSModules$ProcessCommonJsModulesCallback@<init>(com.google.javascript.jscomp.ProcessCommonJSModules)"},
    "Closure-27f": {"com.google.javascript.rhino.IR@blockUnchecked(com.google.javascript.rhino.Node)"},
    "Closure-146f": {"com.google.javascript.rhino.jstype.JSType@getTypesUnderInequality(com.google.javascript.rhino.jstype.JSType)"},
    "Time-11f": {"org.joda.time.tz.ZoneInfoCompiler$1@initialValue()"},
    "Closure-112f": {"com.google.javascript.jscomp.TypeInference$1@apply(com.google.javascript.rhino.jstype.TemplateType)"},
    "Closure-148f": {"com.google.javascript.jscomp.SourceMap$MappingTraversal@<init>(com.google.javascript.jscomp.SourceMap)"},
    "Closure-155f": {"com.google.javascript.jscomp.Scope@getTypeOfThis()", "com.google.javascript.jscomp.Scope$Arguments@hashCode()"},
    "Closure-162f": {"com.google.javascript.jscomp.Scope@getVarIterable()"},
    "Closure-158f": {"com.google.javascript.jscomp.CommandLineRunner$Flags$WarningGuardErrorOptionHandler@<init>(org.kohsuke.args4j.CmdLineParser,org.kohsuke.args4j.OptionDef,org.kohsuke.args4j.spi.Setter<?superjava.lang.String>)",
                     "com.google.javascript.jscomp.CommandLineRunner$Flags$WarningGuardWarningOptionHandler@<init>(org.kohsuke.args4j.CmdLineParser,org.kohsuke.args4j.OptionDef,org.kohsuke.args4j.spi.Setter<?superjava.lang.String>)",
                     "com.google.javascript.jscomp.CommandLineRunner$Flags$WarningGuardOffOptionHandler@<init>(org.kohsuke.args4j.CmdLineParser,org.kohsuke.args4j.OptionDef,org.kohsuke.args4j.spi.Setter<?superjava.lang.String>)",
                     "com.google.javascript.jscomp.CommandLineRunner$Flags$WarningGuardSetter@<init>(org.kohsuke.args4j.spi.Setter,com.google.javascript.jscomp.CheckLevel)",
                     "com.google.javascript.jscomp.CommandLineRunner$Flags$WarningGuardSetter@isMultiValued()",
                     "com.google.javascript.jscomp.CommandLineRunner$Flags$WarningGuardSetter@getType()"},
    "Closure-163f": {"com.google.javascript.jscomp.AnalyzePrototypeProperties$NameContext@<init>",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$LiteralProperty@getRootVar()",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$LiteralProperty@<init>(com.google.javascript.rhino.Node,com.google.javascript.rhino.Node,com.google.javascript.rhino.Node,com.google.javascript.rhino.Node,com.google.javascript.jscomp.Scope.Var,com.google.javascript.jscomp.JSModule)",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$AssignmentProperty@getRootVar()",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$GlobalFunction@getRootVar()",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$AssignmentProperty@<init>(com.google.javascript.rhino.Node,com.google.javascript.jscomp.Scope.Var,com.google.javascript.jscomp.JSModule)",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$GlobalFunction@<init>(com.google.javascript.jscomp.AnalyzePrototypeProperties,com.google.javascript.rhino.Node,com.google.javascript.jscomp.Scope.Var,com.google.javascript.jscomp.JSModule)",
                     "com.google.javascript.jscomp.Scope@getVarIterable()",
                     "com.google.javascript.jscomp.AnalyzePrototypeProperties$NameContext@<init>(com.google.javascript.jscomp.AnalyzePrototypeProperties,com.google.javascript.jscomp.AnalyzePrototypeProperties.NameInfo,com.google.javascript.jscomp.Scope)"},
    "Closure-165f": {"com.google.javascript.rhino.jstype.RecordType@isSynthetic()"},
    "Closure-169f": {"com.google.javascript.rhino.jstype.FunctionType@hasEqualCallType(com.google.javascript.rhino.jstype.FunctionType)",
                     "com.google.javascript.rhino.jstype.JSType@differsFrom(com.google.javascript.rhino.jstype.JSType)",
                     "com.google.javascript.rhino.jstype.JSType@isEquivalentTo(com.google.javascript.rhino.jstype.JSType)",
                     "com.google.javascript.rhino.jstype.JSType@isInvariant(com.google.javascript.rhino.jstype.JSType)"},
    "Closure-175f": {"com.google.javascript.jscomp.FunctionInjector$1@get()",
                     "com.google.javascript.jscomp.FunctionInjector$1@<init>(com.google.javascript.jscomp.FunctionInjector)",
                     "com.google.javascript.jscomp.FunctionInjector@access$200(com.google.javascript.jscomp.FunctionInjector,com.google.javascript.rhino.Node)",
                     "com.google.javascript.jscomp.FunctionInjector@access$100(com.google.javascript.jscomp.FunctionInjector)"}
}


def _load_mutants(mutant_file):
    l2m = defaultdict(set)
    l2l = defaultdict(lambda: defaultdict(set))
    cnt = 0

    with open(mutant_file, "r") as fh:
        for line in fh:
            cnt += 1
            line = line.strip()
            if line.count(":") != 6:
                if "24:00" in line:
                    line = line.replace("24:00", "24\\00")

            arguments = line.split(":")
            mid = int(arguments[0]) - 1
            method_name = arguments[4]
            line_no = int(arguments[5])

            line_key = method_name.split("@")[0]

            l2m[method_name].add(mid)
            l2l[line_key][line_no].add(mid)

        return l2m, l2l, cnt


def iterate_instance(name):
    global _empties
    total = 0
    excluded = 0
    no_fine_mutants = 0

    y = 0
    for x in patch.iterate_changes(name):
        bug_id, line_changes, method_changes = x
        total += 1

        mutant_file = os.path.join("suites", name, bug_id + "f", "mutants")
        if not os.path.exists(mutant_file):
            continue

        l2m, l2l, count = _load_mutants(mutant_file)

        suite_name = "-".join([name, bug_id + "f"])
        method_mutants = []
        line_mutants = []

        for method_name in method_changes:
            if method_name == "no_method":
                continue

            selected = l2m.get(method_name)
            if selected is None:
                if str(suite_name) not in _empties or method_name not in _empties[str(suite_name)]:
                    print("Should confirm that", method_name, "has no mutants in {}".format(suite_name))
            else:
                method_mutants.extend(selected)

        for key, lines in line_changes.items():
            l = l2l.get(key)
            if l is None:
                continue

            for line_no in lines:
                result = l.get(line_no)
                if result is not None:
                    line_mutants.extend(result)

        if len(method_mutants) == 0 or len(line_mutants) == 0:
            no_fine_mutants += 1
            continue

        yield bug_id, line_changes, method_changes, line_mutants, method_mutants, count,
    print("{}: {} no fine-level mutants".format(name, no_fine_mutants))