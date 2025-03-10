from unified_planning.shortcuts import *
from unified_planning.model.htn import *

import sys

import unified_planning.shortcuts as up
import unified_planning.model.htn as up_htn

from unified_planning.model.expression import ConstantExpression
from unified_planning.plans.hierarchical_plan import HierarchicalPlan
from unified_planning.exceptions import UPValueError

from parser import *

def serialize_problem(pb: up.Problem, filename: str):
    from unified_planning.grpc.proto_writer import ProtobufWriter
    writer = ProtobufWriter()
    msg = writer.convert(pb)
    with open(filename, "wb") as file:
        file.write(msg.SerializeToString())

def solve_problem(pb: up_htn.HierarchicalProblem) -> HierarchicalPlan: # type: ignore
    with up.OneshotPlanner(name="aries") as planner:
        # result = planner.solve(pb, timeout=90, output_stream=sys.stdout) # type: ignore
        result = planner.solve(pb, output_stream=sys.stdout) # type: ignore
        plan = result.plan
    return plan

@dataclass
class BelugaProblemMetadata:
    pb_def: BelugaProblemDef
    pb_unload_jig_from_beluga_to_trailer: up.DurativeAction
    pb_load_jig_from_trailer_to_beluga: up.DurativeAction
    pb_putdown_jig_on_rack: up.DurativeAction
    pb_pickup_jig_from_rack: up.DurativeAction
    pb_deliver_jig_to_hangar: up.DurativeAction
    pb_get_jig_from_hangar: up.DurativeAction
    pb_proceed_to_next_flight: up.InstantaneousAction
    pb_all_unloads: list[tuple[up_htn.Subtask, up_htn.Subtask]]
    pb_all_loads: list[tuple[up_htn.Subtask, up_htn.Subtask]] 
    pb_all_delivers: list[tuple[up_htn.Subtask, up_htn.Subtask]] 
    pb_all_gets: list[tuple[up_htn.Subtask, up_htn.Subtask]] 
    pb_all_swaps: list[up_htn.Subtask] 
    pb_all_proceed_to_next_flight: list[up_htn.Subtask] 
    pb_num_used_swaps: up.Parameter
    pb_all_non_swap_subtasks: list[up_htn.Subtask]
    rack_free_space_init: dict[up.Object, int]
    rack_size: dict[up.Object, int]
#    jigs_are_of_same_type: dict[tuple[up.Object, up.Object], int]
    rack_vars_unloads: dict[str, up.Parameter]
    rack_vars_loads: dict[tuple[str, int], up.Parameter]
    rack_vars_delivers: dict[str, up.Parameter]
    rack_vars_gets: dict[str, up.Parameter]
    rack1_vars_swaps: dict[int, up.Parameter]
    rack2_vars_swaps: dict[int, up.Parameter]
    used_rack_size_vars_unloads: dict[str, up.Parameter]
    used_rack_size_vars_gets: dict[str, up.Parameter]
    jig_vars_swaps: dict[int, up.Parameter]
    used_rack_size_vars_swaps: dict[int, up.Parameter]
    max_putdown_delay_vars_unloads: dict[str, up.Parameter]
    max_putdown_delay_vars_gets: dict[str, up.Parameter]
    _objects: list[up.Object]

#    def object(self, name: str) -> up.Object:
#        for o in self._objects:
#            if o.name == name:
#                return o
#        raise UPValueError(f"Object of name: {name} is not defined!")

def make_problem(pb_def: BelugaProblemDef, name: str, num_available_swaps: int=20) -> tuple[up_htn.HierarchicalProblem, BelugaProblemMetadata]:

    pb = up_htn.HierarchicalProblem(name)
    pb.epsilon = 1 # FIXME: ?? needed to later extract the difference between two timepoints as an int ??

    ##### Types, fluents, and initial values set up #####

    side_type = up.UserType("Side")
    beluga_side = pb.add_object("bside", side_type)
    production_side = pb.add_object("fside", side_type)
    opposite_side = pb.add_fluent("opposite", side_type, s=side_type)

    pb.set_initial_value(opposite_side(beluga_side), production_side)
    pb.set_initial_value(opposite_side(production_side), beluga_side)

    # # #

    jig_type = up.UserType("JigType")
    jig_types = {}
    for jt in pb_def.jig_types:
        sub_type = up.UserType(jt.name, jig_type)
        jig_types[jt.name] = sub_type
    jig_size = pb.add_fluent("size", up.IntType(), j=jig_type)

    for jig in pb_def.jigs:
        part_obj = pb.add_object(jig.name, jig_types[jig.type])
        tpe = pb_def.get_jig_type(jig.type)
        if jig.empty:
            pb.set_initial_value(jig_size(part_obj), tpe.size_empty)
        else:
            pb.set_initial_value(jig_size(part_obj), tpe.size_loaded)

