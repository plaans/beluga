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
        result = planner.solve(pb, output_stream=sys.stdout) # type: ignore
        plan = result.plan
        print(result)


def convert(instance: BelugaProblemDef, name: str) -> Problem:

    p = HierarchicalProblem(name)

    # # #

    num_trailers_beluga = len(instance.trailers_beluga)
    num_trailers_production = len(instance.trailers_factory)

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
    beluga_type = UserType("Beluga", part_location_type)
    rack_type = UserType("Rack", father=part_location_type)
    hangar_type = UserType("Hangar", father=part_location_type)
    production_line_type = UserType("ProductionLine", part_location_type)
    free = p.add_fluent("free_space", IntType(lower_bound=0, upper_bound=1000), r=rack_type)
    free_hangar = p.add_fluent("free_hangar", BoolType(), h=hangar_type)

    next = Fluent("next", IntType(), r=rack_type, s=side_type)
    p.add_fluent(next, default_initial_value=0)
    at = p.add_fluent("at", part_location_type, p=jig_type)
    pos = p.add_fluent("pos", IntType(), p=jig_type, s=side_type)

    belugas = {}
    for beluga in instance.flights:
        b = p.add_object(beluga.name, beluga_type)
        belugas[beluga.name] = b

    hangars = {}
    for hangar in instance.hangars:
        h = p.add_object(hangar, hangar_type)
        p.set_initial_value(free_hangar(h), True)
        hangars[hangar] = h

    for pline in instance.production_lines:
        pline_obj = p.add_object(pline.name, production_line_type)

    trailer_type = UserType("Trailer", part_location_type)
    available = Fluent("available", BoolType(), t=trailer_type)
    p.add_fluent(available, default_initial_value=True)
    trailer_side = p.add_fluent("trailer_side", side_type, trailer=trailer_type)

    free_trailers = p.add_fluent("free_trailers", IntType(0,max(num_trailers_beluga, num_trailers_production)), side=side_type)
    p.set_initial_value(free_trailers(beluga_side), num_trailers_beluga)
    p.set_initial_value(free_trailers(production_side), num_trailers_production)

    for trailer in instance.trailers_beluga:
        trailer = p.add_object(trailer, trailer_type)
        p.set_initial_value(trailer_side(trailer), beluga_side)
    for trailer in instance.trailers_factory:
        trailer = p.add_object(trailer, trailer_type)
        p.set_initial_value(trailer_side(trailer), production_side)

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

    # # #

    def load_to_trailer(a: DurativeAction, jig, trailer, side):
        a.add_condition(StartTiming(), Equals(trailer_side(trailer), side))
        a.add_decrease_effect(StartTiming(), free_trailers(side), 1)
        a.add_effect(StartTiming(), at(jig), trailer)
        a.add_condition(StartTiming(), available(trailer))
        a.add_effect(StartTiming(), available(trailer), False)

    def unload_from_trailer(a: DurativeAction, jig, trailer, side):
        a.add_condition(StartTiming(), Equals(trailer_side(trailer), side))
        a.add_increase_effect(EndTiming(), free_trailers(side), 1)
        a.add_effect(EndTiming(), available(trailer), True)

    def to_rack(a: DurativeAction, jig, rack, trailer, side, oside):
        unload_from_trailer(a, jig, trailer, side)
        a.add_decrease_effect(EndTiming(), free(rack), size(jig))
        a.add_increase_effect(EndTiming(), next(rack, side), 1)

        a.add_effect(EndTiming(), at(jig), rack)
        a.add_effect(EndTiming(), pos(jig, side), next(rack, side) + 1)
        a.add_effect(EndTiming(), pos(jig, oside), -next(rack, side))

    def from_rack(a: DurativeAction, jig, rack, trailer, side, oside):
        a.add_condition(StartTiming(), Equals(at(jig), rack))
        a.add_condition(StartTiming(), Equals(next(rack, side), pos(jig, side)))
        a.add_increase_effect(StartTiming(), free(rack), size(jig))
        a.add_decrease_effect(StartTiming(), next(rack, side), 1)
        load_to_trailer(a, jig, trailer, side)

    unload = DurativeAction("unload", jig=jig_type, beluga=beluga_type, rack=rack_type, trailer=trailer_type)
    unload.set_closed_duration_interval(1, 1000)
    to_rack(unload, unload.jig, unload.rack, unload.trailer, beluga_side, production_side)
    load_to_trailer(unload, unload.jig, unload.trailer, beluga_side)
    p.add_action(unload)

    load = DurativeAction("load", jig=jig_type, beluga=beluga_type, rack=rack_type, trailer=trailer_type)
    load.set_closed_duration_interval(1, 1000)
    from_rack(load, load.jig, load.rack, load.trailer, beluga_side, production_side)
    unload_from_trailer(load, load.jig, load.trailer, beluga_side)
    p.add_action(load)

    send_prod = DurativeAction("send-prod", jig=jig_type, prod_line=production_line_type, rack=rack_type, hangar=hangar_type, trailer=trailer_type)
    send_prod.set_closed_duration_interval(1, 1000)
    send_prod.add_condition(EndTiming(), free_hangar(send_prod.hangar))
    send_prod.add_effect(EndTiming(), free_hangar(send_prod.hangar), False)
    from_rack(send_prod, send_prod.jig, send_prod.rack, send_prod.trailer, production_side, beluga_side)
    unload_from_trailer(send_prod, send_prod.jig, send_prod.trailer, production_side)
    p.add_action(send_prod)

    retrieve_prod = DurativeAction("retrieve-prod", jig=jig_type, prod_line=production_line_type, rack=rack_type, hangar=hangar_type, trailer=trailer_type)
    retrieve_prod.set_closed_duration_interval(1, 1000)
    retrieve_prod.add_effect(StartTiming(), free_hangar(retrieve_prod.hangar), True)
    to_rack(retrieve_prod, retrieve_prod.jig, retrieve_prod.rack, retrieve_prod.trailer, production_side, beluga_side)
    load_to_trailer(retrieve_prod, retrieve_prod.jig, retrieve_prod.trailer, production_side)
    p.add_action(retrieve_prod)

    proceed_to_next = InstantaneousAction("proceed_to_next_beluga")
    p.add_action(proceed_to_next)

    # # #

    swap = DurativeAction("swap", p=jig_type, r1=rack_type, r2=rack_type, trailer=trailer_type, side=side_type, oside=side_type)
    swap.set_closed_duration_interval(1, 1000)
    swap.add_condition(StartTiming(), Equals(opposite(swap.side), swap.oside))
    from_rack(swap, swap.p, swap.r1, swap.trailer, swap.side, swap.oside)
    to_rack(swap, swap.p, swap.r2, swap.trailer, swap.side, swap.oside)
    p.add_action(swap)

    # add task to allow an arbitrary number of swaps between racks
    do_swaps = p.add_task("do_swaps")
    m1 = Method("m-noop")
    m1.set_task(do_swaps)
    p.add_method(m1)

    m2 = Method("m-do-rec", p=jig_type, r1=rack_type, r2=rack_type, t=trailer_type, side=side_type, oside=side_type)
    m2.set_task(do_swaps)
    swap_subtask = m2.add_subtask(swap, m2.p, m2.r1, m2.r2, m2.t, m2.side, m2.oside)
    rec_subtask = m2.add_subtask(do_swaps)
    m2.set_ordered(swap_subtask, rec_subtask)
    p.add_method(m2)

    p.task_network.add_subtask(do_swaps)

    # # #

    epochs = []
    for i in range(len(instance.flights)+2):
        t = p.task_network.add_subtask(proceed_to_next)
        epochs.append(t)
        if i > 0:
            p.task_network.add_constraint(LT(epochs[i-1].end, t.start))

    def add_unloading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)

        prev = None
        for i, jig_name in enumerate(flight.incoming):
            jig = p.object(jig_name)

            # add task to unload from beluga
            r = p.task_network.add_variable(f"r_{jig_name}_1", rack_type)
            trailer = p.task_network.add_variable(f"t_{jig_name}_1", trailer_type)
            t = p.task_network.add_subtask(unload, jig, beluga, r, trailer)
            
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
            
            # add task to load to beluga
            jig = p.task_network.add_variable(f"jig_{flight.name}_{i}", jig_type)
            r = p.task_network.add_variable(f"r_{flight.name}_{i}", rack_type)
            trailer = p.task_network.add_variable(f"t_{flight.name}_{i}", trailer_type)
            t = p.task_network.add_subtask(load, jig, beluga, r, trailer)
            
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
            #  send_prod = DurativeAction("send-prod", jig=jig_type, prod_line=production_line_type, rack=rack_type, hangar=hangar_type, trailer=trailer_type)

            # add task to load to production line
            rack = p.task_network.add_variable(f"r_{jig_name}_2", rack_type)
            trailer = p.task_network.add_variable(f"t_{jig_name}_2", trailer_type)
            hangar = p.task_network.add_variable(f"h_{jig_name}_2", hangar_type)
            t_send = p.task_network.add_subtask(send_prod, jig, pline_obj, rack, hangar, trailer)
            
            # add task to retrieve empty jig from hangar
            rack = p.task_network.add_variable(f"r_return_{jig_name}_2", rack_type)
            trailer = p.task_network.add_variable(f"t_return_{jig_name}_2", trailer_type)
            t_retrieve = p.task_network.add_subtask(retrieve_prod, jig, pline_obj, rack, hangar, trailer)
            
            p.task_network.add_constraint(LT(t_send.end, t_retrieve.start))

            if prev is not None:
                p.task_network.add_constraint(LT(prev.end, t_send.end))
            prev = t_send

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
