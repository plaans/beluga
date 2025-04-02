#! /usr/bin/env python3

import sys
import os

import unified_planning.shortcuts as up
import unified_planning.model.htn as up_htn

from unified_planning.model.expression import ConstantExpression
from unified_planning.plans.hierarchical_plan import HierarchicalPlan

from parser import *
from model import *

if __name__ == "__main__":

    output_folder = os.path.abspath(".") # os.path.abspath(sys.path[0])
    output_upp_path = os.path.join(output_folder, "problem/problem.upp")
    output_plan_path = os.path.join(output_folder, "plan/plan.json")

    rust_binary_path = os.path.abspath(".") # os.path.abspath(sys.path[0])

    if sys.argv[1] == "solve":
        #initial_state_filename = './separated_jsons/test_instance_init_state.json'
        #specifications_filename = './separated_jsons/test_instance_specifications.json'
        #test_pb_def = parse_specifications_and_initial_state(initial_state_filename, specifications_filename)

        full_problem_filename = sys.argv[2]
        test_pb_def = parse_problem_full(full_problem_filename)
        # print(test_pb_def)

        # # # # with fixed num of allowed_swaps # # # 
        # 
        # num_available_swaps = 3
        # test_beluga_model = BelugaModel(test_pb_def, full_problem_filename, num_available_swaps, None)
        # serialize_problem(test_beluga_model.pb, output_upp_path)
        # (test_plan, test_plan_as_json) = test_beluga_model.solve()

        # # # with growing num of allowed_swaps (until limit or sol found) # # # 
    
        num_available_swaps = 2
        while True:
            print('available swaps "spawned": {}'.format(num_available_swaps))
        
            test_beluga_model = BelugaModel(test_pb_def, full_problem_filename, num_available_swaps, None)
            (test_plan, test_plan_as_json) = test_beluga_model.solve()
        
            if test_plan is not None:
                break
            if num_available_swaps > 10: # FIXME TODO temporary
                break                    # FIXME TODO temporary
            num_available_swaps += 1

        assert (test_plan is None and test_plan_as_json is None) or (test_plan is not None and test_plan_as_json is not None)
        print(test_plan_as_json)

        if test_plan_as_json is not None:
            os.makedirs(os.path.dirname(output_plan_path), exist_ok=True)
            with open(output_plan_path, 'w', encoding='utf-8') as f:
                json.dump(test_plan_as_json, f, ensure_ascii=False, indent=4)
                sys.exit(0)
            assert False
        sys.exit(2)

    elif sys.argv[1] == "explain":
        #initial_state_filename = './separated_jsons/test_instance_init_state.json'
        #specifications_filename = './separated_jsons/test_instance_specifications.json'
        #test_pb_def = parse_specifications_and_initial_state(initial_state_filename, specifications_filename)

        # # # with fixed num of allowed_swaps # # # 

        full_problem_filename = sys.argv[2]
        test_pb_def = parse_problem_full(full_problem_filename)
        # print(test_pb_def)

        num_available_swaps = 3
        test_beluga_model = BelugaModel(test_pb_def, full_problem_filename, num_available_swaps, None)
        serialize_problem(test_beluga_model.pb, output_upp_path)

        import subprocess
#        popen = subprocess.Popen((os.path.join(os.path.abspath(sys.path[0]), "beluga_rust"), "solve", output_upp_path), stdout=subprocess.PIPE)
        popen = subprocess.Popen((os.path.join(os.path.abspath(sys.path[0]), "beluga_rust"), "explain", output_upp_path, "WHY_INFEASIBLE"), stdout=subprocess.PIPE)
        popen.wait()
        output = popen.stdout.read() # type: ignore
        print(output)

        

        print("SUBCOMMAND {} NOT COMPLETELY IMPLEMENTED !".format(sys.argv[1]))

    else:
        print("UNKNOWN (OR NOT YET IMPLEMENTED) SUBCOMMAND {}".format(sys.argv[1]))