#    jigs_are_of_same_type = pb.add_fluent("jigs_are_of_same_type", up.BoolType(), j1=jig_type, j2=jig_type)
#    for jig1 in pb_def.jigs:
#        for jig2 in pb_def.jigs:
#            pb.set_initial_value(jigs_are_of_same_type(pb.object(jig1.name), pb.object(jig2.name)), up.Bool(jig1.type == jig2.type))

    # # #

    part_location_type = up.UserType("PartLoc")

    # # #

    rack_type = up.UserType("Rack", father=part_location_type)
    rack_free_space = pb.add_fluent("rack_free_space", up.IntType(0, 1000), r=rack_type)
    rack_size = pb.add_fluent("rack_size", up.IntType(0, 1000), rack=rack_type)

    # # #

    beluga_type = up.UserType("Beluga", part_location_type)
    belugas = {}
    for beluga in pb_def.flights:
        b = pb.add_object(beluga.name, beluga_type)
        belugas[beluga.name] = b

    # # #

    hangar_type = up.UserType("Hangar", father=part_location_type)
    free_hangar = pb.add_fluent("free_hangar", up.BoolType(), h=hangar_type)
    hangars = {}
    for hangar in pb_def.hangars:
        h = pb.add_object(hangar, hangar_type)
        pb.set_initial_value(free_hangar(h), True)
        hangars[hangar] = h

    # # #

    production_line_type = up.UserType("ProductionLine", part_location_type)
    for production_line in pb_def.production_lines:
        pb.add_object(production_line.name, production_line_type)

    # # #

    trailer_type = up.UserType("Trailer", part_location_type)
    available = up.Fluent("available", up.BoolType(), t=trailer_type)
    pb.add_fluent(available, default_initial_value=True)
    trailer_side = pb.add_fluent("trailer_side", side_type, trailer=trailer_type)

    num_trailers_beluga = len(pb_def.trailers_beluga)
    num_trailers_production = len(pb_def.trailers_factory)

    free_trailers = pb.add_fluent("free_trailers", up.IntType(0,max(num_trailers_beluga, num_trailers_production)), side=side_type)
    pb.set_initial_value(free_trailers(beluga_side), num_trailers_beluga)
    pb.set_initial_value(free_trailers(production_side), num_trailers_production)

    for trailer in pb_def.trailers_beluga:
        trailer = pb.add_object(trailer, trailer_type)
        pb.set_initial_value(trailer_side(trailer), beluga_side)
    for trailer in pb_def.trailers_factory:
        trailer = pb.add_object(trailer, trailer_type)
        pb.set_initial_value(trailer_side(trailer), production_side)

    # # #

    next = up.Fluent("next", up.IntType(), r=rack_type, s=side_type)
    pb.add_fluent(next, default_initial_value=0)
    at = pb.add_fluent("at", part_location_type, p=jig_type)
    pos = pb.add_fluent("pos", up.IntType(), p=jig_type, s=side_type)

    # # #

    for rack in pb_def.racks:
        r = pb.add_object(rack.name, rack_type)

        num_pieces = len(rack.jigs)
        occupied_space = 0
        for k, jig_name in enumerate(rack.jigs):
            jig = pb_def.get_jig(jig_name)
            pb_def_jig_type = pb_def.get_jig_type(jig.type)
            jig_size_val = pb_def_jig_type.size_empty if jig.empty else pb_def_jig_type.size_loaded
            occupied_space += jig_size_val
            jig = pb.object(jig_name)
            pb.set_initial_value(pos(jig, beluga_side), k)
            pb.set_initial_value(pos(jig, production_side), num_pieces - k)
            pb.set_initial_value(at(jig), r)
        pb.set_initial_value(rack_free_space(r), rack.size - occupied_space)
        pb.set_initial_value(next(r, production_side), num_pieces)
        pb.set_initial_value(rack_size(r), rack.size)

    ##### Helper functions used to define actions (further below) #####

    def load_to_trailer(a: up.DurativeAction, jig, trailer, side):
        a.add_condition(up.StartTiming(), up.Equals(trailer_side(trailer), side))
        a.add_decrease_effect(up.StartTiming(), free_trailers(side), 1)
        a.add_effect(up.StartTiming(), at(jig), trailer)
        a.add_condition(up.StartTiming(), available(trailer))
        a.add_effect(up.StartTiming(), available(trailer), False)

    def unload_from_trailer(a: up.DurativeAction, jig, trailer, side):
        a.add_condition(up.StartTiming(), up.Equals(trailer_side(trailer), side))
        a.add_increase_effect(up.EndTiming(), free_trailers(side), 1)
        a.add_effect(up.EndTiming(), available(trailer), True)

    def to_rack(a: up.DurativeAction, jig, rack, trailer, side, oside):
        unload_from_trailer(a, jig, trailer, side)
        a.add_decrease_effect(up.EndTiming(), rack_free_space(rack), jig_size(jig))
        a.add_increase_effect(up.EndTiming(), next(rack, side), 1)

        a.add_effect(up.EndTiming(), at(jig), rack)
        a.add_effect(up.EndTiming(), pos(jig, side), next(rack, side) + 1)
        a.add_effect(up.EndTiming(), pos(jig, oside), -next(rack, side))

    def from_rack(a: up.DurativeAction, jig, rack, trailer, side, oside):
        a.add_condition(up.StartTiming(), up.Equals(at(jig), rack))
        a.add_condition(up.StartTiming(), up.Equals(next(rack, side), pos(jig, side)))
        a.add_increase_effect(up.StartTiming(), rack_free_space(rack), jig_size(jig))
        a.add_decrease_effect(up.StartTiming(), next(rack, side), 1)
        load_to_trailer(a, jig, trailer, side)

    ##### Actions and task methods definition #####

    unload_jig_from_beluga_to_trailer = up.DurativeAction(
        "unload_beluga",
        j=jig_type,
        b=beluga_type,
        t=trailer_type,
    )
    unload_jig_from_beluga_to_trailer.set_closed_duration_interval(1, 1000)
    load_to_trailer(
        unload_jig_from_beluga_to_trailer,
        unload_jig_from_beluga_to_trailer.j,
        unload_jig_from_beluga_to_trailer.t,
        beluga_side,
    )
    pb.add_action(unload_jig_from_beluga_to_trailer)

    # # #

    load_jig_from_trailer_to_beluga = up.DurativeAction(
        "load_beluga",
        j=jig_type,
        b=beluga_type,
        t=trailer_type,
    )
    load_jig_from_trailer_to_beluga.set_closed_duration_interval(1, 1000)
    unload_from_trailer(
        load_jig_from_trailer_to_beluga,
        load_jig_from_trailer_to_beluga.j,
        load_jig_from_trailer_to_beluga.t,
        beluga_side,
    )
    pb.add_action(load_jig_from_trailer_to_beluga)

    # # #

    putdown_jig_on_rack = up.DurativeAction(
        "put_down_rack",
        j=jig_type,
        t=trailer_type, 
        r=rack_type,
        s=side_type,
        os=side_type,
        rs=up.IntType(0, 1000),
        d=up.IntType(0, 1000),
    )
    putdown_jig_on_rack.set_closed_duration_interval(1, 1000)
    to_rack(
        putdown_jig_on_rack,
        putdown_jig_on_rack.j,
        putdown_jig_on_rack.r,
        putdown_jig_on_rack.t,
        putdown_jig_on_rack.s,
        putdown_jig_on_rack.os,
    )
    putdown_jig_on_rack.add_condition(up.StartTiming(), up.Equals(rack_size(putdown_jig_on_rack.r), putdown_jig_on_rack.rs))
    pb.add_action(putdown_jig_on_rack)

    # # #

    pickup_jig_from_rack = up.DurativeAction(
        "pick_up_rack", 
        j=jig_type,
        t=trailer_type,
        r=rack_type,
        s=side_type,
        os=side_type,
    )
    pickup_jig_from_rack.set_closed_duration_interval(1, 1000)
    from_rack(
        pickup_jig_from_rack,
        pickup_jig_from_rack.j,
        pickup_jig_from_rack.r,
        pickup_jig_from_rack.t,
        pickup_jig_from_rack.s,
        pickup_jig_from_rack.os,
    )
    pb.add_action(pickup_jig_from_rack)

    # # #

    deliver_jig_to_hangar = up.DurativeAction(
        "deliver_to_hangar",
        j=jig_type,
        h=hangar_type,
        t=trailer_type, 
        pl=production_line_type,
    )
    deliver_jig_to_hangar.set_closed_duration_interval(1, 1000)
    deliver_jig_to_hangar.add_condition(up.EndTiming(), free_hangar(deliver_jig_to_hangar.h))
    deliver_jig_to_hangar.add_effect(up.EndTiming(), free_hangar(deliver_jig_to_hangar.h), False)
    unload_from_trailer(
        deliver_jig_to_hangar,
        deliver_jig_to_hangar.j,
        deliver_jig_to_hangar.t,
        production_side,
    )
    pb.add_action(deliver_jig_to_hangar)

    # # #

    get_jig_from_hangar = up.DurativeAction(
        "get_from_hangar",
        j=jig_type,
        h=hangar_type,
        t=trailer_type,
    )
    get_jig_from_hangar.set_closed_duration_interval(1, 1000)
    get_jig_from_hangar.add_effect(up.StartTiming(), free_hangar(get_jig_from_hangar.h), True)
    load_to_trailer(
        get_jig_from_hangar,
        get_jig_from_hangar.j,
        get_jig_from_hangar.t,
        production_side
    )
    pb.add_action(get_jig_from_hangar)

    # # #

    proceed_to_next_flight = up.InstantaneousAction("switch_to_next_beluga")
    pb.add_action(proceed_to_next_flight)

    # # #

    do_swap = pb.add_task(
        "do_swap",
        is_noop=up.BoolType(),
        id_=up.IntType(0, 1000),
        j=jig_type,
        r1=rack_type,
        r2=rack_type,
        t=trailer_type,
        side=side_type,
        rs=up.IntType(0, 1000),
        mtp_lb=up.IntType(0, 1000),
        mtp_ub=up.IntType(0, 1000),
    )
    m1 = up_htn.Method(
        "m_swap_noop",
        is_noop=up.BoolType(),
        id_=up.IntType(0, 1000),
        j=jig_type,
        r1=rack_type,
        r2=rack_type,
        t=trailer_type,
        side=side_type,
        rs=up.IntType(0, 1000),
        mtp_lb=up.IntType(0, 1000),
        mtp_ub=up.IntType(0, 1000),
    )
    m1.set_task(do_swap)
    m1.add_constraint(m1.is_noop)
