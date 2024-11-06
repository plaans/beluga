from unified_planning.shortcuts import *
from unified_planning.model.htn import *

import sys

from parser import *


def serialize(pb: Problem, filename: str):
    from unified_planning.grpc.proto_writer import ProtobufWriter
    writer = ProtobufWriter()
    msg = writer.convert(pb)
    with open(filename, "wb") as file:
        file.write(msg.SerializeToString())

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

def solve(pb: Problem):
    with OneshotPlanner(name="aries") as planner:
        result = planner.solve(pb, output_stream=sys.stdout)
        plan = result.plan
        print(result)


def convert(instance: BelugaProblemDef, name: str) -> Problem:
    num_trucks_beluga = len(instance.trailers_beluga)
    num_trucks_production = len(instance.trailers_factory)


    p = HierarchicalProblem(name)
    
    side_type = UserType("Side")
    beluga_side = p.add_object("beluga_side", side_type)
    production_side = p.add_object("production_side", side_type)
    opposite = p.add_fluent("opposite", side_type, s=side_type)
    p.set_initial_value(opposite(beluga_side), production_side)
    p.set_initial_value(opposite(production_side), beluga_side)

    jig_type = UserType("JigType")
    jig_types = {}
    for jt in instance.jig_types:
        sub_type = UserType(jt.name, jig_type)
        jig_types[jt.name] = sub_type
        
    size = p.add_fluent("size", IntType(), part=jig_type)
    # size_empty = p.add_fluent("size_empty", IntType(), part=jig_type)
    # size_loaded = p.add_fluent("size_loaded", IntType(), part=jig_type)

    part_location_type = UserType("PartLoc")
    buffer_type = UserType("Buffer", part_location_type)
    rack_type = UserType("Rack", father=buffer_type)
    hangar_type = UserType("Hangar", father=buffer_type)
    free = p.add_fluent("free_space", IntType(lower_bound=0, upper_bound=1000), r=buffer_type)

    next = Fluent("next", IntType(), r=buffer_type, s=side_type)
    p.add_fluent(next, default_initial_value=0)
    at = p.add_fluent("at", part_location_type, p=jig_type)
    pos = p.add_fluent("pos", IntType(), p=jig_type, s=side_type)


    
    belugas = {}
    for beluga in instance.flights:
        b = p.add_object(beluga.name, buffer_type)
        p.set_initial_value(free(b), 500)  # leave space
        belugas[beluga.name] = b

    hangars = {}
    for hangar in instance.hangars:
        h = p.add_object(hangar, hangar_type)
        p.set_initial_value(free(h), 500)  # leave space
        hangars[hangar] = h

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

    for trailer in instance.trailers_beluga:
        truck = p.add_object(trailer, truck_type)
        p.set_initial_value(truck_side(truck), beluga_side)
    for trailer in instance.trailers_factory:
        truck = p.add_object(trailer, truck_type)
        p.set_initial_value(truck_side(truck), production_side)

    s = DurativeAction("swap", p=jig_type, r1=buffer_type, r2=buffer_type, truck=truck_type, side=side_type, oside=side_type)
    s.set_closed_duration_interval(1, 1000)
    # ensure that p is the next part on r1
    s.add_condition(StartTiming(), Equals(at(s.p), s.r1))
    s.add_condition(StartTiming(), Equals(next(s.r1, s.side), pos(s.p, s.side)))
    s.add_condition(StartTiming(), Equals(opposite(s.side), s.oside))
    s.add_condition(StartTiming(), Equals(truck_side(s.truck), s.side))
    
    # unclear whether this is useful
    # # do not add to beluga or remove from production
    # for beluga in instance.flights:
    #     s.add_condition(StartTiming(), Not(Equals(s.r2, p.object(beluga.name))))
    # for pline in instance.production_lines:
    #     s.add_condition(StartTiming(), Not(Equals(s.r1, p.object(pline.name))))

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

    for jig in instance.jigs:
        part_obj = p.add_object(jig.name, jig_types[jig.type])
        tpe = instance.get_jig_type(jig.type)
        if jig.empty:
            p.set_initial_value(size(part_obj), tpe.size_empty)
        else:
            p.set_initial_value(size(part_obj), tpe.size_loaded)


    for rack in instance.racks:
        r = p.add_object(rack.name, rack_type)
        

        num_pieces = len(rack.jigs)
        occupied_space = 0
        for i, jig_name in enumerate(rack.jigs):
            jig = instance.get_jig(jig_name)
            instance_jig_type = instance.get_jig_type(jig.type)
            jig_size = instance_jig_type.size_empty if jig.empty else instance_jig_type.size_loaded
            occupied_space += jig_size
            jig = p.object(jig_name)
            p.set_initial_value(pos(jig, beluga_side), i)
            p.set_initial_value(pos(jig, production_side), num_pieces - i)
            p.set_initial_value(at(jig), r)
        p.set_initial_value(free(r), rack.size - occupied_space)
        p.set_initial_value(next(r, production_side), num_pieces)

    proceed_to_next = InstantaneousAction("proceed_to_next_beluga")
    p.add_action(proceed_to_next)

    epochs = []
    for i in range(len(instance.flights)+2):
        t = p.task_network.add_subtask(proceed_to_next)
        epochs.append(t)
        if i > 0:
            p.task_network.add_constraint(LT(epochs[i-1].end, t.start))

    def add_unloading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)

        p.set_initial_value(next(beluga, beluga_side), len(flight.incoming) )
        
        prev = None
        for i, jig_name in enumerate(flight.incoming):
            jig = p.object(jig_name)
            p.set_initial_value(pos(jig, beluga_side), i + 1)
            p.set_initial_value(at(jig), beluga)

            # add task to unload from beluga
            r = p.task_network.add_variable(f"r_{jig_name}_1", rack_type)
            truck = p.task_network.add_variable(f"t_{jig_name}_1", truck_type)
            t = p.task_network.add_subtask(s, jig, beluga, r, truck, beluga_side, production_side)
            
            p.task_network.add_constraint(LT(epochs[flight_number].end, t.start))
            p.task_network.add_constraint(LT(t.end, epochs[flight_number+1].start))

            if prev is not None:
                p.task_network.add_constraint(LT(t.start, prev.start))
            prev = t

    
    def add_loading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)
        
        prev = None
        for i, jig_type_name in enumerate(flight.outgoing):
            jig_type = jig_types[jig_type_name]
            
            # add task to unload from beluga
            jig = p.task_network.add_variable(f"jig_{flight.name}_{i}", jig_type)
            r = p.task_network.add_variable(f"r_{flight.name}_{i}", rack_type)
            truck = p.task_network.add_variable(f"t_{flight.name}_{i}", truck_type)
            t = p.task_network.add_subtask(s, jig, r, beluga, truck, beluga_side, production_side)
            
            p.task_network.add_constraint(LT(epochs[flight_number+1].end, t.start))
            p.task_network.add_constraint(LT(t.end, epochs[flight_number+2].start))

            if prev is not None:
                p.task_network.add_constraint(LT(t.start, prev.start))
            prev = t

    for i in range(len(instance.flights)):
        add_unloading(i)
        add_loading(i)
    

    for pline in instance.production_lines:
        
        pline_obj = p.object(pline.name)
        prev = None
        for i, jig_name in enumerate(pline.schedule):
            jig = p.object(jig_name)
            # p.add_goal(Equals(at(part_obj), pline_obj))
            # p.add_goal(Equals(pos(part_obj, production_side), i +1))

            # add task to load to production line
            r = p.task_network.add_variable(f"r_{jig_name}_2", rack_type)
            truck = p.task_network.add_variable(f"t_{jig_name}_2", truck_type)
            hangar = p.task_network.add_variable(f"h_{jig_name}_2", hangar_type)
            t_load = p.task_network.add_subtask(s, jig, r, hangar, truck, production_side, beluga_side)
            
            # add task to retrieve empty jig from hangar
            r = p.task_network.add_variable(f"r_return_{jig_name}_2", rack_type)
            truck = p.task_network.add_variable(f"t_return_{jig_name}_2", truck_type)
            t_return = p.task_network.add_subtask(s, jig, hangar, r, truck, production_side, beluga_side)
            
            p.task_network.add_constraint(LT(t_load.end, t_return.start))

            if prev is not None:
                p.task_network.add_constraint(LT(prev.end, t_load.end))
            prev = t_load
        
        
            
    
    # # add task to allow an arbitrary number of swaps between racks
    # do_swaps = p.add_task("do_swaps")
    # m1 = Method("m-noop")
    # m1.set_task(do_swaps)
    # p.add_method(m1)

    # m2 = Method("m-do-rec", p=jig_type, r1=rack_type, r2=rack_type, t=truck_type, side=side_type, oside=side_type)
    # m2.set_task(do_swaps)
    # swap_subtask = m2.add_subtask(s, m2.p, m2.r1, m2.r2, m2.t, m2.side, m2.oside)
    # rec_subtask = m2.add_subtask(do_swaps)
    # m2.set_ordered(swap_subtask, rec_subtask)
    # p.add_method(m2)

    # p.task_network.add_subtask(do_swaps)



    return p


if __name__ == "__main__":
    file = 'instances/problem_j4_r3_oc50_f4_s0_3_.json'
    # file = 'instances/problem_j9_r3_oc50_f8_s0_15_.json'
    # file = 'instances/problem_j12_r3_oc50_f7_s0_13_.json'
    # file = 'instances/problem_j16_r10_oc50_f4_s0_46_.json'
    pb = parse_file(file)
    print(pb)
    up = convert(pb, file)
    print(up)
    serialize(up, "/tmp/beluga.upp")
    solve(up)

