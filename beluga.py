#! /usr/bin/env python3

import sys
import os

from parser import *
from model import *
from checker import *

if __name__ == "__main__":

    dir_name = os.path.abspath(os.getcwd())

    output_folder = os.path.join(dir_name, "output")
    output_upp_path = os.path.join(output_folder, "problem/problem.upp")
    output_plan_path = os.path.join(output_folder, "plan/plan.json")
    output_sat_props_path = os.path.join(output_folder, "sat_props/sat_props.json")
    output_confls_path = os.path.join(output_folder, "conflicts/conflicts.json")

    if sys.argv[1] == "solve":

        num_available_swaps = int(sys.argv[2])

        base_filename = sys.argv[3]
        props_filename = sys.argv[4]
        test_pb_def = parse_problem_and_properties(base_filename, props_filename)
        print(test_pb_def)
    
        test_beluga_model = BelugaModelOptSched(test_pb_def, base_filename+"_"+props_filename, num_available_swaps, None)
        serialize_problem(test_beluga_model.pb, output_upp_path)

        num_at_most_considered_swaps = min(
            [num_available_swaps]
            + [m for (_, m) in test_pb_def.props_num_swaps_used_leq]
        )

        n = 0
        while True:
            print('total swaps available: {},' \
                  'max swaps to consider: {},' \
                  'swaps allowed on this run: {} '.format(
                      num_available_swaps,
                      num_at_most_considered_swaps,
                      n,
                  )
            )
        
            (test_plan, test_plan_as_json) = test_beluga_model.solve_with_properties(
                list(test_beluga_model.properties.keys()),
                n
            )
        
            if test_plan is not None:
                break
            n += 1
            if n > num_at_most_considered_swaps:
                sys.exit(2)

        assert (test_plan is None and test_plan_as_json is None) or (test_plan is not None and test_plan_as_json is not None)
        print(test_plan_as_json)

        if test_plan_as_json is not None:
            os.makedirs(os.path.dirname(output_plan_path), exist_ok=True)
            with open(output_plan_path, 'w', encoding='utf-8') as f:
                json.dump(test_plan_as_json, f, ensure_ascii=False, indent=4)

                sys.exit(0)

        assert False

    elif sys.argv[1] == "explain":

        num_available_swaps = int(sys.argv[2])

        base_filename = sys.argv[3]
        props_filename = sys.argv[4]
        test_pb_def = parse_problem_and_properties(base_filename, props_filename)
        print(test_pb_def)

        props_ids_hard_list = [] if len(sys.argv) < 6 else list(map(PropId, sys.argv[5].strip('[]').replace(" ","").split(',')))
        test_pb_def.props_ids_hard_list = props_ids_hard_list
        print(test_pb_def.props_ids_hard_list)

        test_beluga_model = BelugaModelOptSched(test_pb_def, base_filename+"_"+props_filename, num_available_swaps, None)
        serialize_problem(test_beluga_model.pb, output_upp_path)        

        import subprocess

        call_cargo_run_rather_than_compiled_bin = False
        if call_cargo_run_rather_than_compiled_bin:
            popen = subprocess.Popen(
                (
                    "cargo",
                    "run",
                    "--bin",
                    "beluga",
                    "--release",
                    "explain",
                    output_upp_path,
                    output_confls_path,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.join(os.path.abspath(os.path.dirname(__file__)), "aries-beluga"),
            )
        else:
            popen = subprocess.Popen(
                (
                    os.path.abspath(os.path.dirname(__file__))+"/beluga_rust",
                    "explain",
                    output_upp_path,
                    output_confls_path,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.abspath(os.path.dirname(__file__)),
            )

        while True:
            out = popen.stdout.readline().rstrip() # type: ignore
            if popen.poll() is not None:
                break
            if out:
                print(out.decode('utf-8'))
        # popen.poll()
        popen.wait()

        with open(output_confls_path, 'r') as f:
            conflicts_data = json.load(f)
            print(conflicts_data)

        sys.exit(0)

    elif sys.argv[1] == "check-props":

        base_filename = sys.argv[2]
        props_filename = sys.argv[3]
        plan_filename = sys.argv[4]

        test_pb_def = parse_problem_and_properties(base_filename, props_filename)
        # print(test_pb_def)
        test_plan_def = parse_plan(plan_filename)
        assert test_plan_def is not None
        # print(test_plan_def)

        d = json.load(open(props_filename))
        properties = { entry["_id"]: entry["definition"] for entry in d }

        satisfied_properties = check_plan_properties(
            properties,
            test_plan_def,
            [ fl.name for fl in test_pb_def.flights ],
            { j.name: j.type for j in test_pb_def.jigs },
            { r.name: r.jigs for r in test_pb_def.racks },
            { r.name: r.size for r in test_pb_def.racks },
        )

        for prop_id in satisfied_properties:
            print(prop_id)

        os.makedirs(os.path.dirname(output_sat_props_path), exist_ok=True)
        with open(output_sat_props_path, 'w', encoding='utf-8') as f:
            json.dump([prop_id for prop_id in satisfied_properties], f, ensure_ascii=False, indent=4)

            sys.exit(0)
        
        assert False

    else:
        print("UNKNOWN (OR NOT YET IMPLEMENTED) SUBCOMMAND {}".format(sys.argv[1]))