#    m1.add_constraint(up.Equals(m1.p, pb.object(pb_def.jigs[0].name)))
#    m1.add_constraint(up.Equals(m1.r1, pb.object(pb_def.racks[0].name)))
#    m1.add_constraint(up.Equals(m1.r2, pb.object(pb_def.racks[0].name)))
#    m1.add_constraint(up.Equals(m1.t, pb.object(pb_def.trailers_beluga[0])))
#    m1.add_constraint(up.Equals(m1.side, beluga_side))
#    m1.add_constraint(up.Equals(m1.rs, 0))
#    m1.add_constraint(up.Equals(m1.mtp_lb, 0))
#    m1.add_constraint(up.Equals(m1.mtp_ub, 0))
    pb.add_method(m1)

    m2 = up_htn.Method(
        "m_swap_do",
        is_noop=up.BoolType(),
        id_=up.IntType(0, 1000),
        j=jig_type,
        r1=rack_type,
        r2=rack_type,
        t=trailer_type,
        side=side_type,
        oside=side_type,
        rs=up.IntType(0, 1000),
        mtp_lb=up.IntType(0, 1000),
        mtp_ub=up.IntType(0, 1000),
    )
    m2.set_task(do_swap)
    m2.add_constraint(up.Not(m2.is_noop))
    swap_1half = m2.add_subtask(pickup_jig_from_rack, m2.j, m2.t, m2.r1, m2.side, m2.oside)
    swap_2half = m2.add_subtask(putdown_jig_on_rack, m2.j, m2.t, m2.r2, m2.side, m2.oside, m2.rs, 0)
    m2.set_ordered(swap_1half, swap_2half)
    m2.add_constraint(up.LE(swap_1half.end, m2.mtp_lb))
    m2.add_constraint(up.LE(m2.mtp_lb, swap_2half.start))
    m2.add_constraint(up.LE(swap_2half.start, m2.mtp_ub))
    m2.add_constraint(up.LE(m2.mtp_ub, swap_2half.end))
    pb.add_method(m2)

    ##### (Initial) task network #####

    num_flights = len(pb_def.flights)

    all_proceed_to_next_flight: list[up_htn.Subtask] = []
    for k in range(num_flights-1):
        proceed_st = pb.task_network.add_subtask(proceed_to_next_flight)
        all_proceed_to_next_flight.append(proceed_st)
    pb.task_network.set_ordered(*all_proceed_to_next_flight)

    # # #

    rack_vars_unloads: dict[str, up.Parameter] = {}
    trailer_vars_unloads: dict[str, up.Parameter] = {}
    used_rack_size_vars_unloads: dict[str, up.Parameter] = {}
    max_putdown_delay_vars_unloads: dict[str, up.Parameter] = {}
    for flights in pb_def.flights:
        for jig_name in flights.incoming:
            rack_vars_unloads[jig_name] = pb.task_network.add_variable(f"r_{jig_name}_1", rack_type)
            trailer_vars_unloads[jig_name] = pb.task_network.add_variable(f"t_{jig_name}_1", trailer_type)
            used_rack_size_vars_unloads[jig_name] = pb.task_network.add_variable(f"rs_{jig_name}_1", up.IntType(0, 1000))
            max_putdown_delay_vars_unloads[jig_name] = pb.task_network.add_variable(f"md_{jig_name}_1", up.IntType(0, 1000))

    # # #

    all_unloads: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
    def add_unloading(flights_index: int) -> up_htn.Subtask | None:
        flights = pb_def.flights[flights_index]
        if len(flights.incoming) == 0:
            return None

        beluga = pb.object(flights.name)
        prev_unload_st = None
        for jig_name in flights.incoming:

            unload_st = pb.task_network.add_subtask(
                unload_jig_from_beluga_to_trailer,
                pb.object(jig_name),
                beluga,
                trailer_vars_unloads[jig_name],
            )
            putdown_st = pb.task_network.add_subtask(
                putdown_jig_on_rack,
                pb.object(jig_name),
                trailer_vars_unloads[jig_name],
                rack_vars_unloads[jig_name],
                beluga_side,
                production_side,
                used_rack_size_vars_unloads[jig_name],
                max_putdown_delay_vars_unloads[jig_name],
            )
            all_unloads.append((unload_st, putdown_st))

            pb.task_network.add_constraint(up.LE(up.Minus(putdown_st.start, unload_st.start), max_putdown_delay_vars_unloads[jig_name]))

            pb.task_network.set_ordered(unload_st, putdown_st)

            if flight_index > 0:
                pb.task_network.add_constraint(up.LT(all_proceed_to_next_flight[flight_index-1].end, unload_st.start))
            if flight_index < num_flights-1:
                pb.task_network.add_constraint(up.LT(unload_st.end, all_proceed_to_next_flight[flight_index].start))

            if prev_unload_st is not None:
                pb.task_network.add_constraint(up.LT(prev_unload_st.end, unload_st.start))
            prev_unload_st = unload_st

        return unload_st

    # # #

    jig_vars_loads: dict[tuple[str, int], up.Parameter] = {}
    trailer_vars_loads: dict[tuple[str, int], up.Parameter] = {}
    rack_vars_loads: dict[tuple[str, int], up.Parameter] = {}
    for flights in pb_def.flights:
        for i, jig_type_name in enumerate(flights.outgoing):
            jig_vars_loads[(flights.name, i)] = pb.task_network.add_variable(f"jig_{flights.name}_{i}", jig_types[jig_type_name])
            trailer_vars_loads[(flights.name, i)] = pb.task_network.add_variable(f"t_{flights.name}_{i}", trailer_type)
            rack_vars_loads[(flights.name, i)] = pb.task_network.add_variable(f"r_{flights.name}_{i}", rack_type)

    all_loads: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
    def add_loading(flights_index: int, last_unload_before_loads: up_htn.Subtask | None):
        flights = pb_def.flights[flights_index]
        if len(flights.outgoing) == 0:
            return

        flight_name = flights.name
        beluga = pb.object(flight_name)
        prev_load_st = None
        for i in range(len(flights.outgoing)):

            pickup_st = pb.task_network.add_subtask(
                pickup_jig_from_rack,
                jig_vars_loads[(flight_name, i)],
                trailer_vars_loads[(flight_name, i)],
                rack_vars_loads[(flight_name, i)],
                beluga_side,
                production_side,
            )
            load_st = pb.task_network.add_subtask(
                load_jig_from_trailer_to_beluga, 
                jig_vars_loads[(flight_name, i)], 
                beluga, 
                trailer_vars_loads[(flight_name, i)],
            )
            all_loads.append((pickup_st, load_st))

            if i == 0 and last_unload_before_loads is not None:
                pb.task_network.set_ordered(last_unload_before_loads, load_st)

            pb.task_network.set_ordered(pickup_st, load_st)

            if flight_index > 0:
                pb.task_network.add_constraint(up.LT(all_proceed_to_next_flight[flight_index-1].end, load_st.start))
            if flight_index < num_flights-1:
                pb.task_network.add_constraint(up.LT(load_st.end, all_proceed_to_next_flight[flight_index].start))

            if prev_load_st is not None:
                pb.task_network.add_constraint(up.LT(prev_load_st.end, load_st.start))
            prev_load_st = load_st

    # # #

    trailer_vars_delivers: dict[str, up.Parameter] = {}
    rack_vars_delivers: dict[str, up.Parameter] = {}
    hangar_vars_delivers_n_gets: dict[str, up.Parameter] = {}
    trailer_vars_gets: dict[str, up.Parameter] = {}
    rack_vars_gets: dict[str, up.Parameter] = {}
    used_rack_size_vars_gets: dict[str, up.Parameter] = {}
    max_putdown_delay_vars_gets: dict[str, up.Parameter] = {}
    for production_line in pb_def.production_lines:
        for i, jig_name in enumerate(production_line.schedule):
            trailer_vars_delivers[jig_name] = pb.task_network.add_variable(f"t_{jig_name}_2a", trailer_type)
            rack_vars_delivers[jig_name] = pb.task_network.add_variable(f"r_{jig_name}_2a", rack_type)
            hangar_vars_delivers_n_gets[jig_name] = pb.task_network.add_variable(f"h_{jig_name}_2", hangar_type)
            trailer_vars_gets[jig_name] = pb.task_network.add_variable(f"t_{jig_name}_2b", trailer_type)
            rack_vars_gets[jig_name] = pb.task_network.add_variable(f"r_{jig_name}_2b", rack_type)
            used_rack_size_vars_gets[jig_name] = pb.task_network.add_variable(f"rs_{jig_name}_2b", up.IntType(0, 1000))
            max_putdown_delay_vars_gets[jig_name] = pb.task_network.add_variable(f"md_{jig_name}_2b", up.IntType(0, 1000))

    all_delivers: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
    all_gets: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
    def add_delivering_and_getting(production_line: ProductionLine):

        prev_deliver = None
        for jig_name in production_line.schedule:
   
            pickup_st = pb.task_network.add_subtask(
                pickup_jig_from_rack,
                pb.object(jig_name),
                trailer_vars_delivers[jig_name],
                rack_vars_delivers[jig_name],
                production_side,
                beluga_side,
            )
            deliver_st = pb.task_network.add_subtask(
                deliver_jig_to_hangar,
                pb.object(jig_name),
                hangar_vars_delivers_n_gets[jig_name],
                trailer_vars_delivers[jig_name],
                pb.object(production_line.name),
            )
            all_delivers.append((pickup_st, deliver_st))

            if prev_deliver is not None:
