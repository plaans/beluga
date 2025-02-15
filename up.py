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
        # result = planner.solve(pb, timeout=90, output_stream=sys.stdout) # type: ignore
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

    # # #
    
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

    # # #

    unload_jig_from_beluga_to_trailer = DurativeAction("unload_beluga", j=jig_type, b=beluga_type, t=trailer_type)
    unload_jig_from_beluga_to_trailer.set_closed_duration_interval(1, 1000)
    load_to_trailer(
        unload_jig_from_beluga_to_trailer,
        unload_jig_from_beluga_to_trailer.j,
        unload_jig_from_beluga_to_trailer.t,
        beluga_side,
    )
    p.add_action(unload_jig_from_beluga_to_trailer)

    load_jig_from_trailer_to_beluga = DurativeAction("load_beluga", j=jig_type, b=beluga_type, t=trailer_type)
    load_jig_from_trailer_to_beluga.set_closed_duration_interval(1, 1000)
    unload_from_trailer(
        load_jig_from_trailer_to_beluga,
        load_jig_from_trailer_to_beluga.j,
        load_jig_from_trailer_to_beluga.t,
        beluga_side,
    )
    p.add_action(load_jig_from_trailer_to_beluga)

    put_down_jig_on_rack = DurativeAction("put_down_rack", j=jig_type, t=trailer_type, r=rack_type, s=side_type, os=side_type)
    put_down_jig_on_rack.set_closed_duration_interval(1, 1000)
    to_rack(
        put_down_jig_on_rack,
        put_down_jig_on_rack.j,
        put_down_jig_on_rack.r,
        put_down_jig_on_rack.t,
        put_down_jig_on_rack.s,
        put_down_jig_on_rack.os,
    )
    p.add_action(put_down_jig_on_rack)

    pick_up_jig_from_rack = DurativeAction("pick_up_rack", j=jig_type, t=trailer_type, r=rack_type, s=side_type, os=side_type)
    pick_up_jig_from_rack.set_closed_duration_interval(1, 1000)
    from_rack(
        pick_up_jig_from_rack,
        pick_up_jig_from_rack.j,
        pick_up_jig_from_rack.r,
        pick_up_jig_from_rack.t,
        pick_up_jig_from_rack.s,
        pick_up_jig_from_rack.os,
    )
    p.add_action(pick_up_jig_from_rack)

    deliver_jig_to_hangar = DurativeAction("deliver_to_hangar", j=jig_type, h=hangar_type, t=trailer_type, pl=production_line_type)
    deliver_jig_to_hangar.set_closed_duration_interval(1, 1000)
    deliver_jig_to_hangar.add_condition(EndTiming(), free_hangar(deliver_jig_to_hangar.h))
    deliver_jig_to_hangar.add_effect(EndTiming(), free_hangar(deliver_jig_to_hangar.h), False)
    unload_from_trailer(
        deliver_jig_to_hangar,
        deliver_jig_to_hangar.j,
        deliver_jig_to_hangar.t,
        production_side,
    )
    p.add_action(deliver_jig_to_hangar)

    get_jig_from_hangar = DurativeAction("get_from_hangar", j=jig_type, h=hangar_type, t=trailer_type)
    get_jig_from_hangar.set_closed_duration_interval(1, 1000)
    get_jig_from_hangar.add_effect(StartTiming(), free_hangar(get_jig_from_hangar.h), True)
    load_to_trailer(
        get_jig_from_hangar,
        get_jig_from_hangar.j,
        get_jig_from_hangar.t,
        production_side
    )
    p.add_action(get_jig_from_hangar)

    proceed_to_next = InstantaneousAction("switch_to_next_beluga")
    p.add_action(proceed_to_next)

    # # #

    # add task to allow an arbitrary number of swaps between racks
    do_swaps = p.add_task("do_swaps")
    m1 = Method("m-noop")
    m1.set_task(do_swaps)
    p.add_method(m1)

    m2 = Method("m-do-rec", p=jig_type, r1=rack_type, r2=rack_type, t=trailer_type, side=side_type, oside=side_type)
    m2.set_task(do_swaps)
    swap_subtask_part1 = m2.add_subtask(pick_up_jig_from_rack, m2.p, m2.t, m2.r1, m2.side, m2.oside)
    swap_subtask_part2 = m2.add_subtask(put_down_jig_on_rack, m2.p, m2.t, m2.r2, m2.side, m2.oside)
    rec_subtask = m2.add_subtask(do_swaps)
    #m2.set_ordered(swap_subtask_part1, swap_subtask_part2, rec_subtask)
    m2.add_constraint(Equals(swap_subtask_part1.end, swap_subtask_part2.start)) # FIXME: find a way to keep an epsilon time between the two ?
    m2.set_ordered(swap_subtask_part2, rec_subtask)
    p.add_method(m2)

    p.task_network.add_subtask(do_swaps)

    # # #

    epochs = []
    for i in range(len(instance.flights)):
        if i == 0:
            epochs.append(None)
        else:
            t = p.task_network.add_subtask(proceed_to_next)
            epochs.append(t)
        if i > 1:
            p.task_network.add_constraint(LT(epochs[i-1].end, t.start))

    def add_unloading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)

        prev = None
        for i, jig_name in enumerate(flight.incoming):
            jig = p.object(jig_name)

            rack = p.task_network.add_variable(f"r_{jig_name}_1", rack_type)
            trailer = p.task_network.add_variable(f"t_{jig_name}_1", trailer_type)

            # add tasks to unload from beluga
            t1 = p.task_network.add_subtask(unload_jig_from_beluga_to_trailer, jig, beluga, trailer)
            t2 = p.task_network.add_subtask(put_down_jig_on_rack, jig, trailer, rack, beluga_side, production_side)

            p.task_network.set_ordered(t1, t2)

            if flight_number > 0:
                p.task_network.add_constraint(LT(epochs[flight_number].end, t1.start))
            if flight_number < len(instance.flights)-1:
                p.task_network.add_constraint(LT(t2.end, epochs[flight_number+1].start))

            if prev is not None:
                p.task_network.add_constraint(LT(t1.start, prev.start))
            prev = t1
    
    def add_loading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)
        
        prev = None
        for i, jig_type_name in enumerate(flight.outgoing):
            jig_type = jig_types[jig_type_name]
            
            # add tasks to load to beluga
            jig = p.task_network.add_variable(f"jig_{flight.name}_{i}", jig_type)
            rack = p.task_network.add_variable(f"r_{flight.name}_{i}", rack_type)
            trailer = p.task_network.add_variable(f"t_{flight.name}_{i}", trailer_type)

            t1 = p.task_network.add_subtask(pick_up_jig_from_rack, jig, trailer, rack, beluga_side, production_side)
            t2 = p.task_network.add_subtask(load_jig_from_trailer_to_beluga, jig, beluga, trailer)
            
            p.task_network.set_ordered(t1, t2)

            if flight_number > 0:
                p.task_network.add_constraint(LT(epochs[flight_number].end, t1.start))
            if flight_number < len(instance.flights)-1:
                p.task_network.add_constraint(LT(t2.end, epochs[flight_number+1].start))

            if prev is not None:
                p.task_network.add_constraint(LT(t2.start, prev.start))
            prev = t2

    for i in range(len(instance.flights)):
        add_unloading(i)
        add_loading(i)
    
    for pline in instance.production_lines:
        
        pline_obj = p.object(pline.name)
        prev = None
        for i, jig_name in enumerate(pline.schedule):
            jig = p.object(jig_name)
   
            # add tasks to load to production line
            rack = p.task_network.add_variable(f"r_{jig_name}_2", rack_type)
            trailer = p.task_network.add_variable(f"t_{jig_name}_2", trailer_type)
            hangar = p.task_network.add_variable(f"h_{jig_name}_2", hangar_type)
            
            t_send1 = p.task_network.add_subtask(pick_up_jig_from_rack, jig, trailer, rack, production_side, beluga_side)
            t_send2 = p.task_network.add_subtask(deliver_jig_to_hangar, jig, hangar, trailer, pline_obj)

            p.task_network.set_ordered(t_send1, t_send2)

            # add tasks to retrieve empty jig from hangar
            rack = p.task_network.add_variable(f"r_return_{jig_name}_2", rack_type)
            trailer = p.task_network.add_variable(f"t_return_{jig_name}_2", trailer_type)

            t_retrieve1 = p.task_network.add_subtask(get_jig_from_hangar, jig, hangar, trailer)
            t_retrieve2 = p.task_network.add_subtask(put_down_jig_on_rack, jig, trailer, rack, production_side, beluga_side)

            p.task_network.set_ordered(t_retrieve1, t_retrieve2)
            
            p.task_network.add_constraint(LT(t_send2.end, t_retrieve1.start))

            if prev is not None:
                p.task_network.add_constraint(LT(prev.end, t_send2.end))
            prev = t_send2

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
