#! /usr/bin/env python3

import sys
import os

from parser import *
from model import *

if __name__ == "__main__":

    output_folder = os.path.abspath(".") # os.path.abspath(sys.path[0])
    output_upp_path = os.path.join(output_folder, "problem/problem.upp")
    output_plan_path = os.path.join(output_folder, "plan/plan.json")
    output_confls_path = os.path.join(output_folder, "conflicts/conflicts.json")

    rust_binary_path = os.path.abspath(".") # os.path.abspath(sys.path[0])

    if sys.argv[1] == "solve":

        base_filename = sys.argv[2]
        props_filename = sys.argv[3]
        test_pb_def = parse_problem_and_properties(base_filename, props_filename)
        print(test_pb_def)
        # full_problem_filename = sys.argv[2]
        # test_pb_def = parse_problem_full(full_problem_filename)
        # print(test_pb_def)

        # # # with fixed num of allowed_swaps # # # 
        """
        num_available_swaps = 0
        test_beluga_model = BelugaModelOptSched(test_pb_def, base_filename+"_"+props_filename, num_available_swaps, None)
        
        serialize_problem(test_beluga_model.pb, output_upp_path)
        (test_plan, test_plan_as_json) = test_beluga_model.solve_with_properties(list(test_beluga_model.properties.keys()))
        """
        # import subprocess
        # popen = subprocess.Popen(
        #     (
        #         os.path.join(os.path.abspath(sys.path[0]), "beluga_rust"),
        #         "solve",
        #         output_upp_path,
        #     ),
        #     stdout=subprocess.PIPE,
        # )
        # popen.wait()
        # output = popen.stdout.read() # type: ignore
        # print(output)
        
        # # # with growing num of allowed_swaps (until limit or sol found) # # # 
    
        """ max_num_available_swaps = int(os.environ.get('MAX_NUM_AVAILABLE_SWAPS', 10))
        num_available_swaps = 0
        while True:
            print('available swaps "spawned": {}'.format(num_available_swaps))
        
            test_beluga_model = BelugaModelOptSched(test_pb_def, base_filename+"_"+props_filename, num_available_swaps, None)

            (test_plan, test_plan_as_json) = test_beluga_model.solve_with_properties(list(test_beluga_model.properties.keys()))
        
            if test_plan is not None:
                break
            num_available_swaps += 1
            if num_available_swaps >= max_num_available_swaps:   # FIXME TODO temporary ?
                sys.exit(2)                                      # FIXME TODO temporary ?
         """
        # # # ALT: with growing num of allowed_swaps (until limit or sol found) # # # 
    
        num_available_swaps = int(os.environ.get('MAX_NUM_AVAILABLE_SWAPS', 10))
        test_beluga_model = BelugaModelOptSched(test_pb_def, base_filename+"_"+props_filename, num_available_swaps, None)
        serialize_problem(test_beluga_model.pb, output_upp_path)

        n = 0
        while True:
            print('swaps "spawned": {} swaps allowed: {}'.format(num_available_swaps, n))
        
            (test_plan, test_plan_as_json) = test_beluga_model.solve_with_properties(
                list(test_beluga_model.properties.keys()),
                n
            )
        
            if test_plan is not None:
                break
            n += 1
            if n > num_available_swaps:   # FIXME TODO temporary ?
                sys.exit(2)                # FIXME TODO temporary ?

        assert (test_plan is None and test_plan_as_json is None) or (test_plan is not None and test_plan_as_json is not None)
        print(test_plan_as_json)

        if test_plan_as_json is not None:
            os.makedirs(os.path.dirname(output_plan_path), exist_ok=True)
            with open(output_plan_path, 'w', encoding='utf-8') as f:
                json.dump(test_plan_as_json, f, ensure_ascii=False, indent=4)
                sys.exit(0)
        assert False


    elif sys.argv[1] == "explain":

        base_filename = sys.argv[2]
        props_filename = sys.argv[3]
        props_filename = sys.argv[3]
        test_pb_def = parse_problem_and_properties(base_filename, props_filename)
        print(test_pb_def)
        # full_problem_filename = sys.argv[2]
        # test_pb_def = parse_problem_full(full_problem_filename)
        # print(test_pb_def)

        num_available_swaps = int(os.environ.get('MAX_NUM_AVAILABLE_SWAPS', 10))
        test_beluga_model = BelugaModelOptSched(test_pb_def, base_filename+"_"+props_filename, num_available_swaps, None)
        serialize_problem(test_beluga_model.pb, output_upp_path)        

        import subprocess
        popen = subprocess.Popen(
            (
                os.path.join(os.path.abspath(sys.path[0]), "beluga_rust"),
                "explain",
                output_upp_path,
                output_confls_path,
            ),
            stdout=subprocess.PIPE,
        )
        popen.wait()
        # output = popen.stdout.read() # type: ignore
        # print(output)

        sys.exit(0)

    else:
        print("UNKNOWN (OR NOT YET IMPLEMENTED) SUBCOMMAND {}".format(sys.argv[1]))