#                pb.task_network.add_constraint(up.LT(prev_deliver.start, deliver_st.start))
                pb.task_network.add_constraint(up.LT(prev_deliver.end, deliver_st.end))
            prev_deliver = deliver_st

            get_st = pb.task_network.add_subtask(
                get_jig_from_hangar,
                pb.object(jig_name),
                hangar_vars_delivers_n_gets[jig_name],
                trailer_vars_gets[jig_name],
            )
            putdown_st = pb.task_network.add_subtask(
                putdown_jig_on_rack,
                pb.object(jig_name), 
                trailer_vars_gets[jig_name],
                rack_vars_gets[jig_name],
                production_side,
                beluga_side,
                used_rack_size_vars_gets[jig_name],
                max_putdown_delay_vars_gets[jig_name],
            )
            all_gets.append((get_st, putdown_st))

            pb.task_network.add_constraint(up.LE(up.Minus(putdown_st.start, get_st.start), max_putdown_delay_vars_gets[jig_name]))

            pb.task_network.set_ordered(pickup_st, deliver_st, get_st, putdown_st)
 
    # # #

    is_noop_vars_swaps: dict[int, up.Parameter] = {}
    id_vars_swaps: dict[int, up.Parameter] = {}
    jig_vars_swaps: dict[int, up.Parameter] = {}
    rack1_vars_swaps: dict[int, up.Parameter] = {}
    rack2_vars_swaps: dict[int, up.Parameter] = {}
    trailer_vars_swaps: dict[int, up.Parameter] = {}
    side_vars_swaps: dict[int, up.Parameter] = {}
    used_rack_size_vars_swaps: dict[int, up.Parameter] = {}
    mid_timepoint_lb_vars_swaps: dict[int, up.Parameter] = {}
    mid_timepoint_ub_vars_swaps: dict[int, up.Parameter] = {}
    for id_val in range(num_available_swaps):
        is_noop_vars_swaps[id_val] = pb.task_network.add_variable(f"is_noop_swap{id_val}", up.BoolType())
        id_vars_swaps[id_val] = pb.task_network.add_variable(f"id_swap{id_val}", up.IntType(0, num_available_swaps))
        jig_vars_swaps[id_val] = pb.task_network.add_variable(f"j_swap{id_val}", jig_type)
        rack1_vars_swaps[id_val] = pb.task_network.add_variable(f"r1_swap{id_val}", rack_type)
        rack2_vars_swaps[id_val] = pb.task_network.add_variable(f"r2_swap{id_val}", rack_type)
        trailer_vars_swaps[id_val] = pb.task_network.add_variable(f"t_swap{id_val}", trailer_type)
        side_vars_swaps[id_val] = pb.task_network.add_variable(f"s_swap{id_val}", side_type)
        used_rack_size_vars_swaps[id_val] = pb.task_network.add_variable(f"rs_swap{id_val}", up.IntType(0, 1000))
        mid_timepoint_lb_vars_swaps[id_val] = pb.task_network.add_variable(f"mtp_lb_swap{id_val}", up.IntType(0, 1000))
        mid_timepoint_ub_vars_swaps[id_val] = pb.task_network.add_variable(f"mtp_ub_swap{id_val}", up.IntType(0, 1000))

    num_used_swaps = pb.task_network.add_variable("num_used_swaps", up.IntType(0, 1000))

    all_swaps: list[up_htn.Subtask] = []
    def add_swaps():
        """Adding a limited number of allowed swaps to the task network. Uniquely identifiable because of their ids' ordering"""
        prev_id_var = None
        for id_val in range(num_available_swaps):
            is_noop = is_noop_vars_swaps[id_val]
            id_var = id_vars_swaps[id_val]

            swap_st = pb.task_network.add_subtask(
                do_swap,
                is_noop,
                id_var,
                jig_vars_swaps[id_val],
                rack1_vars_swaps[id_val],
                rack2_vars_swaps[id_val],
                trailer_vars_swaps[id_val],
                side_vars_swaps[id_val],
                used_rack_size_vars_swaps[id_val],
                mid_timepoint_lb_vars_swaps[id_val],
                mid_timepoint_ub_vars_swaps[id_val],
            )
            all_swaps.append(swap_st)

            pb.task_network.add_constraint(
                up.Or(
                    up.And(up.LT(id_var, num_used_swaps), up.Not(is_noop)),
                    up.And(up.GE(id_var, num_used_swaps), is_noop),
                )
            )
            if id_val > 0:
                pb.task_network.add_constraint(up.LT(all_swaps[-2].start, all_swaps[-1].start))
                pb.task_network.add_constraint(up.LT(prev_id_var, id_var))
            prev_id_var = id_var

    # # #

    for flight_index in range(num_flights):
        last_unload_before_loads = add_unloading(flight_index)
        add_loading(flight_index, last_unload_before_loads)

    for production_line in pb_def.production_lines:
        add_delivering_and_getting(production_line)

    add_swaps()

    ##### Make metadata #####

    all_non_swap_subtasks = []
    for (unload_st, putdown_st) in all_unloads:
        all_non_swap_subtasks.append(unload_st)
        all_non_swap_subtasks.append(putdown_st)
    for (pickup_st, load_st) in all_loads:
        all_non_swap_subtasks.append(pickup_st)
        all_non_swap_subtasks.append(load_st)
    for (pickup_st, deliver_st) in all_delivers:
        all_non_swap_subtasks.append(pickup_st)
        all_non_swap_subtasks.append(deliver_st)
    for (get_st, putdown_st) in all_gets:
        all_non_swap_subtasks.append(get_st)
        all_non_swap_subtasks.append(putdown_st)
    for st in all_proceed_to_next_flight:
        all_non_swap_subtasks.append(st)

    pb_metadata = BelugaProblemMetadata(
        pb_def=pb_def,
        pb_unload_jig_from_beluga_to_trailer=unload_jig_from_beluga_to_trailer,
        pb_load_jig_from_trailer_to_beluga=load_jig_from_trailer_to_beluga,
        pb_putdown_jig_on_rack=putdown_jig_on_rack,
        pb_pickup_jig_from_rack=pickup_jig_from_rack,
        pb_deliver_jig_to_hangar=deliver_jig_to_hangar,
        pb_get_jig_from_hangar=get_jig_from_hangar,
        pb_proceed_to_next_flight=proceed_to_next_flight,
        pb_all_unloads=all_unloads,
        pb_all_loads=all_loads,
        pb_all_delivers=all_delivers,
        pb_all_gets=all_gets,
        pb_all_swaps=all_swaps,
        pb_all_proceed_to_next_flight=all_proceed_to_next_flight,
        pb_num_used_swaps=num_used_swaps,
        pb_all_non_swap_subtasks=all_non_swap_subtasks,
        rack_free_space_init={pb.object(rack.name): pb.explicit_initial_values[rack_free_space(pb.object(rack.name))] for rack in pb_def.racks},
        rack_size={pb.object(rack.name): pb.explicit_initial_values[rack_size(pb.object(rack.name))] for rack in pb_def.racks},
#        jigs_are_of_same_type={ (pb.object(jig1.name), pb.object(jig2.name)): pb.explicit_initial_values[jigs_are_of_same_type(pb.object(jig1.name), pb.object(jig2.name))]
#            for jig1 in pb_def.jigs for jig2 in pb_def.jigs
#        },
        rack_vars_unloads=rack_vars_unloads,
        rack_vars_loads=rack_vars_loads,
        rack_vars_delivers=rack_vars_delivers,
        rack_vars_gets=rack_vars_gets,
        rack1_vars_swaps=rack1_vars_swaps,
        rack2_vars_swaps=rack2_vars_swaps,
        used_rack_size_vars_unloads=used_rack_size_vars_unloads,
        used_rack_size_vars_gets=used_rack_size_vars_gets,
        jig_vars_swaps=jig_vars_swaps,
        used_rack_size_vars_swaps=used_rack_size_vars_swaps,
        max_putdown_delay_vars_unloads=max_putdown_delay_vars_unloads,
        max_putdown_delay_vars_gets=max_putdown_delay_vars_gets,
        _objects=pb.all_objects,
    )

    ##### End #####

    return pb, pb_metadata

