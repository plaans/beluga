from unified_planning.shortcuts import *
from unified_planning.model.htn import *

import sys

from parser import *


# def serialize(pb: Problem, filename: str):
#     from unified_planning.grpc.proto_writer import ProtobufWriter
#     writer = ProtobufWriter()
#     msg = writer.convert(pb)
#     with open(filename, "wb") as file:
#         file.write(msg.SerializeToString())

# def deserialize(filename: str) -> Problem:
#     from unified_planning.grpc.proto_reader import ProtobufReader
#     import unified_planning.grpc.generated.unified_planning_pb2 as proto  

#     with open(filename, "rb") as file:
#         content = file.read()
#         pb_msg = proto.Problem()
#         pb_msg.ParseFromString(content)
#     reader = ProtobufReader()
#     problem = reader.convert(pb_msg)
#     return problem

# def solve(pb: Problem):
#     with OneshotPlanner(name="aries") as planner:
#         result = planner.solve(pb, output_stream=sys.stdout)
#         plan = result.plan
#         print(result)


def convert(instance: BelugaProblemDef, name: str) -> Problem:
    num_trucks_beluga = 1
    num_trucks_production = 2


    p = HierarchicalProblem(name)
    
    side_type = UserType("Side")
    beluga_side = p.add_object("beluga_side", side_type)
    production_side = p.add_object("production_side", side_type)
    opposite = p.add_fluent("opposite", side_type, s=side_type)
    p.set_initial_value(opposite(beluga_side), production_side)
    p.set_initial_value(opposite(production_side), beluga_side)

    part_type = UserType("Part")
    size = p.add_fluent("size", IntType(), part=part_type)

    part_location_type = UserType("PartLoc")
    buffer_type = UserType("Buffer", part_location_type)
    rack_type = UserType("Rack", father=buffer_type)
    free = p.add_fluent("free_space", IntType(lower_bound=0, upper_bound=1000), r=buffer_type)
    
    beluga = p.add_object("beluga", buffer_type)
    p.set_initial_value(free(beluga), 0)

    for pline in instance.production_lines:
        pline_obj = p.add_object(pline.name, buffer_type)
        p.set_initial_value(free(pline_obj), 1000)

    truck_type = UserType("Truck", part_location_type)
    available = Fluent("available", BoolType(), t=truck_type)
    p.add_fluent(available, default_initial_value=True)
    truck_side = p.add_fluent("truck_side", side_type, truck=truck_type)

    free_trucks = p.add_fluent("free_trucks", IntType(0,max(num_trucks_beluga, num_trucks_production)), side=side_type)
    p.set_initial_value(free_trucks(beluga_side), num_trucks_beluga)
    p.set_initial_value(free_trucks(production_side), num_trucks_production)

    for i in range(num_trucks_beluga):
        truck = p.add_object(f"tb{i}", truck_type)
        p.set_initial_value(truck_side(truck), beluga_side)
    for i in range(num_trucks_production):
        truck = p.add_object(f"tp{i}", truck_type)
        p.set_initial_value(truck_side(truck), production_side)


    next = Fluent("next", IntType(), r=buffer_type, s=side_type)
    p.add_fluent(next, default_initial_value=0)
    at = p.add_fluent("at", part_location_type, p=part_type)
    pos = p.add_fluent("pos", IntType(), p=part_type, s=side_type)

    s = DurativeAction("swap", p=part_type, r1=buffer_type, r2=buffer_type, truck=truck_type, side=side_type, oside=side_type)
    s.set_closed_duration_interval(1, 1000)
    # ensure that p is the next part on r1
    s.add_condition(StartTiming(), Equals(at(s.p), s.r1))
    s.add_condition(StartTiming(), Equals(next(s.r1, s.side), pos(s.p, s.side)))
    s.add_condition(StartTiming(), Equals(opposite(s.side), s.oside))
    s.add_condition(StartTiming(), Equals(truck_side(s.truck), s.side))
    

    # do not add to beluga or remove from production
    s.add_condition(StartTiming(), Not(Equals(s.r2, beluga)))
    for pline in instance.production_lines:
        s.add_condition(StartTiming(), Not(Equals(s.r1, p.object(pline.name))))

    s.add_increase_effect(StartTiming(), free(s.r1), size(s.p))
    s.add_decrease_effect(EndTiming(), free(s.r2), size(s.p))
    s.add_decrease_effect(StartTiming(), next(s.r1, s.side), 1)
    s.add_increase_effect(EndTiming(), next(s.r2, s.side), 1)

    # truck resource management
    s.add_decrease_effect(StartTiming(), free_trucks(s.side), 1)
    s.add_increase_effect(EndTiming(), free_trucks(s.side), 1)
    s.add_effect(StartTiming(), at(s.p), s.truck)
    # the conditions/effects below are only necessary to be able to name the truck but resource managament with free_trucks should be sufficent
    s.add_condition(StartTiming(), available(s.truck))
    s.add_effect(StartTiming(), available(s.truck), False)
    s.add_effect(EndTiming(), available(s.truck), True)

    s.add_effect(EndTiming(), at(s.p), s.r2)
    s.add_effect(EndTiming(), pos(s.p, s.side), next(s.r2, s.side) + 1)
    s.add_effect(EndTiming(), pos(s.p, s.oside), -next(s.r2, s.side))

    p.add_action(s)

    for rack in instance.racks:
        r = p.add_object(rack.name, rack_type)
        p.set_initial_value(free(r), rack.size)

    for part in instance.parts:
        part_obj = p.add_object(part.name, part_type)
        p.set_initial_value(size(part_obj), part.size)

    p.set_initial_value(next(beluga, beluga_side), len(instance.arrivals) )
    
    prev = None
    for i, part in enumerate(instance.arrivals):
        part_obj = p.object(part.name)
        p.set_initial_value(pos(part_obj, beluga_side), i + 1)
        p.set_initial_value(at(part_obj), beluga)

        # add task to unload from beluga
        r = p.task_network.add_variable(f"r_{part.name}_1", rack_type)
        truck = p.task_network.add_variable(f"t_{part.name}_1", truck_type)
        t = p.task_network.add_subtask(s, part_obj, beluga, r, truck, beluga_side, production_side)
        
        if prev is not None:
            p.task_network.add_constraint(LT(t.start, prev.start))
        prev = t

    

    for pline in instance.production_lines:
        
        pline_obj = p.object(pline.name)
        prev = None
        for i, part in enumerate(pline.schedule):
            part_obj = p.object(part.name)
            p.add_goal(Equals(at(part_obj), pline_obj))
            p.add_goal(Equals(pos(part_obj, production_side), i +1))

            # add task to load to production line
            r = p.task_network.add_variable(f"r_{part.name}_2", rack_type)
            truck = p.task_network.add_variable(f"t_{part.name}_2", truck_type)
            t = p.task_network.add_subtask(s, part_obj, r, pline_obj, truck, production_side, beluga_side)
            
            if prev is not None:
                p.task_network.add_constraint(LT(prev.end, t.end))
            prev = t
        
        
            
    
    # add task to allow an arbitrary number of swaps between racks
    do_swaps = p.add_task("do_swaps")
    m1 = Method("m-noop")
    m1.set_task(do_swaps)
    p.add_method(m1)

    m2 = Method("m-do-rec", p=part_type, r1=rack_type, r2=rack_type, t=truck_type, side=side_type, oside=side_type)
    m2.set_task(do_swaps)
    swap_subtask = m2.add_subtask(s, m2.p, m2.r1, m2.r2, m2.t, m2.side, m2.oside)
    rec_subtask = m2.add_subtask(do_swaps)
    m2.set_ordered(swap_subtask, rec_subtask)
    p.add_method(m2)

    p.task_network.add_subtask(do_swaps)



    return p


if __name__ == "__main__":
    file = 'instances/problem_j4_r3_oc50_f4_s0_3_.json'
    pb = parse_file(file)
    print(pb)
    convert(pb, file)