from unified_planning.shortcuts import *
from unified_planning.model.htn import *
from unified_planning.model.scheduling import *

import sys

from parser import *
CNT = 0


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


def convert(instance: BelugaProblemDef, name: str) -> SchedulingProblem:
    num_trucks_beluga = len(instance.trailers_beluga)
    num_trucks_production = len(instance.trailers_factory)


    p = SchedulingProblem(name)

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

    def load_to_trailer(a: Activity, jig, trailer, side):
        a.add_condition(StartTiming(), Equals(truck_side(trailer), side))
        a.add_decrease_effect(StartTiming()+1, free_trucks(side), 1)
        a.add_effect(StartTiming()+1, at(jig), trailer)
        a.add_condition(StartTiming(), available(trailer))
        a.add_effect(StartTiming()+1, available(trailer), False)

    def unload_from_trailer(a: Activity, jig, trailer, side):
        a.add_condition(StartTiming(), Equals(truck_side(trailer), side))
        a.add_increase_effect(EndTiming()+1, free_trucks(side), 1)
        a.add_effect(EndTiming()+1, available(trailer), True)

    def to_rack(a: Activity, jig, rack, trailer, side, oside):
        unload_from_trailer(a, jig, trailer, side)
        a.add_decrease_effect(EndTiming()+1, free(rack), size(jig))
        a.add_increase_effect(EndTiming()+1, next(rack, side), 1)

        a.add_effect(EndTiming()+1, at(jig), rack)
        a.add_effect(EndTiming()+1, pos(jig, side), next(rack, side) + 1)
        a.add_effect(EndTiming()+1, pos(jig, oside), -next(rack, side))

    def from_rack(a: Activity, jig, rack, trailer, side, oside):
        a.add_condition(StartTiming(), Equals(at(jig), rack))
        a.add_condition(StartTiming(), Equals(next(rack, side), pos(jig, side)))
        a.add_increase_effect(StartTiming()+1, free(rack), size(jig))
        a.add_decrease_effect(StartTiming()+1, next(rack, side), 1)
        load_to_trailer(a, jig, trailer, side)
        pass


    def nextid() -> int:
        global CNT
        CNT = CNT + 1
        return CNT


    # swap = DurativeAction("swap", p=jig_type, r1=rack_type, r2=rack_type, trailer=truck_type, side=side_type, oside=side_type)
    # swap.set_closed_duration_interval(1, 1000)
    # swap.add_condition(StartTiming(), Equals(opposite(swap.side), swap.oside))
    # from_rack(swap, swap.p, swap.r1, swap.trailer, swap.side, swap.oside)
    # to_rack(swap, swap.p, swap.r2, swap.trailer, swap.side, swap.oside)
    # p.add_action(swap)
    def add_swap(pb: SchedulingProblem, i: int) -> Activity:
        a = pb.add_activity(f"swap-{i}", optional=True)
        a.set_duration_bounds(1, 1000)
        a.add_parameter("jig", jig_type)
        a.add_parameter("rack1", rack_type)
        a.add_parameter("rack2", rack_type)
        a.add_parameter("trailer", truck_type)
        a.add_parameter("side", side_type)
        a.add_parameter("oside", side_type)
        a.add_constraint(Equals(opposite(a.side), a.oside))
        from_rack(a, a.jig, a.rack1, a.trailer, a.side, a.oside)
        to_rack(a, a.jig, a.rack2, a.trailer, a.side, a.oside)
        return a

    # unload = DurativeAction("unload", jig=jig_type, beluga=beluga_type, rack=rack_type, trailer=truck_type)
    # unload.set_closed_duration_interval(1, 1000)
    # to_rack(unload, unload.jig, unload.rack, unload.trailer, beluga_side, production_side)
    # load_to_trailer(unload, unload.jig, unload.trailer, beluga_side)
    # p.add_action(unload)
    def add_unload(pb: SchedulingProblem, jig, beluga) -> Activity:
        a = pb.add_activity(f"unload-{nextid()}", optional=False)
        a.set_duration_bounds(1, 1000)
        a.add_parameter("jig", jig_type)
        a.add_constraint(Equals(a.jig, jig))
        a.add_parameter("beluga", beluga_type)
        a.add_constraint(Equals(a.beluga, beluga))
        a.add_parameter("rack", rack_type)
        a.add_parameter("trailer", truck_type)
        load_to_trailer(a, a.jig, a.trailer, beluga_side)
        to_rack(a, a.jig, a.rack, a.trailer, beluga_side, production_side)

        return a

    # load = DurativeAction("load", jig=jig_type, beluga=beluga_type, rack=rack_type, trailer=truck_type)
    # load.set_closed_duration_interval(1, 1000)
    # from_rack(load, load.jig, load.rack, load.trailer, beluga_side, production_side)
    # unload_from_trailer(load, load.jig, load.trailer, beluga_side)
    # p.add_action(load)
    def add_load(pb: SchedulingProblem, jig_type, beluga) -> Activity:
        a = pb.add_activity(f"load-{nextid()}", optional=False)
        a.set_duration_bounds(1, 1000)
        a.add_parameter("jig", jig_type)
        a.add_parameter("beluga", beluga_type)
        a.add_constraint(Equals(a.beluga, beluga))
        a.add_parameter("rack", rack_type)
        a.add_parameter("trailer", truck_type)
        from_rack(a, a.jig, a.rack, a.trailer, beluga_side, production_side)
        unload_from_trailer(a, a.jig, a.trailer, beluga_side)
        return a


    # send_prod = DurativeAction("send-prod", jig=jig_type, prod_line=production_line_type, rack=rack_type, hangar=hangar_type, trailer=truck_type)
    # send_prod.set_closed_duration_interval(1, 1000)
    # send_prod.add_condition(EndTiming(), free_hangar(send_prod.hangar))
    # send_prod.add_effect(EndTiming(), free_hangar(send_prod.hangar), False)
    # from_rack(send_prod, send_prod.jig, send_prod.rack, send_prod.trailer, production_side, beluga_side)
    # unload_from_trailer(send_prod, send_prod.jig, send_prod.trailer, production_side)
    # p.add_action(send_prod)
    def add_send_prod(pb: SchedulingProblem, jig, prod_line) -> Activity:
        a = pb.add_activity(f"send-prod-{nextid()}", optional=False)
        a.set_duration_bounds(1, 1000)
        a.add_parameter("jig", jig_type)
        a.add_constraint(Equals(a.jig, jig))
        a.add_parameter("prod_line", production_line_type)
        a.add_constraint(Equals(a.prod_line, prod_line))
        a.add_parameter("rack", rack_type)
        a.add_parameter("hangar", hangar_type)
        a.add_parameter("trailer", truck_type)
        from_rack(a, a.jig, a.rack, a.trailer, production_side, beluga_side)
        unload_from_trailer(a, a.jig, a.trailer, production_side)
        a.add_condition(EndTiming() -1, free_hangar(a.hangar))
        a.add_effect(EndTiming(), free_hangar(a.hangar), False)
        return a



    # retrieve_prod = DurativeAction("retrieve-prod", jig=jig_type, prod_line=production_line_type, rack=rack_type, hangar=hangar_type, trailer=truck_type)
    # retrieve_prod.set_closed_duration_interval(1, 1000)
    # retrieve_prod.add_effect(StartTiming(), free_hangar(retrieve_prod.hangar), True)
    # to_rack(retrieve_prod, retrieve_prod.jig, retrieve_prod.rack, retrieve_prod.trailer, production_side, beluga_side)
    # load_to_trailer(retrieve_prod, retrieve_prod.jig, retrieve_prod.trailer, production_side)
    # p.add_action(retrieve_prod)
    def add_retrieve_prod(pb: SchedulingProblem, jig, prod_line) -> Activity:
        a = pb.add_activity(f"retrieve-prod-{nextid()}", optional=False)
        a.set_duration_bounds(1, 1000)
        a.add_parameter("jig", jig_type)
        a.add_constraint(Equals(a.jig, jig))
        a.add_parameter("prod_line", production_line_type)
        a.add_constraint(Equals(a.prod_line, prod_line))
        a.add_parameter("rack", rack_type)
        a.add_parameter("hangar", hangar_type)
        a.add_parameter("trailer", truck_type)
        a.add_effect(StartTiming(), free_hangar(a.hangar), True)
        to_rack(a, a.jig, a.rack, a.trailer, production_side, beluga_side)
        load_to_trailer(a, a.jig, a.trailer, production_side)
        return a

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
        p.set_initial_value(next(r, production_side), num_pieces)   ## Nicka suggested adding -1 but does not seem to work


    def new_proceed_to_next(pb: SchedulingProblem, id: int):
      a = pb.add_activity(name=f"next-{id}")
      return a

    epochs = []
    for i in range(len(instance.flights)+2):
        t = new_proceed_to_next(p, i)
        epochs.append(t)
        if i > 0:
            p.add_constraint(LT(epochs[i-1].end, t.start))


    def add_unloading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)

        prev = None
        for i, jig_name in enumerate(flight.incoming):
            jig = p.object(jig_name)

            t = add_unload(p, jig, beluga)

            p.add_constraint(LT(epochs[flight_number].end, t.start), scope=[t.present])
            p.add_constraint(LT(t.end, epochs[flight_number+1].start), scope=[t.present])

            if prev is not None:
                p.add_constraint(LT(t.start, prev.start), scope=[prev.present, t.present])
            prev = t


    def add_loading(flight_number: int):
        flight = instance.flights[flight_number]
        beluga = p.object(flight.name)

        prev = None
        for i, jig_type_name in enumerate(flight.outgoing):
            jig_type = jig_types[jig_type_name]

            # add task to unload from beluga
            t = add_load(p, jig_type, beluga)

            p.add_constraint(LT(epochs[flight_number+1].end, t.start), scope=[t.present])
            p.add_constraint(LT(t.end, epochs[flight_number+2].start), scope=[t.present])

            if prev is not None:
                p.add_constraint(LT(t.start, prev.start), scope=[prev.present, t.present])
            prev = t

    for i in range(len(instance.flights)):
        add_unloading(i)
        add_loading(i)


    for pline in instance.production_lines:

        pline_obj = p.object(pline.name)
        prev = None
        for i, jig_name in enumerate(pline.schedule):
            jig = p.object(jig_name)

            # add task to load to production line
            t_send = add_send_prod(p, jig, pline_obj)

            # add task to retrieve empty jig from hangar
            t_retrieve = add_retrieve_prod(p, jig, pline_obj)
            p.add_constraint(Equals(t_send.hangar, t_retrieve.hangar), scope=[t_send.present, t_retrieve.present])

            p.add_constraint(LT(t_send.end, t_retrieve.start), scope=[t_send.present, t_retrieve.present])

            if prev is not None:
                p.add_constraint(LT(prev.end, t_send.end), scope=[prev.present, t_send.present])
            prev = t_send




    MAX_SWAPS = 10
    num_swaps = p.add_variable("num_swaps", IntType(0, MAX_SWAPS))
    prev = None
    for i in range(1, MAX_SWAPS+1):
        t = add_swap(p, i)
        t.add_constraint(GE(num_swaps, i))
        p.add_constraint(Implies(Not(t.present), LT(num_swaps, i)))
        if prev is not None:
            # add symmetry breaking constraint
            p.add_constraint(Implies(t.present, prev.present))
            p.add_constraint(LE(prev.start, t.start), scope=[prev.present, t.present])
        prev = t



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