@dataclass
class BelugaPlanProblemMatching:
    struct_vars_plan_assignments: dict[up.Parameter, ConstantExpression]
    struct_map_plan_action_to_subtask: dict[int, up_htn.Subtask | tuple[bool, up_htn.Subtask]]
    struct_map_plan_action_to_subtask_inv: dict[up_htn.Subtask | tuple[bool, up_htn.Subtask], int]
    pref_at_least_one_rack_always_empty: bool
    pref_rack_always_empty: dict[up.Object, bool]
    # pref_always_jigs_of_same_type_on_rack: dict[up.Object, bool]
    pref_max_rack_size_used_for_jig: dict[up.Object, int]
    pref_putdown_full_delay: dict[up.Object, int]
    pref_putdown_empty_delay: dict[up.Object, int]
    all_non_swap_subtasks_not_required_by_plan: list[up_htn.Subtask]

def analyse_reference_plan(
    plan_def: BelugaPlanDef,
    pb: up_htn.HierarchicalProblem,
    pb_metadata: BelugaProblemMetadata,
) -> BelugaPlanProblemMatching:

    pb_unload_jig_from_beluga_to_trailer = pb_metadata.pb_unload_jig_from_beluga_to_trailer
    pb_load_jig_from_trailer_to_beluga = pb_metadata.pb_load_jig_from_trailer_to_beluga
    pb_putdown_jig_on_rack = pb_metadata.pb_putdown_jig_on_rack
    pb_pickup_jig_from_rack = pb_metadata.pb_pickup_jig_from_rack
    pb_deliver_jig_to_hangar = pb_metadata.pb_deliver_jig_to_hangar
    pb_get_jig_from_hangar = pb_metadata.pb_get_jig_from_hangar
    pb_proceed_to_next_flight = pb_metadata.pb_proceed_to_next_flight
    pb_all_unloads = pb_metadata.pb_all_unloads
    pb_all_loads = pb_metadata.pb_all_loads
    pb_all_delivers = pb_metadata.pb_all_delivers
    pb_all_gets = pb_metadata.pb_all_gets
    pb_all_swaps = pb_metadata.pb_all_swaps
    pb_all_proceed_to_next_flight = pb_metadata.pb_all_proceed_to_next_flight
    pb_num_used_swaps = pb_metadata.pb_num_used_swaps

    struct_vars_plan_assignments: dict[up.Parameter, ConstantExpression] = {}
    struct_map_plan_action_to_subtask: dict[int, up_htn.Subtask | tuple[bool, up_htn.Subtask]] = {}
    struct_map_plan_action_to_subtask_inv: dict[up_htn.Subtask | tuple[bool, up_htn.Subtask], int] = {}

    ##### Match problem subtasks (+ parameters/variables) with plan actions (+ parameter/variable assignments) #####

    def insert(plan_action_index: int, subtask: up_htn.Subtask | tuple[bool, up_htn.Subtask]):
        assert plan_action_index not in struct_map_plan_action_to_subtask and subtask not in struct_map_plan_action_to_subtask_inv
        struct_map_plan_action_to_subtask[plan_action_index] = subtask
        struct_map_plan_action_to_subtask_inv[subtask] = plan_action_index

    def contains_plan_action(plan_action_index: int) -> bool:
        return plan_action_index in struct_map_plan_action_to_subtask
    
    def contains_subtask(subtask: up_htn.Subtask | tuple[bool, up_htn.Subtask]) -> bool:
        return subtask in struct_map_plan_action_to_subtask_inv

    def insert_var_assignment(var: up.Parameter, val: ConstantExpression):
        assert var not in struct_vars_plan_assignments
        struct_vars_plan_assignments[var] = val

#    def build_plan_subtask_order_constraints(self):
#        n = len(self._act_subt_map)
#        prev = None
#        for i in range(n):
#            v = self._act_subt_map[i]
#            if isinstance(v, up_htn.Subtask):
#                st = v
#                tp = st.start
#                if prev is not None:
#                    up.LE(prev, tp)
#                prev = tp
#            else:
#                assert isinstance(v, tuple)
#                swap_st: up_htn.Subtask = v[1]
#                tp = swap_st.start if v[0] == False else self._swap_aux_ts[swap_st]
#                if prev is not None:
#                    up.LE(prev, tp)
#                prev = tp

    (num_encountered_load, num_encountered_proceed_to_next_flight) = (0, 0)

    plan_len = len(plan_def)

    for k in range(plan_len):
        a_k = plan_def[k]

        if a_k.name == pb_unload_jig_from_beluga_to_trailer.name:
            for (unload_st, putdown_st) in pb_all_unloads:
                if (unload_st.parameters[0].object() == pb.object(a_k.params['j'])
                    and not contains_subtask(unload_st)
                ):
                    insert(k, unload_st)
                    for kk in range(k+1, plan_len):
                        a_kk = plan_def[kk]

                        if (a_kk.name == pb_putdown_jig_on_rack.name
                            and putdown_st.parameters[0].object() == pb.object(a_kk.params['j'])
                            and a_k.params['t'] == a_kk.params['t']
                        ):
                            insert(kk, putdown_st)
                            insert_var_assignment(putdown_st.parameters[1].parameter(), pb.object(a_k.params['t']))
                            insert_var_assignment(putdown_st.parameters[2].parameter(), pb.object(a_kk.params['r']))
                            insert_var_assignment(putdown_st.parameters[5].parameter(), pb_metadata.rack_size[pb.object(a_kk.params['r'])])
                            break
                    break

        elif a_k.name == pb_load_jig_from_trailer_to_beluga.name:
            (pickup_st, load_st) = pb_all_loads[num_encountered_load]
            insert(k, load_st)
            for kk in range(k-1, -1, -1):
                a_kk = plan_def[kk]

                if (a_kk.name == pb_pickup_jig_from_rack.name
                    and a_k.params['j'] == a_kk.params['j']
                    and a_k.params['t'] == a_kk.params['t']
                ):
                    insert(kk, pickup_st)
                    insert_var_assignment(pickup_st.parameters[0].parameter(), pb.object(a_k.params['j']))
                    insert_var_assignment(pickup_st.parameters[1].parameter(), pb.object(a_k.params['t']))
                    insert_var_assignment(pickup_st.parameters[2].parameter(), pb.object(a_kk.params['r']))
                    break
            num_encountered_load += 1

        elif a_k.name == pb_deliver_jig_to_hangar.name:
            for (pickup_st, deliver_st) in pb_all_delivers:
                if (deliver_st.parameters[0].object() == pb.object(a_k.params['j'])
                    and deliver_st.parameters[3].object() == pb.object(a_k.params['pl'])
                    and not contains_subtask(deliver_st)
                ):
                    insert(k, deliver_st)
                    for kk in range(k-1, -1, -1):
                        a_kk = plan_def[kk]
        
                        if (a_kk.name == pb_pickup_jig_from_rack.name
                            and pickup_st.parameters[0].object() == pb.object(a_kk.params['j'])
                            and a_k.params['t'] == a_kk.params['t']
                        ):
                            insert(kk, pickup_st)
                            insert_var_assignment(pickup_st.parameters[1].parameter(), pb.object(a_k.params['t']))
                            insert_var_assignment(pickup_st.parameters[2].parameter(), pb.object(a_kk.params['r']))
                            break
                    break

        elif a_k.name == pb_get_jig_from_hangar.name:
            for (get_st, putdown_st) in pb_all_gets:
                if (get_st.parameters[0].object() == pb.object(a_k.params['j'])
                    and not contains_subtask(get_st)
                ):
                    insert(k, get_st)
                    for kk in range(k+1, plan_len):
                        a_kk = plan_def[kk]

                        if (plan_def[kk].name == pb_putdown_jig_on_rack.name
                            and putdown_st.parameters[0].object() == pb.object(a_kk.params['j'])
                            and a_k.params['t'] == a_kk.params['t']
                        ):
                            insert(kk, putdown_st)
                            insert_var_assignment(putdown_st.parameters[1].parameter(), pb.object(a_k.params['t']))
                            insert_var_assignment(putdown_st.parameters[2].parameter(), pb.object(a_kk.params['r']))
                            insert_var_assignment(putdown_st.parameters[5].parameter(), pb_metadata.rack_size[pb.object(a_kk.params['r'])])
                            break
                    break

        elif a_k.name == pb_proceed_to_next_flight.name:
            insert(k, pb_all_proceed_to_next_flight[num_encountered_proceed_to_next_flight])
            num_encountered_proceed_to_next_flight += 1

        else:
            continue

    swap_id = 0
    for k in range(plan_len):
        a_k = plan_def[k]

        if a_k.name == pb_pickup_jig_from_rack.name and not contains_plan_action(k):
            for kk in range(k+1, plan_len):
                a_kk = plan_def[kk]
                if (not contains_plan_action(kk)
                    and a_kk.name == pb_putdown_jig_on_rack.name
                    and a_k.params['j'] == a_kk.params['j']
                    and a_k.params['t'] == a_kk.params['t']
                    and a_k.params['s'] == a_kk.params['s']
                ):
                    swap = pb.task_network.get_subtask(pb_all_swaps[swap_id].identifier)
                    insert(k, (False, swap))
                    insert(kk, (True, swap))

                    insert_var_assignment(swap.parameters[0].parameter(), up.FALSE())
                    insert_var_assignment(swap.parameters[1].parameter(), swap_id)
                    insert_var_assignment(swap.parameters[2].parameter(), pb.object(a_k.params['j']))
                    insert_var_assignment(swap.parameters[3].parameter(), pb.object(a_k.params['r']))
                    insert_var_assignment(swap.parameters[4].parameter(), pb.object(a_kk.params['r']))
                    insert_var_assignment(swap.parameters[5].parameter(), pb.object(a_k.params['t']))
                    insert_var_assignment(swap.parameters[6].parameter(), pb.object(a_k.params['s']))
                    insert_var_assignment(swap.parameters[7].parameter(), pb_metadata.rack_size[pb.object(a_kk.params['r'])])

                    swap_id += 1
                    break

    insert_var_assignment(pb_num_used_swaps, swap_id)

    # Assign the "is_noop" variable of the remaining / not used swaps to False
    for swap in pb_all_swaps:
        if (not contains_subtask((False, swap))
            and not contains_subtask((True, swap))
        ):
            insert_var_assignment(swap.parameters[0].parameter(), up.TRUE())

    #print(set(range(plan_len)).difference(plan_action_to_subtask_map.keys()))
    assert len(set(range(plan_len)).difference(struct_map_plan_action_to_subtask.keys())) == 0

    ##### Read values of preferences in the plan #####

    # size of largest rack onto which the same jig is placed

    pref_max_rack_size_used_for_jig = {}
    for j in pb_metadata.pb_def.jigs:
        jig_name = j.name
        jig = pb.object(jig_name)

        if pb.fluent("at")(jig) in pb.explicit_initial_values:
            jig_initially_at = pb.explicit_initial_values[pb.fluent("at")(jig)].object()
        else:
            jig_initially_at = None
        if jig_initially_at in pb_metadata.rack_size: # if the initial location of the jig is actually a rack
            pref_max_rack_size_used_for_jig[jig] = pb_metadata.rack_size[jig_initially_at] # type: ignore

        if jig_name in pb_metadata.used_rack_size_vars_unloads:
            val = struct_vars_plan_assignments.get(pb_metadata.used_rack_size_vars_unloads[jig_name], None)
            if val is not None:
                if jig not in pref_max_rack_size_used_for_jig: 
                    pref_max_rack_size_used_for_jig[jig] = val
                else:
                    pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig[jig])

        if jig_name in pb_metadata.used_rack_size_vars_gets:
            val = struct_vars_plan_assignments.get(pb_metadata.used_rack_size_vars_gets[jig_name], None)
            if val is not None:
                if jig not in pref_max_rack_size_used_for_jig: 
                    pref_max_rack_size_used_for_jig[jig] = val
                else:
                    pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig[jig])

        for id_swap in pb_metadata.used_rack_size_vars_swaps:
            jig_var_swap = pb_metadata.jig_vars_swaps[id_swap]
            if jig_var_swap in struct_vars_plan_assignments and struct_vars_plan_assignments[jig_var_swap] == jig_name:
                val = struct_vars_plan_assignments.get(jig_var_swap, None)
                if val is not None:
                    if jig_name not in pref_max_rack_size_used_for_jig: 
                        pref_max_rack_size_used_for_jig[jig] = val
                    else:
                        pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig[jig])

    # always jigs of same type on rack

    pref_jig_types_on_rack = {}

    for rack in pb_metadata.pb_def.racks:
        rack_name = rack.name
        rack = pb.object(rack_name)
        pref_jig_types_on_rack.setdefault(rack, set())

        initial_jig_type_on_rack: JigType | None = None # None when no jig initially on the rack
        for j in pb_metadata.pb_def.jigs:
            jig_name = j.name
            jig = pb.object(jig_name)
            jig_initially_at_rack = (pb.explicit_initial_values[pb.fluent("at")(jig)].object() == rack if pb.fluent("at")(jig) in pb.explicit_initial_values else False)
            if jig_initially_at_rack:
                initial_jig_type_on_rack = pb_metadata.pb_def.get_jig_type(pb_metadata.pb_def.get_jig(jig_name).type)
                if initial_jig_type_on_rack is not None:
                    pref_jig_types_on_rack[rack].add(initial_jig_type_on_rack.name)

    for jig_name, rack_var in pb_metadata.rack_vars_unloads.items():
        if rack_var in struct_vars_plan_assignments:
            rack = struct_vars_plan_assignments[rack_var]
            pref_jig_types_on_rack[rack].add(pb_metadata.pb_def.get_jig_type(pb_metadata.pb_def.get_jig(jig_name).type).name)

    for jig_name, rack_var in pb_metadata.rack_vars_gets.items():
        if rack_var in struct_vars_plan_assignments:
            rack = struct_vars_plan_assignments[rack_var]
            pref_jig_types_on_rack[rack].add(pb_metadata.pb_def.get_jig_type(pb_metadata.pb_def.get_jig(jig_name).type).name)

    for id_swap, rack_var in pb_metadata.rack2_vars_swaps.items():
        if rack_var in struct_vars_plan_assignments:
            rack = struct_vars_plan_assignments[rack_var]
            jig_name = struct_vars_plan_assignments[pb_metadata.jig_vars_swaps[id_swap]].name # type: ignore
            pref_jig_types_on_rack[rack].add(pb_metadata.pb_def.get_jig_type(pb_metadata.pb_def.get_jig(jig_name).type).name)

    pref_always_jigs_of_same_type_on_rack = { rack: True if len(jt) <= 1 else False for rack, jt in pref_jig_types_on_rack.items() }

    # rack always empty

    pref_rack_always_empty = {}
    
    for rack in pb_metadata.pb_def.racks:
        rack = pb.object(rack.name)
        if rack not in pref_always_jigs_of_same_type_on_rack or len(pref_jig_types_on_rack[rack]) == 0:
            pref_rack_always_empty[rack] = True
        else:
            pref_rack_always_empty[rack] = False

    # at least one rack always empty

    pref_at_least_one_rack_always_empty = True in pref_rack_always_empty.values()

    # # #

    all_non_swap_subtasks_not_required_by_plan=list(set(pb_metadata.pb_all_non_swap_subtasks).difference(struct_map_plan_action_to_subtask_inv.keys()))

    pbb = pb.clone()
    pbb.epsilon = 1

    struct_constrs = _make_plan_structural_constraints(
        struct_vars_plan_assignments,
        struct_map_plan_action_to_subtask,
        all_non_swap_subtasks_not_required_by_plan,
    )
    for c in struct_constrs:
        pbb.task_network.add_constraint(c)

    pll = solve_problem(pbb)

    # putdown delay (full jigs)

    pref_putdown_full_delay = {}

    for (unload_st, putdown_st) in pb_metadata.pb_all_unloads:
        (t1, unload_a) = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[unload_st.identifier]][0]
        (t2, putdown_a) = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[putdown_st.identifier]][0]
        jig = putdown_a.actual_parameters[0].object()
        pref_putdown_full_delay[jig] = (t2 - t1).numerator # WARNING we allow ourselves to do this because we ensure epsilon = 1
    
    # putdown delay (empty jigs)

    pref_putdown_empty_delay = {}

    for (get_st, putdown_st) in pb_metadata.pb_all_gets:
        (t1, get_a) = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[get_st.identifier]][0]
        (t2, putdown_a) = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[putdown_st.identifier]][0]
        # do not include jigs that are not required to be brought back in the reference plan ?
        if putdown_st.parameters[2].parameter() in struct_vars_plan_assignments:
            jig = putdown_a.actual_parameters[0].object()
            pref_putdown_empty_delay[jig] = (t2 - t1).numerator # WARNING we allow ourselves to do this because we ensure epsilon = 1
    
    # # #

    # print(at_least_one_rack_always_empty)
    # print(rack_always_empty)
    # print(always_jigs_of_same_type_on_rack)
    # print(max_rack_size_used_for_jig)
    # print(putdown_full_delay)
    # print(putdown_empty_delay)

    ##### End #####

    return BelugaPlanProblemMatching(
        struct_vars_plan_assignments,
        struct_map_plan_action_to_subtask,
        struct_map_plan_action_to_subtask_inv,
        pref_at_least_one_rack_always_empty,
        pref_rack_always_empty,
        # pref_always_jigs_of_same_type_on_rack,
        pref_max_rack_size_used_for_jig,
        pref_putdown_full_delay,
        pref_putdown_empty_delay,
        all_non_swap_subtasks_not_required_by_plan,
    )

def make_plan_structural_constraints(
    plan_problem_matching: BelugaPlanProblemMatching
) -> list[up.BoolExpression]:
    return _make_plan_structural_constraints(
        plan_problem_matching.struct_vars_plan_assignments,
        plan_problem_matching.struct_map_plan_action_to_subtask,
        plan_problem_matching.all_non_swap_subtasks_not_required_by_plan
    )

def _make_plan_structural_constraints(
    struct_vars_plan_assignments,
    struct_map_plan_action_to_subtask,
    all_non_swap_subtasks_not_required_by_plan,
) -> list[up.BoolExpression]:

    def make_total_order_constraints():
        constrs = []
        prev = None
        for _, v in sorted(struct_map_plan_action_to_subtask.items()):
            if isinstance(v, up_htn.Subtask):
                st: up_htn.Subtask = v
                if prev is not None:
                    constrs.append(up.LT(prev, st.start)) # FIXME LE/LT?
                prev = st.start
            elif isinstance(v, tuple):
                st: up_htn.Subtask = v[1]
                if prev is not None:
                    if v[0] == False:
                        constrs.append(up.LT(prev, st.start)) # FIXME LE/LT?
                        prev = st.start
                    else:
                        constrs.append(up.LT(prev, st.parameters[8].parameter()))
                        prev = st.parameters[9].parameter()
            else:
                assert False
        
        # Force actions that were not required by the reference plan (whose analysed structure we use in this function) to be after all the required ones.
        # This could be the case of actions that retrieve an empty jig to the beluga side, even though the jig does not need to be loaded into an outgoing Beluga.
        # Our model forces these actions to be there, but they are not required in the reference plans given to us.
        for st in all_non_swap_subtasks_not_required_by_plan:
            constrs.append(up.LT(prev, st.start))

        return constrs
    
    constrs = make_total_order_constraints()
    for var, val in struct_vars_plan_assignments.items():
        if var.type == up.BoolType():
            constrs.append(var if val == up.TRUE() else up.Not(var))
        else:
            constrs.append(up.Equals(var, val))
    
    return constrs
    

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
