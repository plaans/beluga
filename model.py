import sys
import os

import unified_planning.shortcuts as up
import unified_planning.model.htn as up_htn

from unified_planning.model.expression import ConstantExpression
from unified_planning.plans.hierarchical_plan import HierarchicalPlan

from parser import *

def serialize_problem(pb: up.Problem, filename: str):
    from unified_planning.grpc.proto_writer import ProtobufWriter
    writer = ProtobufWriter()
    msg = writer.convert(pb)
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "wb") as file:
        file.write(msg.SerializeToString())

def solve_problem(pb: up_htn.HierarchicalProblem, timeout:float|None) -> HierarchicalPlan: # type: ignore
    with up.OneshotPlanner(name="aries") as planner:
        result = planner.solve( # type: ignore
            pb,
            timeout=timeout,
            output_stream=sys.stdout,
        )
        plan = result.plan
    return plan

TASK_NAME_PREFIX = "t_"
METHOD_NAME_PREFIX = "m_"

class BelugaModel:

    def __init__(
        self,
        pb_def: BelugaProblemDef,
        name: str,
        num_available_swaps_margin: int,
        ref_plan_def: BelugaPlanDef | None,
    ):
        self.num_flights: int
        # # #
        self.pb: up_htn.HierarchicalProblem
        # # #
        self.side_type: up.Type
        self.side_beluga: up.Object
        self.side_production: up.Object
        self.side_opposite: up.Fluent
        # # #
        self.jig_type: up.Type
        self.jig_subtypes: dict[str, up.Type]
        self.jig_objects: dict[str, up.Object] = {}
        self.jig_size: up.Fluent
        self.jig_size_empty: up.Fluent
        self.jig_is_empty: up.Fluent
        # # #
        self.part_location_type: up.Type
        # # #
        self.rack_type: up.Type
        self.rack_free_space: up.Fluent
        self.rack_size: up.Fluent
        self.rack_objects: dict[str, up.Object] = {}
        # # #
        self.beluga_type: up.Type
        self.beluga_objects: dict[str, up.Object] = {}
        self.beluga_current: up.Fluent
        self.beluga_next: up.Fluent
        # # #
        self.hangar_type: up.Type
        self.hangar_free: up.Fluent
        self.hangar_objects: dict[str, up.Object] = {}
        # # #
        self.production_line_type: up.Type
        self.production_line_objects: dict[str, up.Object] = {}
        # # #
        self.trailer_type: up.Type
        self.trailer_available: up.Fluent
        self.trailer_side: up.Fluent
        self.trailer_free: up.Fluent
        self.trailer_objects: dict[str, up.Object] = {}
        # # #
        self.next_: up.Fluent
        self.at: up.Fluent
        self.pos: up.Fluent
        # # #
        self.proceed_to_next_flight: up.InstantaneousAction
        self.unload_jig_from_beluga_to_trailer: up.InstantaneousAction | up.DurativeAction
        self.load_jig_from_trailer_to_beluga: up.InstantaneousAction | up.DurativeAction
        self.putdown_jig_on_rack: up_htn.Task
        self.pickup_jig_from_rack: up.InstantaneousAction | up.DurativeAction
        self.deliver_jig_to_hangar: up.InstantaneousAction | up.DurativeAction
        self.get_jig_from_hangar: up_htn.Task
        self.do_swap: up_htn.Task
        # # #
        self.all_proceed_to_next_flight: list[up_htn.Subtask] = []
        self.all_unloads: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
        self.all_loads: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
        self.all_delivers: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
        self.all_gets: list[tuple[up_htn.Subtask, up_htn.Subtask]] = []
        self.all_swaps: list[up_htn.Subtask] = []
        self.all_non_swap_subtasks: list[up_htn.Subtask] = []
        # # #
        self.unloads_rack_vars: dict[str, up.Parameter] = {}
        self.unloads_trailer_vars: dict[str, up.Parameter] = {}
        self.unloads_used_rack_size_vars: dict[str, up.Parameter] = {}
        self.unloads_max_putdown_delay_vars: dict[str, up.Parameter] = {}
        self.unloads_is_noop_putdown_vars: dict[str, up.Parameter] = {}
        # # #
        self.loads_jig_vars: dict[tuple[str, int], up.Parameter] = {}
        self.loads_trailer_vars: dict[tuple[str, int], up.Parameter] = {}
        self.loads_rack_vars: dict[tuple[str, int], up.Parameter] = {}
        # # #
        self.delivers_trailer_vars: dict[str, up.Parameter] = {}
        self.delivers_rack_vars: dict[str, up.Parameter] = {}
        self.delivers_n_gets_hangar_vars: dict[str, up.Parameter] = {}
        self.gets_trailer_vars: dict[str, up.Parameter] = {}
        self.gets_rack_vars: dict[str, up.Parameter] = {}
        self.gets_used_rack_size_vars: dict[str, up.Parameter] = {}
        self.gets_max_putdown_delay_vars: dict[str, up.Parameter] = {}
        self.gets_is_noop_vars: dict[str, up.Parameter] = {}
        # # #
        self.num_used_swaps: up.Parameter
        # # #
        self.swaps_is_noop_vars: dict[int, up.Parameter] = {}
        #self.swaps_id_vars: dict[int, up.Parameter] = {}
        self.swaps_jig_vars: dict[int, up.Parameter] = {}
        self.swaps_rack1_vars: dict[int, up.Parameter] = {}
        self.swaps_rack2_vars: dict[int, up.Parameter] = {}
        self.swaps_trailer_vars: dict[int, up.Parameter] = {}
        self.swaps_side_vars: dict[int, up.Parameter] = {}
        self.swaps_used_rack_size_vars: dict[int, up.Parameter] = {}
        self.swaps_mid_timepoint_lb_vars: dict[int, up.Parameter] = {}
        self.swaps_mid_timepoint_ub_vars: dict[int, up.Parameter] = {}
        # # #

        self.pb_def = pb_def
        self.num_available_swaps = num_available_swaps_margin

        self.pb = up_htn.HierarchicalProblem(name)
        self.pb.epsilon = 1 # FIXME: ?? needed to later extract the difference between two timepoints as an int ??
        
        self._make_types_and_fluents_and_initial_values()

        self._make_tasks_and_actions_and_methods()

        self.num_flights = len(pb_def.flights)

        # make htn

        for flight in self.pb_def.flights[1:]:
            proceed_st = self.pb.task_network.add_subtask(self.proceed_to_next_flight, self.beluga_objects[flight.name])
            self.all_proceed_to_next_flight.append(proceed_st)
        self.pb.task_network.set_ordered(*self.all_proceed_to_next_flight)

        for flight_index in range(self.num_flights):
            last_unload_before_loads = self._make_htn_add_unloading(flight_index)
            self._make_htn_add_loading(flight_index, last_unload_before_loads)

        for production_line in self.pb_def.production_lines:
            self._make_htn_add_delivering_and_getting(production_line)

        if ref_plan_def is not None:
            num_swaps_used_in_ref_plan = self._get_number_of_swaps_in_reference_plan(ref_plan_def)
            self.num_available_swaps = num_swaps_used_in_ref_plan + num_available_swaps_margin

        self._make_htn_add_swaps()

        # # #

        for r in self.pb_def.racks:
            reif_c = reify_rack_always_empty(self, r.name)
            if r.name in self.pb_def.rack_always_empty:
                self.pb.task_network.add_constraint(reif_c) # FIXME? do this in rust or here ?

        reif_c = reify_at_least_one_rack_always_empty(self)
        if self.pb_def.use_at_least_one_rack_always_empty:
            self.pb.task_network.add_constraint(reif_c)

        for (jig_name, rs_ub) in self.pb_def.jig_always_placed_on_rack_size_leq:
            reif_c = reify_jig_always_placed_on_rack_shorter_or_same_size_as(self, jig_name, rs_ub)
            self.pb.task_network.add_constraint(reif_c) # FIXME? do this in rust or here ?

        if self.pb_def.val_num_swaps_used_leq is not None:
            reif_c = reify_num_swaps_used_leq(self, self.pb_def.val_num_swaps_used_leq)
            self.pb.task_network.add_constraint(reif_c) # FIXME? do this in rust or here ?

        # !!! TODO also add all "required tasks" and "properties" to a least / use some names to be able to find them in rust ?

    def solve(self, timeout:float|None=None) -> tuple[HierarchicalPlan, list[dict[str, str]]]:
        pl = solve_problem(self.pb, timeout)

        pl_as_json = []

        if pl is not None:
            for (_, a, _) in pl.action_plan.timed_actions:
                if a.action == self.unload_jig_from_beluga_to_trailer:
                    aa = { 
                        "name": a.action.name,
                        "j": a.actual_parameters[0].object().name,
                        "b": a.actual_parameters[1].object().name,
                        "t": a.actual_parameters[2].object().name,
                    }
                elif a.action == self.load_jig_from_trailer_to_beluga:
                    aa = { 
                        "name": a.action.name,
                        "j": a.actual_parameters[0].object().name,
                        "b": a.actual_parameters[1].object().name,
                        "t": a.actual_parameters[2].object().name,
                    }
                elif a.action == self.do_putdown_jig_on_rack:
                    aa = { 
                        "name": a.action.name,
                        "j": a.actual_parameters[0].object().name,
                        "t": a.actual_parameters[1].object().name,
                        "r": a.actual_parameters[2].object().name,
                        "s": a.actual_parameters[3].object().name,
                    }
                elif a.action == self.pickup_jig_from_rack:
                    aa = { 
                        "name": a.action.name,
                        "j": a.actual_parameters[0].object().name,
                        "t": a.actual_parameters[1].object().name,
                        "r": a.actual_parameters[2].object().name,
                        "s": a.actual_parameters[3].object().name,
                    }
                elif a.action == self.deliver_jig_to_hangar:
                    aa = { 
                        "name": a.action.name,
                        "j": a.actual_parameters[0].object().name,
                        "h": a.actual_parameters[1].object().name,
                        "t": a.actual_parameters[2].object().name,
                        "pl": a.actual_parameters[3].object().name,
                    }
                elif a.action == self.do_get_jig_from_hangar:
                    aa = { 
                        "name": a.action.name,
                        "j": a.actual_parameters[0].object().name,
                        "h": a.actual_parameters[1].object().name,
                        "t": a.actual_parameters[2].object().name,
                    }
                elif a.action == self.proceed_to_next_flight:
                    aa = { 
                        "name": a.action.name,
                    }
                else:
                    assert False
                
                pl_as_json.append(aa)

        return (pl, pl_as_json)

    def _make_types_and_fluents_and_initial_values(self):

        self.side_type = up.UserType("Side")
        self.side_beluga = self.pb.add_object("bside", self.side_type)
        self.side_production = self.pb.add_object("fside", self.side_type)
        self.side_opposite = self.pb.add_fluent("opposite", self.side_type, s=self.side_type)

        self.pb.set_initial_value(self.side_opposite(self.side_beluga), self.side_production)
        self.pb.set_initial_value(self.side_opposite(self.side_production), self.side_beluga)

        # # #

        self.jig_type = up.UserType("JigType")
        self.jig_subtypes = {}
        for jt in self.pb_def.jig_types:
            sub_type = up.UserType(jt.name, self.jig_type)
            self.jig_subtypes[jt.name] = sub_type
        self.jig_size = self.pb.add_fluent("jig_size", up.IntType(0, 1000), j=self.jig_type)
        self.jig_size_empty = self.pb.add_fluent("jig_size_empty", up.IntType(0, 1000), j=self.jig_type)
        self.jig_is_empty = self.pb.add_fluent("jig_is_empty", up.BoolType(), j=self.jig_type)

        for jig in self.pb_def.jigs:
            jig_obj = self.pb.add_object(jig.name, self.jig_subtypes[jig.type])
            tpe = self.pb_def.get_jig_type(jig.type)
            self.pb.set_initial_value(self.jig_size(jig_obj), tpe.size_empty if jig.empty else tpe.size_loaded)
            self.pb.set_initial_value(self.jig_size_empty(jig_obj), tpe.size_empty)
            self.pb.set_initial_value(self.jig_is_empty(jig_obj), up.Bool(jig.empty))
            self.jig_objects[jig.name] = jig_obj

    #    jigs_are_of_same_type = pb.add_fluent("jigs_are_of_same_type", up.BoolType(), j1=jig_type, j2=jig_type)
    #    for jig1 in pb_def.jigs:
    #        for jig2 in pb_def.jigs:
    #            pb.set_initial_value(jigs_are_of_same_type(pb.object(jig1.name), pb.object(jig2.name)), up.Bool(jig1.type == jig2.type))

        # # #

        self.part_location_type = up.UserType("PartLoc")

        # # #

        self.rack_type = up.UserType("Rack", father=self.part_location_type)
        self.rack_free_space = self.pb.add_fluent("rack_free_space", up.IntType(0, 1000), r=self.rack_type)
        self.rack_size = self.pb.add_fluent("rack_size", up.IntType(0, 1000), rack=self.rack_type)

        # # #

        self.beluga_type = up.UserType("Beluga", self.part_location_type)
        self.beluga_current = self.pb.add_fluent("current_beluga", self.beluga_type)
        self.beluga_next = self.pb.add_fluent("next_beluga", self.beluga_type, b=self.beluga_type)
        prev = None
        for i, beluga in enumerate(self.pb_def.flights):
            beluga_obj = self.pb.add_object(beluga.name, self.beluga_type)
            self.beluga_objects[beluga.name] = beluga_obj
            if i > 0:
                self.pb.set_initial_value(self.beluga_next(prev), beluga_obj)
            else:
                self.pb.set_initial_value(self.beluga_current(), beluga_obj)
            prev = beluga_obj

        # # #

        self.hangar_type = up.UserType("Hangar", father=self.part_location_type)
        self.hangar_free = self.pb.add_fluent("free_hangar", up.BoolType(), h=self.hangar_type)
        for hangar_name in self.pb_def.hangars:
            hangar_obj = self.pb.add_object(hangar_name, self.hangar_type)
            self.pb.set_initial_value(self.hangar_free(hangar_obj), True)
            self.hangar_objects[hangar_name] = hangar_obj

        # # #

        self.production_line_type = up.UserType("ProductionLine", self.part_location_type)
        for production_line in self.pb_def.production_lines:
            production_line_obj = self.pb.add_object(production_line.name, self.production_line_type)
            self.production_line_objects[production_line.name] = production_line_obj

        # # #

        self.trailer_type = up.UserType("Trailer", self.part_location_type)
        self.trailer_available = up.Fluent("available", up.BoolType(), t=self.trailer_type)
        self.pb.add_fluent(self.trailer_available, default_initial_value=True)
        self.trailer_side = self.pb.add_fluent("trailer_side", self.side_type, trailer=self.trailer_type)

        num_trailers_beluga = len(self.pb_def.trailers_beluga)
        num_trailers_production = len(self.pb_def.trailers_factory)

        self.trailer_free = self.pb.add_fluent("free_trailers", up.IntType(0,max(num_trailers_beluga, num_trailers_production)), side=self.side_type)
        self.pb.set_initial_value(self.trailer_free(self.side_beluga), num_trailers_beluga)
        self.pb.set_initial_value(self.trailer_free(self.side_production), num_trailers_production)

        for trailer_name in self.pb_def.trailers_beluga:
            trailer_obj = self.pb.add_object(trailer_name, self.trailer_type)
            self.pb.set_initial_value(self.trailer_side(trailer_obj), self.side_beluga)
            self.trailer_objects[trailer_name] = trailer_obj
        for trailer_name in self.pb_def.trailers_factory:
            trailer_obj = self.pb.add_object(trailer_name, self.trailer_type)
            self.pb.set_initial_value(self.trailer_side(trailer_obj), self.side_production)
            self.trailer_objects[trailer_name] = trailer_obj

        # # #

        self.at = self.pb.add_fluent("at", self.part_location_type, p=self.jig_type)
        self.next_ = up.Fluent("next", up.IntType(), r=self.rack_type, s=self.side_type)
        self.pb.add_fluent(self.next_, default_initial_value=0)
        self.pos = self.pb.add_fluent("pos", up.IntType(), p=self.jig_type, s=self.side_type)

        # # #

        for rack in self.pb_def.racks:
            rack_obj = self.pb.add_object(rack.name, self.rack_type)
            self.rack_objects[rack.name] = rack_obj

            num_pieces = len(rack.jigs)
            occupied_space = 0
            for k, jig_name in enumerate(rack.jigs):
                jig = self.pb_def.get_jig(jig_name)
                pb_def_jig_type = self.pb_def.get_jig_type(jig.type)
                jig_size_val = pb_def_jig_type.size_empty if jig.empty else pb_def_jig_type.size_loaded
                occupied_space += jig_size_val
                jig_obj = self.jig_objects[jig_name]

                self.pb.set_initial_value(self.pos(jig_obj, self.side_beluga), k)
                self.pb.set_initial_value(self.pos(jig_obj, self.side_production), -k)
                self.pb.set_initial_value(self.at(jig_obj), rack_obj)

            self.pb.set_initial_value(self.rack_free_space(rack_obj), rack.size - occupied_space)
            self.pb.set_initial_value(self.next_(rack_obj, self.side_production), -num_pieces+1)
            self.pb.set_initial_value(self.rack_size(rack_obj), rack.size)

        # # #

        for beluga in self.pb_def.flights:
            beluga_obj = self.beluga_objects[beluga.name]
            for _, jig_name in beluga.incoming.items():
                jig_obj = self.jig_objects[jig_name]
                self.pb.set_initial_value(self.at(jig_obj), beluga_obj)

    def _make_tasks_and_actions_and_methods(self):

        # # #

        def load_to_trailer(a: up.InstantaneousAction, jig, trailer, side):
            a.add_precondition(up.Equals(self.trailer_side(trailer), side))
            a.add_precondition(self.trailer_available(trailer))
            a.add_effect(self.trailer_available(trailer), False)
            a.add_effect(self.at(jig), trailer)

        def unload_from_trailer(a: up.InstantaneousAction, jig, trailer, side):
            a.add_precondition(up.Equals(self.trailer_side(trailer), side))
            a.add_precondition(up.Not(self.trailer_available(trailer))) # actually not needed ?
            a.add_effect(self.trailer_available(trailer), True)
            a.add_precondition(up.Equals(self.at(jig), trailer))

        def to_rack(a: up.InstantaneousAction, jig, rack, side, oside):
            a.add_decrease_effect(self.rack_free_space(rack), self.jig_size(jig))
            a.add_decrease_effect(self.next_(rack, side), 1)
            a.add_effect(self.pos(jig, side), self.next_(rack, side)-1)
            a.add_effect(self.pos(jig, oside), -self.next_(rack, side)+1)
            a.add_effect(self.at(jig), rack)

        def from_rack(a: up.InstantaneousAction, jig, rack, side, oside):
            a.add_increase_effect(self.rack_free_space(rack), self.jig_size(jig))
            a.add_precondition(up.Equals(self.next_(rack, side), self.pos(jig, side)))
            a.add_increase_effect(self.next_(rack, side), 1)
            a.add_precondition(up.Equals(self.at(jig), rack))

        # # #

        self.unload_jig_from_beluga_to_trailer = up.InstantaneousAction(
            "unload_beluga",
            j=self.jig_type,
            b=self.beluga_type,
            t=self.trailer_type,
        )
        load_to_trailer(
            self.unload_jig_from_beluga_to_trailer,
            self.unload_jig_from_beluga_to_trailer.j,
            self.unload_jig_from_beluga_to_trailer.t,
            self.side_beluga,
        )
        self.unload_jig_from_beluga_to_trailer.add_precondition(
            up.Equals(
                self.at(self.unload_jig_from_beluga_to_trailer.j),
                self.unload_jig_from_beluga_to_trailer.b,
            ),
        )
        self.pb.add_action(self.unload_jig_from_beluga_to_trailer)

        # # #

        self.load_jig_from_trailer_to_beluga = up.InstantaneousAction(
            "load_beluga",
            j=self.jig_type,
            b=self.beluga_type,
            t=self.trailer_type,
        )
        unload_from_trailer(
            self.load_jig_from_trailer_to_beluga,
            self.load_jig_from_trailer_to_beluga.j,
            self.load_jig_from_trailer_to_beluga.t,
            self.side_beluga,
        )
        self.load_jig_from_trailer_to_beluga.add_effect(
            self.at(self.load_jig_from_trailer_to_beluga.j),
            self.load_jig_from_trailer_to_beluga.b,
        )
        self.load_jig_from_trailer_to_beluga.add_precondition(
            self.jig_is_empty(self.load_jig_from_trailer_to_beluga.j),
        )
        self.pb.add_action(self.load_jig_from_trailer_to_beluga)

        # # #

        self.do_putdown_jig_on_rack = up.InstantaneousAction(
            "put_down_rack",
            j=self.jig_type,
            t=self.trailer_type, 
            r=self.rack_type,
            s=self.side_type,
            os=self.side_type,
            rs=up.IntType(0, 1000),
            d=up.IntType(0, 1000),
        )
        unload_from_trailer(
            self.do_putdown_jig_on_rack,
            self.do_putdown_jig_on_rack.j,
            self.do_putdown_jig_on_rack.t,
            self.do_putdown_jig_on_rack.s,
        )
        to_rack(
            self.do_putdown_jig_on_rack,
            self.do_putdown_jig_on_rack.j,
            self.do_putdown_jig_on_rack.r,
            self.do_putdown_jig_on_rack.s,
            self.do_putdown_jig_on_rack.os,
        )
        self.do_putdown_jig_on_rack.add_precondition(
            up.Equals(self.rack_size(self.do_putdown_jig_on_rack.r), self.do_putdown_jig_on_rack.rs),
        )
        self.pb.add_action(self.do_putdown_jig_on_rack)

        # # #

        self.putdown_jig_on_rack = self.pb.add_task(
            TASK_NAME_PREFIX+"put_down_rack",
            j=self.jig_type,
            t=self.trailer_type, 
            r=self.rack_type,
            s=self.side_type,
            os=self.side_type,
            rs=up.IntType(0, 1000),
            d=up.IntType(0, 1000),
            is_noop=up.BoolType(),
        )
        m1 = up_htn.Method(
            METHOD_NAME_PREFIX+"put_down_rack_noop",
            j=self.jig_type,
            t=self.trailer_type, 
            r=self.rack_type,
            s=self.side_type,
            os=self.side_type,
            rs=up.IntType(0, 1000),
            d=up.IntType(0, 1000),
            is_noop=up.BoolType(),
        )
        m1.set_task(self.putdown_jig_on_rack)
        m1.add_constraint(m1.is_noop)
        self.pb.add_method(m1)

        m2 = up_htn.Method(
            METHOD_NAME_PREFIX+"put_down_rack_do",
            j=self.jig_type,
            t=self.trailer_type, 
            r=self.rack_type,
            s=self.side_type,
            os=self.side_type,
            rs=up.IntType(0, 1000),
            d=up.IntType(0, 1000),
            is_noop=up.BoolType(),
        )
        m2.set_task(self.putdown_jig_on_rack)
        m2.add_constraint(up.Not(m2.is_noop))
        m2.add_subtask(self.do_putdown_jig_on_rack, m2.j, m2.t, m2.r, m2.s, m2.os, m2.rs, m2.d)
        self.pb.add_method(m2)

        # # #

        self.pickup_jig_from_rack = up.InstantaneousAction(
            "pick_up_rack", 
            j=self.jig_type,
            t=self.trailer_type,
            r=self.rack_type,
            s=self.side_type,
            os=self.side_type,
        )
        from_rack(
            self.pickup_jig_from_rack,
            self.pickup_jig_from_rack.j,
            self.pickup_jig_from_rack.r,
            self.pickup_jig_from_rack.s,
            self.pickup_jig_from_rack.os,
        )
        load_to_trailer(
            self.pickup_jig_from_rack,
            self.pickup_jig_from_rack.j,
            self.pickup_jig_from_rack.t,
            self.pickup_jig_from_rack.s,
        )
        self.pb.add_action(self.pickup_jig_from_rack)

        # # #

        self.deliver_jig_to_hangar = up.InstantaneousAction(
            "deliver_to_hangar",
            j=self.jig_type,
            h=self.hangar_type,
            t=self.trailer_type, 
            pl=self.production_line_type,
        )
        unload_from_trailer(
            self.deliver_jig_to_hangar,
            self.deliver_jig_to_hangar.j,
            self.deliver_jig_to_hangar.t,
            self.side_production,
        )
        self.deliver_jig_to_hangar.add_precondition(self.hangar_free(self.deliver_jig_to_hangar.h))
        self.deliver_jig_to_hangar.add_effect(self.hangar_free(self.deliver_jig_to_hangar.h), False)
        self.deliver_jig_to_hangar.add_effect(
            self.at(self.deliver_jig_to_hangar.j),
            self.deliver_jig_to_hangar.h,
        )
        self.deliver_jig_to_hangar.add_effect(
            self.jig_size(self.deliver_jig_to_hangar.j),
            self.jig_size_empty(self.deliver_jig_to_hangar.j),
        )
        self.deliver_jig_to_hangar.add_effect(
            self.jig_is_empty(self.deliver_jig_to_hangar.j),
            up.TRUE(),
        )
        self.pb.add_action(self.deliver_jig_to_hangar)

        # # #

        self.do_get_jig_from_hangar = up.InstantaneousAction(
            "get_from_hangar",
            j=self.jig_type,
            h=self.hangar_type,
            t=self.trailer_type,
        )
        load_to_trailer(
            self.do_get_jig_from_hangar,
            self.do_get_jig_from_hangar.j,
            self.do_get_jig_from_hangar.t,
            self.side_production
        )
        self.do_get_jig_from_hangar.add_effect(self.hangar_free(self.do_get_jig_from_hangar.h), True)
        self.do_get_jig_from_hangar.add_precondition(
            up.Equals(self.at(self.do_get_jig_from_hangar.j), self.do_get_jig_from_hangar.h),
        )
        self.pb.add_action(self.do_get_jig_from_hangar)

        # # #

        self.get_jig_from_hangar = self.pb.add_task(
            TASK_NAME_PREFIX+"get_from_hangar",
            j=self.jig_type,
            h=self.hangar_type,
            t=self.trailer_type,
            is_noop=up.BoolType(),
        )
        m1 = up_htn.Method(
            METHOD_NAME_PREFIX+"get_from_hangar_noop",
            j=self.jig_type,
            h=self.hangar_type,
            t=self.trailer_type,
            is_noop=up.BoolType(),
        )
        m1.set_task(self.get_jig_from_hangar)
        m1.add_constraint(m1.is_noop)
        self.pb.add_method(m1)

        m2 = up_htn.Method(
            METHOD_NAME_PREFIX+"get_from_hangar_do",
            j=self.jig_type,
            h=self.hangar_type,
            t=self.trailer_type,
            is_noop=up.BoolType(),
        )
        m2.set_task(self.get_jig_from_hangar)
        m2.add_constraint(up.Not(m2.is_noop))
        m2.add_subtask(self.do_get_jig_from_hangar, m2.j, m2.h, m2.t)
        self.pb.add_method(m2)

        # # #

        self.proceed_to_next_flight = up.InstantaneousAction("switch_to_next_beluga", b=self.beluga_type)
        self.proceed_to_next_flight.add_precondition(up.Equals(self.beluga_next(self.beluga_current()), self.proceed_to_next_flight.b))
        self.proceed_to_next_flight.add_effect(self.beluga_current(), self.proceed_to_next_flight.b)
        self.pb.add_action(self.proceed_to_next_flight)

        # # #

        self.do_swap = self.pb.add_task(
            TASK_NAME_PREFIX+"swap",
            is_noop=up.BoolType(),
            id_=up.IntType(0, 1000),
            j=self.jig_type,
            r1=self.rack_type,
            r2=self.rack_type,
            t=self.trailer_type,
            side=self.side_type,
            rs=up.IntType(0, 1000),
            mtp_lb=up.IntType(0, 1000),
            mtp_ub=up.IntType(0, 1000),
        )
        m1 = up_htn.Method(
            METHOD_NAME_PREFIX+"swap_noop",
            is_noop=up.BoolType(),
            id_=up.IntType(0, 1000),
            j=self.jig_type,
            r1=self.rack_type,
            r2=self.rack_type,
            t=self.trailer_type,
            side=self.side_type,
            rs=up.IntType(0, 1000),
            mtp_lb=up.IntType(0, 1000),
            mtp_ub=up.IntType(0, 1000),
        )
        m1.set_task(self.do_swap)
        m1.add_constraint(m1.is_noop)
        self.pb.add_method(m1)

        m2 = up_htn.Method(
            METHOD_NAME_PREFIX+"swap_do",
            is_noop=up.BoolType(),
            id_=up.IntType(0, 1000),
            j=self.jig_type,
            r1=self.rack_type,
            r2=self.rack_type,
            t=self.trailer_type,
            side=self.side_type,
            oside=self.side_type,
            rs=up.IntType(0, 1000),
            mtp_lb=up.IntType(0, 1000),
            mtp_ub=up.IntType(0, 1000),
        )
        m2.set_task(self.do_swap)
        m2.add_constraint(up.Not(m2.is_noop))
        swap_1half = m2.add_subtask(self.pickup_jig_from_rack, m2.j, m2.t, m2.r1, m2.side, m2.oside)
        swap_2half = m2.add_subtask(self.do_putdown_jig_on_rack, m2.j, m2.t, m2.r2, m2.side, m2.oside, m2.rs, 0)
        m2.set_ordered(swap_1half, swap_2half)
        m2.add_constraint(up.LE(swap_1half.end, m2.mtp_lb))
        m2.add_constraint(up.LE(m2.mtp_lb, swap_2half.start))
        m2.add_constraint(up.LE(swap_2half.start, m2.mtp_ub))
        m2.add_constraint(up.LE(m2.mtp_ub, swap_2half.end))
        self.pb.add_method(m2)

    def _get_number_of_swaps_in_reference_plan(self, plan_def: BelugaPlanDef):

        seen = set()

        (num_encountered_load, num_encountered_proceed_to_next_flight) = (0, 0)

        plan_len = len(plan_def)

        for k in range(plan_len):
            a_k = plan_def[k]

            if a_k.name == self.unload_jig_from_beluga_to_trailer.name:
                for (unload_st, putdown_st) in self.all_unloads:
                    if (unload_st.parameters[0].object() == self.jig_objects[a_k.params['j']]
                        and not k in seen
                    ):
                        seen.add(k)
                        for l in range(k+1, plan_len):
                            a_l = plan_def[l]
                            if (TASK_NAME_PREFIX+a_l.name == self.putdown_jig_on_rack.name
                                and putdown_st.parameters[0].object() == self.jig_objects[a_l.params['j']]
                                and a_k.params['t'] == a_l.params['t']
                            ):
                                seen.add(l)
                                break
                        break

            elif a_k.name == self.load_jig_from_trailer_to_beluga.name:
                (pickup_st, load_st) = self.all_loads[num_encountered_load]
                seen.add(k)
                for l in range(k-1, -1, -1):
                    a_l = plan_def[l]

                    if (a_l.name == self.pickup_jig_from_rack.name
                        and a_k.params['j'] == a_l.params['j']
                        and a_k.params['t'] == a_l.params['t']
                    ):
                        seen.add(l)
                        break
                num_encountered_load += 1

            elif a_k.name == self.deliver_jig_to_hangar.name:
                for (pickup_st, deliver_st) in self.all_delivers:
                    if (deliver_st.parameters[0].object() == self.jig_objects[a_k.params['j']]
                        and deliver_st.parameters[3].object() == self.production_line_objects[a_k.params['pl']]
                        and not k in seen
                    ):
                        seen.add(k)
                        for l in range(k-1, -1, -1):
                            a_l = plan_def[l]
            
                            if (a_l.name == self.pickup_jig_from_rack.name
                                and pickup_st.parameters[0].object() == self.jig_objects[a_l.params['j']]
                                and a_k.params['t'] == a_l.params['t']
                            ):
                                seen.add(l)
                                break
                        break

            elif TASK_NAME_PREFIX+a_k.name == self.get_jig_from_hangar.name:
                for (get_st, putdown_st) in self.all_gets:
                    if (get_st.parameters[0].object() == self.jig_objects[a_k.params['j']]
                        and not k in seen
                    ):
                        seen.add(k)
                        for l in range(k+1, plan_len):
                            a_l = plan_def[l]

                            if (TASK_NAME_PREFIX+a_l.name == self.putdown_jig_on_rack.name
                                and putdown_st.parameters[0].object() == self.jig_objects[a_l.params['j']]
                                and a_k.params['t'] == a_l.params['t']
                            ):
                                seen.add(l)
                                break
                        break

            elif a_k.name == self.proceed_to_next_flight.name:
                seen.add(k)
                num_encountered_proceed_to_next_flight += 1

            else:
                continue

        num_swaps = 0
        for k in range(plan_len):
            if plan_def[k].name == self.pickup_jig_from_rack.name and not k in seen:
                num_swaps += 1

        return num_swaps

    def _make_htn_add_unloading(self, flights_index: int) -> up_htn.Subtask | None:

        flights = self.pb_def.flights[flights_index]

        if len(flights.incoming) == 0:
            return None

        prev_unload_st = None
        for _, jig_name in flights.incoming.items():

            self.unloads_rack_vars[jig_name] = self.pb.task_network.add_variable(f"r_{jig_name}_1", self.rack_type)
            self.unloads_trailer_vars[jig_name] = self.pb.task_network.add_variable(f"t_{jig_name}_1", self.trailer_type)
            self.unloads_used_rack_size_vars[jig_name] = self.pb.task_network.add_variable(f"rs_{jig_name}_1", up.IntType(0, 1000))
            self.unloads_max_putdown_delay_vars[jig_name] = self.pb.task_network.add_variable(f"md_{jig_name}_1", up.IntType(0, 1000))
            self.unloads_is_noop_putdown_vars[jig_name] = self.pb.task_network.add_variable(f"is_noop_{jig_name}_1", up.BoolType())

            unload_st = self.pb.task_network.add_subtask(
                self.unload_jig_from_beluga_to_trailer,
                self.jig_objects[jig_name],
                self.beluga_objects[flights.name],
                self.unloads_trailer_vars[jig_name],
            )
            putdown_st = self.pb.task_network.add_subtask(
                self.putdown_jig_on_rack,
                self.jig_objects[jig_name],
                self.unloads_trailer_vars[jig_name],
                self.unloads_rack_vars[jig_name],
                self.side_beluga,
                self.side_production,
                self.unloads_used_rack_size_vars[jig_name],
                self.unloads_max_putdown_delay_vars[jig_name],
                self.unloads_is_noop_putdown_vars[jig_name],
            )
            self.all_unloads.append((unload_st, putdown_st))
            self.all_non_swap_subtasks.append(unload_st)
            self.all_non_swap_subtasks.append(putdown_st)

            self.pb.task_network.add_constraint(up.LE(up.Minus(putdown_st.start, unload_st.start), self.unloads_max_putdown_delay_vars[jig_name]))

            self.pb.task_network.set_ordered(unload_st, putdown_st)

            if flights_index > 0:
                self.pb.task_network.add_constraint(up.LT(self.all_proceed_to_next_flight[flights_index-1].end, unload_st.start))
            if flights_index < self.num_flights-1:
                self.pb.task_network.add_constraint(up.LT(unload_st.end, self.all_proceed_to_next_flight[flights_index].start))

            if prev_unload_st is not None:
                self.pb.task_network.add_constraint(up.LT(prev_unload_st.end, unload_st.start))
            prev_unload_st = unload_st

        return unload_st

    def _make_htn_add_loading(self, flights_index: int, last_unload_before_loads):
    
        flights = self.pb_def.flights[flights_index]
        if len(flights.outgoing) == 0:
            return

        flight_name = flights.name
        prev_load_st = None
        for i, jig_type_name in flights.outgoing.items():

            self.loads_jig_vars[(flights.name, i)] = self.pb.task_network.add_variable(f"jig_{flights.name}_{i}", self.jig_subtypes[jig_type_name])
            self.loads_trailer_vars[(flights.name, i)] = self.pb.task_network.add_variable(f"t_{flights.name}_{i}", self.trailer_type)
            self.loads_rack_vars[(flights.name, i)] = self.pb.task_network.add_variable(f"r_{flights.name}_{i}", self.rack_type)

            if jig_type_name.startswith("jig"):
                self.pb.task_network.add_constraint(up.Equals(self.loads_jig_vars[(flights.name, i)], self.jig_objects[jig_type_name]))
                # FIXME TODO: ^ will have to be put in a conjunction ("and") together with the acomplishment of the task, to represent the property of achieving this spec (loading)
            else:
                assert jig_type_name.startswith("type")

            pickup_st = self.pb.task_network.add_subtask(
                self.pickup_jig_from_rack,
                self.loads_jig_vars[(flight_name, i)],
                self.loads_trailer_vars[(flight_name, i)],
                self.loads_rack_vars[(flight_name, i)],
                self.side_beluga,
                self.side_production,
            )
            load_st = self.pb.task_network.add_subtask(
                self.load_jig_from_trailer_to_beluga, 
                self.loads_jig_vars[(flight_name, i)], 
                self.beluga_objects[flight_name], 
                self.loads_trailer_vars[(flight_name, i)],
            )
            self.all_loads.append((pickup_st, load_st))
            self.all_non_swap_subtasks.append(pickup_st)
            self.all_non_swap_subtasks.append(load_st)

            # vvv WARNING vvv
            # if i == 0 and last_unload_before_loads is not None:
            #     self.pb.task_network.set_ordered(last_unload_before_loads, load_st)
            # ^^^ WARNING ^^^ LOADS ARE ALLOWED TO BE MADE BEFORE ALL UNLOADS ARE FINISHED, SO THIS IS COMMENTED OUT

            self.pb.task_network.set_ordered(pickup_st, load_st)

            if flights_index > 0:
                self.pb.task_network.add_constraint(up.LT(self.all_proceed_to_next_flight[flights_index-1].end, load_st.start))
            if flights_index < self.num_flights-1:
                self.pb.task_network.add_constraint(up.LT(load_st.end, self.all_proceed_to_next_flight[flights_index].start))

            if prev_load_st is not None:
                self.pb.task_network.add_constraint(up.LT(prev_load_st.end, load_st.start))
            prev_load_st = load_st

    def _make_htn_add_delivering_and_getting(self, production_line: ProductionLine):

        prev_deliver = None
        for (_, jig_name) in sorted(production_line.schedule.items()):

            self.delivers_trailer_vars[jig_name] = self.pb.task_network.add_variable(f"t_{jig_name}_2a", self.trailer_type)
            self.delivers_rack_vars[jig_name] = self.pb.task_network.add_variable(f"r_{jig_name}_2a", self.rack_type)
            self.delivers_n_gets_hangar_vars[jig_name] = self.pb.task_network.add_variable(f"h_{jig_name}_2", self.hangar_type)
            self.gets_trailer_vars[jig_name] = self.pb.task_network.add_variable(f"t_{jig_name}_2b", self.trailer_type)
            self.gets_rack_vars[jig_name] = self.pb.task_network.add_variable(f"r_{jig_name}_2b", self.rack_type)
            self.gets_used_rack_size_vars[jig_name] = self.pb.task_network.add_variable(f"rs_{jig_name}_2b", up.IntType(0, 1000))
            self.gets_max_putdown_delay_vars[jig_name] = self.pb.task_network.add_variable(f"md_{jig_name}_2b", up.IntType(0, 1000))
            self.gets_is_noop_vars[jig_name] = self.pb.task_network.add_variable(f"is_noop_{jig_name}_2b", up.BoolType())

            pickup_st = self.pb.task_network.add_subtask(
                self.pickup_jig_from_rack,
                self.jig_objects[jig_name],
                self.delivers_trailer_vars[jig_name],
                self.delivers_rack_vars[jig_name],
                self.side_production,
                self.side_beluga,
            )
            deliver_st = self.pb.task_network.add_subtask(
                self.deliver_jig_to_hangar,
                self.jig_objects[jig_name],
                self.delivers_n_gets_hangar_vars[jig_name],
                self.delivers_trailer_vars[jig_name],
                self.production_line_objects[production_line.name],
            )
            self.all_delivers.append((pickup_st, deliver_st))
            self.all_non_swap_subtasks.append(pickup_st)
            self.all_non_swap_subtasks.append(deliver_st)

            if prev_deliver is not None:
                self.pb.task_network.add_constraint(up.LT(prev_deliver.start, deliver_st.start))
#                self.pb.task_network.add_constraint(up.LE(prev_deliver.end, deliver_st.end))
##                self.pb.task_network.add_constraint(up.LE(prev_deliver.end, deliver_st.start))
            prev_deliver = deliver_st

            get_st = self.pb.task_network.add_subtask(
                self.get_jig_from_hangar,
                self.jig_objects[jig_name],
                self.delivers_n_gets_hangar_vars[jig_name],
                self.gets_trailer_vars[jig_name],
                # self.gets_is_noop_vars[jig_name],
                up.FALSE(),
            )
            putdown_st = self.pb.task_network.add_subtask(
                self.putdown_jig_on_rack,
                self.jig_objects[jig_name], 
                self.gets_trailer_vars[jig_name],
                self.gets_rack_vars[jig_name],
                self.side_production,
                self.side_beluga,
                self.gets_used_rack_size_vars[jig_name],
                self.gets_max_putdown_delay_vars[jig_name],
                self.gets_is_noop_vars[jig_name],
            )
            self.all_gets.append((get_st, putdown_st))
            self.all_non_swap_subtasks.append(get_st)
            self.all_non_swap_subtasks.append(putdown_st)

            self.pb.task_network.add_constraint(up.LE(up.Minus(putdown_st.start, get_st.start), self.gets_max_putdown_delay_vars[jig_name]))

            self.pb.task_network.set_ordered(pickup_st, deliver_st, get_st, putdown_st)

    def _make_htn_add_swaps(self):
        """Adding a limited number of allowed swaps to the task network. Uniquely identifiable because of their ids' ordering"""

        self.num_used_swaps = self.pb.task_network.add_variable("num_used_swaps", up.IntType(0, self.num_available_swaps))

        # prev_id_var = None
        # for i, id_val in enumerate(range(num_available_swaps)):
        for id_val in range(self.num_available_swaps):

            self.swaps_is_noop_vars[id_val] = self.pb.task_network.add_variable(f"is_noop_swap{id_val}", up.BoolType())
            #self.swaps_id_vars[id_val] = self.pb.task_network.add_variable(f"id_swap{id_val}", up.IntType(0, self.num_available_swaps))
            self.swaps_jig_vars[id_val] = self.pb.task_network.add_variable(f"j_swap{id_val}", self.jig_type)
            self.swaps_rack1_vars[id_val] = self.pb.task_network.add_variable(f"r1_swap{id_val}", self.rack_type)
            self.swaps_rack2_vars[id_val] = self.pb.task_network.add_variable(f"r2_swap{id_val}", self.rack_type)
            self.swaps_trailer_vars[id_val] = self.pb.task_network.add_variable(f"t_swap{id_val}", self.trailer_type)
            self.swaps_side_vars[id_val] = self.pb.task_network.add_variable(f"s_swap{id_val}", self.side_type)
            self.swaps_used_rack_size_vars[id_val] = self.pb.task_network.add_variable(f"rs_swap{id_val}", up.IntType(0, 1000))
            self.swaps_mid_timepoint_lb_vars[id_val] = self.pb.task_network.add_variable(f"mtp_lb_swap{id_val}", up.IntType(0, 1000))
            self.swaps_mid_timepoint_ub_vars[id_val] = self.pb.task_network.add_variable(f"mtp_ub_swap{id_val}", up.IntType(0, 1000))

            swap_st = self.pb.task_network.add_subtask(
                self.do_swap,
                self.swaps_is_noop_vars[id_val],
                # id_vars_swaps[id_val],
                id_val,
                self.swaps_jig_vars[id_val],
                self.swaps_rack1_vars[id_val],
                self.swaps_rack2_vars[id_val],
                self.swaps_trailer_vars[id_val],
                self.swaps_side_vars[id_val],
                self.swaps_used_rack_size_vars[id_val],
                self.swaps_mid_timepoint_lb_vars[id_val],
                self.swaps_mid_timepoint_ub_vars[id_val],
            )
            self.all_swaps.append(swap_st)

            self.pb.task_network.add_constraint(
                up.Or(
                    # up.And(up.LT(id_var, self.num_used_swaps), up.Not(self.swaps_is_noop_vars[id_val])),
                    # up.And(up.GE(id_var, self.num_used_swaps), self.swaps_is_noop_vars[id_val]),
                    up.And(up.LT(id_val, self.num_used_swaps), up.Not(self.swaps_is_noop_vars[id_val])),
                    up.And(up.GE(id_val, self.num_used_swaps), self.swaps_is_noop_vars[id_val]),
                )
            )
            if id_val > 0:
                self.pb.task_network.add_constraint(up.LT(self.all_swaps[-2].start, self.all_swaps[-1].start))
            #     self.pb.task_network.add_constraint(up.LT(prev_id_var, id_var))
            # prev_id_var = id_var

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
    beluga_model: BelugaModel,   
) -> BelugaPlanProblemMatching:

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

    (num_encountered_load, num_encountered_proceed_to_next_flight) = (0, 0)

    plan_len = len(plan_def)

    for k in range(plan_len):
        a_k = plan_def[k]

        if a_k.name == beluga_model.unload_jig_from_beluga_to_trailer.name:
            for (unload_st, putdown_st) in beluga_model.all_unloads:
                if (unload_st.parameters[0].object() == beluga_model.jig_objects[a_k.params['j']]
                    and not contains_subtask(unload_st)
                ):
                    insert(k, unload_st)
                    for l in range(k+1, plan_len):
                        a_l = plan_def[l]
                        if (TASK_NAME_PREFIX+a_l.name == beluga_model.putdown_jig_on_rack.name
                            and putdown_st.parameters[0].object() == beluga_model.jig_objects[a_l.params['j']]
                            and a_k.params['t'] == a_l.params['t']
                        ):
                            insert(l, putdown_st)
                            insert_var_assignment(putdown_st.parameters[1].parameter(), beluga_model.trailer_objects[a_k.params['t']])
                            insert_var_assignment(putdown_st.parameters[2].parameter(), beluga_model.rack_objects[a_l.params['r']])
                            insert_var_assignment(putdown_st.parameters[5].parameter(), beluga_model.pb.explicit_initial_values[beluga_model.rack_size(beluga_model.rack_objects[a_l.params['r']])].int_constant_value())
                            break
                    break

        elif a_k.name == beluga_model.load_jig_from_trailer_to_beluga.name:
            (pickup_st, load_st) = beluga_model.all_loads[num_encountered_load]
            insert(k, load_st)
            for l in range(k-1, -1, -1):
                a_l = plan_def[l]

                if (a_l.name == beluga_model.pickup_jig_from_rack.name
                    and a_k.params['j'] == a_l.params['j']
                    and a_k.params['t'] == a_l.params['t']
                ):
                    insert(l, pickup_st)
                    insert_var_assignment(pickup_st.parameters[0].parameter(), beluga_model.jig_objects[a_k.params['j']])
                    insert_var_assignment(pickup_st.parameters[1].parameter(), beluga_model.trailer_objects[a_k.params['t']])
                    insert_var_assignment(pickup_st.parameters[2].parameter(), beluga_model.rack_objects[a_l.params['r']])
                    break
            num_encountered_load += 1

        elif a_k.name == beluga_model.deliver_jig_to_hangar.name:
            for (pickup_st, deliver_st) in beluga_model.all_delivers:
                if (deliver_st.parameters[0].object() == beluga_model.jig_objects[a_k.params['j']]
                    and deliver_st.parameters[3].object() == beluga_model.production_line_objects[a_k.params['pl']]
                    and not contains_subtask(deliver_st)
                ):
                    insert(k, deliver_st)
                    for l in range(k-1, -1, -1):
                        a_l = plan_def[l]
        
                        if (a_l.name == beluga_model.pickup_jig_from_rack.name
                            and pickup_st.parameters[0].object() == beluga_model.jig_objects[a_l.params['j']]
                            and a_k.params['t'] == a_l.params['t']
                        ):
                            insert(l, pickup_st)
                            insert_var_assignment(pickup_st.parameters[1].parameter(), beluga_model.trailer_objects[a_k.params['t']])
                            insert_var_assignment(pickup_st.parameters[2].parameter(), beluga_model.rack_objects[a_l.params['r']])
                            break
                    break

        elif TASK_NAME_PREFIX+a_k.name == beluga_model.get_jig_from_hangar.name:
            for (get_st, putdown_st) in beluga_model.all_gets:
                if (get_st.parameters[0].object() == beluga_model.jig_objects[a_k.params['j']]
                    and not contains_subtask(get_st)
                ):
                    insert(k, get_st)
                    for l in range(k+1, plan_len):
                        a_l = plan_def[l]

                        if (TASK_NAME_PREFIX+a_l.name == beluga_model.putdown_jig_on_rack.name
                            and putdown_st.parameters[0].object() == beluga_model.jig_objects[a_l.params['j']]
                            and a_k.params['t'] == a_l.params['t']
                        ):
                            insert(l, putdown_st)
                            insert_var_assignment(putdown_st.parameters[1].parameter(), beluga_model.trailer_objects[a_k.params['t']])
                            insert_var_assignment(putdown_st.parameters[2].parameter(), beluga_model.rack_objects[a_l.params['r']])
                            insert_var_assignment(putdown_st.parameters[5].parameter(), beluga_model.pb.explicit_initial_values[beluga_model.rack_size(beluga_model.rack_objects[a_l.params['r']])].int_constant_value())
                            break
                    break

        elif a_k.name == beluga_model.proceed_to_next_flight.name:
            insert(k, beluga_model.all_proceed_to_next_flight[num_encountered_proceed_to_next_flight])
            num_encountered_proceed_to_next_flight += 1

        else:
            continue

    swap_id = 0
    for k in range(plan_len):
        a_k = plan_def[k]

        if a_k.name == beluga_model.pickup_jig_from_rack.name and not contains_plan_action(k):
            for l in range(k+1, plan_len):
                a_l = plan_def[l]
                if (not contains_plan_action(l)
                    and TASK_NAME_PREFIX+a_l.name == beluga_model.putdown_jig_on_rack.name
                    and a_k.params['j'] == a_l.params['j']
                    and a_k.params['t'] == a_l.params['t']
                    and a_k.params['s'] == a_l.params['s']
                ):
                    swap = beluga_model.pb.task_network.get_subtask(beluga_model.all_swaps[swap_id].identifier)
                    insert(k, (False, swap))
                    insert(l, (True, swap))
                    insert_var_assignment(swap.parameters[0].parameter(), up.FALSE())
                    assert(swap.parameters[1].constant_value() == swap_id)
                    insert_var_assignment(swap.parameters[2].parameter(), beluga_model.jig_objects[a_k.params['j']])
                    insert_var_assignment(swap.parameters[3].parameter(), beluga_model.rack_objects[a_k.params['r']])
                    insert_var_assignment(swap.parameters[4].parameter(), beluga_model.rack_objects[a_l.params['r']])
                    insert_var_assignment(swap.parameters[5].parameter(), beluga_model.trailer_objects[a_k.params['t']])
                    insert_var_assignment(swap.parameters[6].parameter(), beluga_model.pb.object(a_k.params['s']))
                    insert_var_assignment(swap.parameters[7].parameter(), beluga_model.pb.explicit_initial_values[beluga_model.rack_size(beluga_model.rack_objects[a_l.params['r']])].int_constant_value())

                    swap_id += 1
                    break

    insert_var_assignment(beluga_model.num_used_swaps, swap_id)

    # Assign the "is_noop" variable of the remaining / not used swaps to False
    for swap in beluga_model.all_swaps:
        if (not contains_subtask((False, swap))
            and not contains_subtask((True, swap))
        ):
            insert_var_assignment(swap.parameters[0].parameter(), up.TRUE())

    #print(set(range(plan_len)).difference(plan_action_to_subtask_map.keys()))
    for a in struct_map_plan_action_to_subtask:
        print(a, struct_map_plan_action_to_subtask[a])
    for a in set(range(plan_len)).difference(struct_map_plan_action_to_subtask.keys()):
        print(a, plan_def[a])        
    assert len(set(range(plan_len)).difference(struct_map_plan_action_to_subtask.keys())) == 0

    ##### Read values of preferences in the plan #####

    # size of largest rack onto which the same jig is placed

    pref_max_rack_size_used_for_jig = {}
    for j in beluga_model.pb_def.jigs:
        jig_name = j.name
        jig = beluga_model.jig_objects[jig_name]

        if beluga_model.at(jig) in beluga_model.pb.explicit_initial_values:
            jig_initially_at = beluga_model.pb.explicit_initial_values[beluga_model.at(jig)].object()
        else:
            jig_initially_at = None
        if jig_initially_at in beluga_model.rack_objects: # if the initial location of the jig is actually a rack
            val = beluga_model.rack_size[jig_initially_at] # type: ignore
            pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig.setdefault(jig, val))

        if jig_name in beluga_model.unloads_used_rack_size_vars:
            val = struct_vars_plan_assignments.get(beluga_model.unloads_used_rack_size_vars[jig_name], None)
            if val is not None:
                pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig.setdefault(jig, val))

        if jig_name in beluga_model.gets_used_rack_size_vars:
            val = struct_vars_plan_assignments.get(beluga_model.gets_used_rack_size_vars[jig_name], None)
            if val is not None:
                pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig.setdefault(jig, val))

        for id_swap in beluga_model.swaps_used_rack_size_vars:
            jig_var_swap = beluga_model.swaps_jig_vars[id_swap]
            if jig_var_swap in struct_vars_plan_assignments and struct_vars_plan_assignments[jig_var_swap] == jig:
                val = struct_vars_plan_assignments.get(beluga_model.swaps_used_rack_size_vars[id_swap], None)
                if val is not None:
                    pref_max_rack_size_used_for_jig[jig] = max(val, pref_max_rack_size_used_for_jig.setdefault(jig, val))

    # always jigs of same type on rack

    pref_jig_types_on_rack = {}

    for rack in beluga_model.pb_def.racks:
        rack_name = rack.name
        rack = beluga_model.rack_objects[rack_name]
        pref_jig_types_on_rack.setdefault(rack, set())

        initial_jig_type_on_rack: JigType | None = None # None when no jig initially on the rack
        for j in beluga_model.pb_def.jigs:
            jig_name = j.name
            jig = beluga_model.jig_objects[jig_name]
            jig_initially_at_rack = (beluga_model.pb.explicit_initial_values[beluga_model.at(jig)].object() == rack if beluga_model.at(jig) in beluga_model.pb.explicit_initial_values else False)
            if jig_initially_at_rack:
                initial_jig_type_on_rack = beluga_model.pb_def.get_jig_type(beluga_model.pb_def.get_jig(jig_name).type)
                if initial_jig_type_on_rack is not None:
                    pref_jig_types_on_rack[rack].add(initial_jig_type_on_rack.name)

    for jig_name, rack_var in beluga_model.unloads_rack_vars.items():
        if rack_var in struct_vars_plan_assignments:
            rack = struct_vars_plan_assignments[rack_var]
            pref_jig_types_on_rack[rack].add(beluga_model.pb_def.get_jig_type(beluga_model.pb_def.get_jig(jig_name).type).name)

    for jig_name, rack_var in beluga_model.gets_rack_vars.items():
        if rack_var in struct_vars_plan_assignments:
            rack = struct_vars_plan_assignments[rack_var]
            pref_jig_types_on_rack[rack].add(beluga_model.pb_def.get_jig_type(beluga_model.pb_def.get_jig(jig_name).type).name)

    for id_swap, rack_var in beluga_model.swaps_rack2_vars.items():
        if rack_var in struct_vars_plan_assignments:
            rack = struct_vars_plan_assignments[rack_var]
            jig_name = struct_vars_plan_assignments[beluga_model.swaps_jig_vars[id_swap]].name # type: ignore
            pref_jig_types_on_rack[rack].add(beluga_model.pb_def.get_jig_type(beluga_model.pb_def.get_jig(jig_name).type).name)

    pref_always_jigs_of_same_type_on_rack = { rack: True if len(jt) <= 1 else False for rack, jt in pref_jig_types_on_rack.items() }

    # rack always empty

    pref_rack_always_empty = {}
    
    for rack in beluga_model.pb_def.racks:
        rack = beluga_model.rack_objects[rack.name]
        if rack not in pref_always_jigs_of_same_type_on_rack or len(pref_jig_types_on_rack[rack]) == 0:
            pref_rack_always_empty[rack] = True
        else:
            pref_rack_always_empty[rack] = False

    # at least one rack always empty

    pref_at_least_one_rack_always_empty = True in pref_rack_always_empty.values()

    # # #

    all_non_swap_subtasks_not_required_by_plan=list(set(beluga_model.all_non_swap_subtasks).difference(struct_map_plan_action_to_subtask_inv.keys()))

    pbb = beluga_model.pb.clone()
    pbb.epsilon = 1

    struct_constrs = _make_plan_structural_constraints(
        struct_vars_plan_assignments,
        struct_map_plan_action_to_subtask,
        all_non_swap_subtasks_not_required_by_plan,
    )
    for c in struct_constrs:
        pbb.task_network.add_constraint(c)

    pll = solve_problem(pbb, None)
    # up_plot.plot_time_triggered_plan(pll.action_plan, figsize=(26.0, 8.0))

    # putdown delay (full jigs)

    pref_putdown_full_delay = {}

    for (unload_st, putdown_st) in beluga_model.all_unloads:
        (t1, unload_a) = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[unload_st.identifier]][0]
        jig = unload_a.actual_parameters[0].object()
        aux = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[putdown_st.identifier].decomposition.subtasks.get("_t1", None)] # type: ignore
        if len(aux) > 0:
            assert len(aux) == 1
            (t2, putdown_a) = aux[0]
            pref_putdown_full_delay[jig] = (t2 - t1).numerator # WARNING we allow ourselves to do this because we ensure epsilon = 1
        # else:
        #     pref_putdown_full_delay[jig] = 1000
    
    # putdown delay (empty jigs)

    pref_putdown_empty_delay = {}

    for (get_st, putdown_st) in beluga_model.all_gets:
        aux1 = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[get_st.identifier].decomposition.subtasks.get("_t2", None)] # type: ignore
        if len(aux1) > 0:
            assert len(aux1) == 1
            (t1, get_a) = aux1[0]
            jig = get_a.actual_parameters[0].object()
            aux2 = [(t, a) for (t, a, d) in pll.action_plan.timed_actions if a == pll.decomposition.subtasks[putdown_st.identifier].decomposition.subtasks.get("_t2", None)] # type: ignore
            if len(aux2) > 0:
                assert len(aux2) == 1
                (t2, putdown_a) = aux2[0]
                if putdown_st.parameters[2].parameter() in struct_vars_plan_assignments:
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
            #print("--- ",v)
            if isinstance(v, up_htn.Subtask):
                st: up_htn.Subtask = v
                if prev is not None:
                    constrs.append(up.LT(prev, st.start)) # FIXME LE/LT?
                prev = st.start
            elif isinstance(v, tuple):
                st: up_htn.Subtask = v[1]
                if v[0] == False:
                    if prev is not None:
                        constrs.append(up.LT(prev, st.start)) # FIXME LE/LT?
                    prev = st.start
                else:
                    if prev is not None:
                        constrs.append(up.LT(prev, st.parameters[8].parameter()))
                    prev = st.parameters[9].parameter()

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
            constrs.append(up.Equals(var, val)) # APPARENTLY, CAUSED A BUG!... EXAMPLE_SAT_QUESTIONS0...

    return constrs
    
def apply_plan_structural_constraints_to_problem(
    pb: up_htn.HierarchicalProblem,
    plan_problem_matching: BelugaPlanProblemMatching
):
    constrs = make_plan_structural_constraints(plan_problem_matching)
    for c in constrs:
        pb.task_network.add_constraint(c)

def reify_conjunction_of_plan_structural_constraints(
    pb: up_htn.HierarchicalProblem,
    plan_problem_matching: BelugaPlanProblemMatching
) -> up.Parameter:
    if "is_ref_plan" in pb.task_network._variables:
        is_ref_plan = pb.task_network.parameter("is_ref_plan")
    else:
        is_ref_plan = pb.task_network.add_variable("is_ref_plan", up.BoolType())
    constrs = make_plan_structural_constraints(plan_problem_matching)
    pb.task_network.add_constraint(
        up.Or(
            up.And(is_ref_plan, up.And(constrs)),
            up.And(up.Not(is_ref_plan), up.Not(up.And(constrs))),
        )
    )
    return is_ref_plan

def reify_at_least_one_rack_always_empty(
    beluga_model: BelugaModel,
) -> up.Parameter:

    if "at_least_one_rack_always_empty" in beluga_model.pb.task_network._variables:
        at_least_one_rack_always_empty = beluga_model.pb.task_network.parameter("at_least_one_rack_always_empty")
    else:
        at_least_one_rack_always_empty = beluga_model.pb.task_network.add_variable("at_least_one_rack_always_empty", up.BoolType())

        rack_always_empty_list = []
        for rack in beluga_model.pb_def.racks:
            rack_always_empty_list.append(reify_rack_always_empty(beluga_model, rack.name))

        beluga_model.pb.task_network.add_constraint(
            up.Or(
                up.And(at_least_one_rack_always_empty, up.Or([r_always_empty for r_always_empty in rack_always_empty_list])),
                up.And(up.Not(at_least_one_rack_always_empty), up.Not(up.Or([r_always_empty for r_always_empty in rack_always_empty_list]))),
            )
        )
    return at_least_one_rack_always_empty

def reify_rack_always_empty(
    beluga_model: BelugaModel,
    rack_name:str,
) -> up.Parameter:

    all_rack_putdown_vars = list(beluga_model.unloads_rack_vars.values())
    all_rack_putdown_vars += list(beluga_model.gets_rack_vars.values())
    all_rack_putdown_vars += list(beluga_model.swaps_rack2_vars.values())

    rack_initially_empty = up.Bool(beluga_model.pb.explicit_initial_values[beluga_model.rack_free_space(beluga_model.rack_objects[rack_name])] == beluga_model.pb.explicit_initial_values[beluga_model.rack_size(beluga_model.rack_objects[rack_name])])

    if f"{rack_name}_always_empty" in beluga_model.pb.task_network._variables:
        r_always_empty = beluga_model.pb.task_network.parameter(f"{rack_name}_always_empty",)
    else:
        r_always_empty = beluga_model.pb.task_network.add_variable(f"{rack_name}_always_empty", up.BoolType())

        beluga_model.pb.task_network.add_constraint(
            up.Or(
                up.And(up.Not(r_always_empty), up.Or([up.Not(rack_initially_empty)]+[up.Equals(var_, beluga_model.rack_objects[rack_name]) for var_ in all_rack_putdown_vars])),
                up.And(r_always_empty, up.And([rack_initially_empty]+[up.Not(up.Equals(var_, beluga_model.rack_objects[rack_name])) for var_ in all_rack_putdown_vars])),
            )
        )
    return r_always_empty

def reify_jig_always_placed_on_rack_shorter_or_same_size_as(beluga_model: BelugaModel, jig_name:str, max_allowed_rack_size:int) -> up.Parameter:
    terms = []

    if f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as" in beluga_model.pb.task_network._variables:
        jig_always_placed_on_rack_shorter_or_same_size_as = beluga_model.pb.task_network.parameter(f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as",)
    else:
        jig_always_placed_on_rack_shorter_or_same_size_as = beluga_model.pb.task_network.add_variable(f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as", up.BoolType())

        jig_initially_at = beluga_model.pb.explicit_initial_values.get(beluga_model.at(beluga_model.jig_objects[jig_name]), None)
        if jig_initially_at is not None:
            jig_initially_at = jig_initially_at.object()
            # if the initial location of the jig is actually a rack
            if (jig_initially_at in beluga_model.rack_objects.values()
                and beluga_model.rack_size(jig_initially_at) in beluga_model.pb.explicit_initial_values
            ):
                terms += [up.LE(beluga_model.pb.explicit_initial_values[beluga_model.rack_size(jig_initially_at)], max_allowed_rack_size)]

        if jig_name in beluga_model.unloads_used_rack_size_vars:
            terms += [up.LE(beluga_model.unloads_used_rack_size_vars[jig_name], max_allowed_rack_size)]
        if jig_name in beluga_model.gets_used_rack_size_vars:
            terms += [up.LE(beluga_model.gets_used_rack_size_vars[jig_name], max_allowed_rack_size)]
        assert len(terms) > 0
        
        for id_swap in beluga_model.swaps_used_rack_size_vars:
            terms += [
                up.Or(
                    up.Not(up.Equals(beluga_model.swaps_jig_vars[id_swap], beluga_model.jig_objects[jig_name])),
                    up.LE(beluga_model.swaps_used_rack_size_vars[id_swap], max_allowed_rack_size),
                )
            ]
        
        beluga_model.pb.task_network.add_constraint(
            up.Or(
                up.And(jig_always_placed_on_rack_shorter_or_same_size_as, up.And(terms)),
                up.And(up.Not(jig_always_placed_on_rack_shorter_or_same_size_as), up.Not(up.And(terms))),
            )
        )

    return jig_always_placed_on_rack_shorter_or_same_size_as

def reify_num_swaps_used_leq(
    beluga_model: BelugaModel,
    val: int,
) -> up.Parameter:

    if f"num_swaps_used_leq_{val}" in beluga_model.pb.task_network._variables:
        num_swaps_used_leq_val = beluga_model.pb.task_network.parameter(f"num_swaps_used_leq_{val}")
    else:
        num_swaps_used_leq_val = beluga_model.pb.task_network.add_variable(f"num_swaps_used_leq_{val}", up.BoolType())

        beluga_model.pb.task_network.add_constraint(
            up.Or(
                up.And(num_swaps_used_leq_val,
                        up.LE(beluga_model.num_used_swaps, val)),
                up.And(up.Not(num_swaps_used_leq_val),
                        up.GT(beluga_model.num_used_swaps, val)),
            )
        )
    return num_swaps_used_leq_val
""" 
def reify_satisfaction_of_ref_plan_prefs_in_problem(
    beluga_model: BelugaModel,
    plan_pb_matching: BelugaPlanProblemMatching,
):# -> tuple[
#    up.Parameter,
#    dict[up.Object, up.Parameter],
#    dict[up.Object, up.Parameter],
#    dict[up.Object, up.Parameter],
#    up.Parameter, 
#    up.Parameter,
#]:

    def reify_jig_always_placed_on_rack_shorter_or_same_size_as(jig_name:str, max_allowed_rack_size:int) -> up.Parameter:
        terms = []

        if f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as" in beluga_model.pb.task_network._variables:
            jig_always_placed_on_rack_shorter_or_same_size_as = beluga_model.pb.task_network.parameter(f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as",)
        else:
            jig_always_placed_on_rack_shorter_or_same_size_as = beluga_model.pb.task_network.add_variable(f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as", up.BoolType())

            jig_initially_at = beluga_model.pb.explicit_initial_values.get(beluga_model.at(beluga_model.jig_objects[jig_name]), None)
            if jig_initially_at is not None:
                jig_initially_at = jig_initially_at.object()
                # if the initial location of the jig is actually a rack
                if (jig_initially_at in beluga_model.rack_objects.values()
                    and beluga_model.rack_size(jig_initially_at) in beluga_model.pb.explicit_initial_values
                ):
                    terms += [up.LE(beluga_model.pb.explicit_initial_values[beluga_model.rack_size(jig_initially_at)], max_allowed_rack_size)]

            if jig_name in beluga_model.unloads_used_rack_size_vars:
                terms += [up.LE(beluga_model.unloads_used_rack_size_vars[jig_name], max_allowed_rack_size)]
            if jig_name in beluga_model.gets_used_rack_size_vars:
                terms += [up.LE(beluga_model.gets_used_rack_size_vars[jig_name], max_allowed_rack_size)]
            assert len(terms) > 0
            
            for id_swap in beluga_model.swaps_used_rack_size_vars:
                terms += [
                    up.Or(
                        up.Not(up.Equals(beluga_model.swaps_jig_vars[id_swap], beluga_model.jig_objects[jig_name])),
                        up.LE(beluga_model.swaps_used_rack_size_vars[id_swap], max_allowed_rack_size),
                    )
                ]
            
            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(jig_always_placed_on_rack_shorter_or_same_size_as, up.And(terms)),
                    up.And(up.Not(jig_always_placed_on_rack_shorter_or_same_size_as), up.Not(up.And(terms))),
                )
            )

        return jig_always_placed_on_rack_shorter_or_same_size_as

    def reify_max_delay_putdown_full_le(jig_name:str, max_allowed_delay:int) -> up.Parameter:
        if f"{jig_name}_max_delay_putdown_full_le_{max_allowed_delay}" in beluga_model.pb.task_network._variables:
            max_delay_putdown_full_le = beluga_model.pb.task_network.parameter(f"{jig_name}_max_delay_putdown_full_le_{max_allowed_delay}",)
        else:
            max_delay_putdown_full_le = beluga_model.pb.task_network.add_variable(f"{jig_name}_max_delay_putdown_full_le_{max_allowed_delay}", up.BoolType())

            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(max_delay_putdown_full_le, up.LE(beluga_model.unloads_max_putdown_delay_vars[jig_name], max_allowed_delay)),
                    up.And(up.Not(max_delay_putdown_full_le), up.GT(beluga_model.unloads_max_putdown_delay_vars[jig_name], max_allowed_delay)),
                )
            )
        return max_delay_putdown_full_le
 
    def reify_max_delay_putdown_empty_le(jig_name:str, max_allowed_delay:int) -> up.Parameter:
        if f"{jig_name}_max_delay_putdown_empty_le_{max_allowed_delay}" in beluga_model.pb.task_network._variables:
            max_delay_putdown_empty_le = beluga_model.pb.task_network.parameter(f"{jig_name}_max_delay_putdown_empty_le_{max_allowed_delay}",)
        else:
            max_delay_putdown_empty_le = beluga_model.pb.task_network.add_variable(f"{jig_name}_max_delay_putdown_empty_le_{max_allowed_delay}", up.BoolType())

            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(max_delay_putdown_empty_le, up.LE(beluga_model.gets_max_putdown_delay_vars[jig_name], max_allowed_delay)),
                    up.And(up.Not(max_delay_putdown_empty_le), up.GT(beluga_model.gets_max_putdown_delay_vars[jig_name], max_allowed_delay)),
                )
            )
        return max_delay_putdown_empty_le

    # # #

    if "ref_plan_pref_sat_at_least_one_rack_always_empty" in beluga_model.pb.task_network._variables:
        ref_plan_pref_sat_at_least_one_rack_always_empty = beluga_model.pb.task_network.parameter("ref_plan_pref_sat_at_least_one_rack_always_empty")
    else:
        ref_plan_pref_sat_at_least_one_rack_always_empty = beluga_model.pb.task_network.add_variable("ref_plan_pref_sat_at_least_one_rack_always_empty", up.BoolType())

        iff_workaround = up.Or(
            up.And(reify_at_least_one_rack_always_empty(beluga_model), up.Bool(plan_pb_matching.pref_at_least_one_rack_always_empty)),
            up.And(up.Not(reify_at_least_one_rack_always_empty(beluga_model)), up.Not(up.Bool(plan_pb_matching.pref_at_least_one_rack_always_empty))),
        )
        beluga_model.pb.task_network.add_constraint(
            up.Or(
                up.And(ref_plan_pref_sat_at_least_one_rack_always_empty, iff_workaround),
                up.And(up.Not(ref_plan_pref_sat_at_least_one_rack_always_empty), up.Not(iff_workaround)),
            )
        )

    # # #

    ref_plan_pref_sat_reify_rack_always_empty: dict[up.Object, up.Parameter] = {}

    for rack in plan_pb_matching.pref_rack_always_empty:
        rack_name = rack.name

        if f"ref_plan_pref_sat_{rack_name}_always_empty" in beluga_model.pb.task_network._variables:
            ref_plan_pref_sat_reify_rack_always_empty[rack] = beluga_model.pb.task_network.parameter(f"ref_plan_pref_sat_{rack_name}_always_empty")
        else:
            ref_plan_pref_sat_reify_rack_always_empty[rack] = beluga_model.pb.task_network.add_variable(f"ref_plan_pref_sat_{rack_name}_always_empty", up.BoolType())
        
            iff_workaround = up.Or(
                up.And(reify_rack_always_empty(beluga_model, rack_name), up.Bool(plan_pb_matching.pref_rack_always_empty[rack])),
                up.And(up.Not(reify_rack_always_empty(beluga_model, rack_name)), up.Not(up.Bool(plan_pb_matching.pref_rack_always_empty[rack]))),
            )
            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(ref_plan_pref_sat_reify_rack_always_empty[rack], iff_workaround),
                    up.And(up.Not(ref_plan_pref_sat_reify_rack_always_empty[rack]), up.Not(iff_workaround)),
                )
            )

    # # #

    ref_plan_pref_sat_jig_always_placed_on_rack_shorter_or_same_size_as: dict[up.Object, up.Parameter] = {}

    for jig in plan_pb_matching.pref_max_rack_size_used_for_jig:
        jig_name = jig.name

        if f"ref_plan_pref_sat_{jig_name}_always_placed_on_rack_shorter_or_same_size_as" in beluga_model.pb.task_network._variables:
            ref_plan_pref_sat_jig_always_placed_on_rack_shorter_or_same_size_as[jig] = beluga_model.pb.task_network.parameter(f"ref_plan_pref_sat_{jig_name}_always_placed_on_rack_shorter_or_same_size_as")
        else:
            ref_plan_pref_sat_jig_always_placed_on_rack_shorter_or_same_size_as[jig] = beluga_model.pb.task_network.add_variable(f"ref_plan_pref_sat_{jig_name}_always_placed_on_rack_shorter_or_same_size_as", up.BoolType())
            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(ref_plan_pref_sat_jig_always_placed_on_rack_shorter_or_same_size_as[jig],
                        reify_jig_always_placed_on_rack_shorter_or_same_size_as(jig_name, plan_pb_matching.pref_max_rack_size_used_for_jig[jig])),
                    up.And(up.Not(ref_plan_pref_sat_jig_always_placed_on_rack_shorter_or_same_size_as[jig]),
                        up.Not(reify_jig_always_placed_on_rack_shorter_or_same_size_as(jig_name, plan_pb_matching.pref_max_rack_size_used_for_jig[jig]))),
                )
            )

    # # #

    ref_plan_pref_sat_max_delay_putdown_full: dict[up.Object, up.Parameter] = {}

    for jig in plan_pb_matching.pref_putdown_full_delay:
        jig_name = jig.name

        if f"ref_plan_pref_sat_{jig_name}_max_delay_putdown_full" in beluga_model.pb.task_network._variables:
            ref_plan_pref_sat_max_delay_putdown_full[jig] = beluga_model.pb.task_network.parameter(f"ref_plan_pref_sat_{jig_name}_max_delay_putdown_full")
        else:
            ref_plan_pref_sat_max_delay_putdown_full[jig] = beluga_model.pb.task_network.add_variable(f"ref_plan_pref_sat_{jig_name}_max_delay_putdown_full", up.BoolType())

            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(ref_plan_pref_sat_max_delay_putdown_full[jig],
                        reify_max_delay_putdown_full_le(jig_name, plan_pb_matching.pref_putdown_full_delay[jig])),
                    up.And(up.Not(ref_plan_pref_sat_max_delay_putdown_full[jig]),
                        up.Not(reify_max_delay_putdown_full_le(jig_name, plan_pb_matching.pref_putdown_full_delay[jig]))),
                )
            )

    # # #

    ref_plan_pref_sat_max_delay_putdown_empty: dict[up.Object, up.Parameter] = {}

    for jig in plan_pb_matching.pref_putdown_empty_delay:
        jig_name = jig.name

        if f"ref_plan_pref_sat_{jig_name}_max_delay_putdown_empty" in beluga_model.pb.task_network._variables:
            ref_plan_pref_sat_max_delay_putdown_empty[jig] = beluga_model.pb.task_network.parameter(f"ref_plan_pref_sat_{jig_name}_max_delay_putdown_empty")
        else:
            ref_plan_pref_sat_max_delay_putdown_empty[jig] = beluga_model.pb.task_network.add_variable(f"ref_plan_pref_sat_{jig_name}_max_delay_putdown_empty", up.BoolType())

            beluga_model.pb.task_network.add_constraint(
                up.Or(
                    up.And(ref_plan_pref_sat_max_delay_putdown_empty[jig],
                        reify_max_delay_putdown_empty_le(jig_name, plan_pb_matching.pref_putdown_empty_delay[jig])),
                    up.And(up.Not(ref_plan_pref_sat_max_delay_putdown_empty[jig]),
                        up.Not(reify_max_delay_putdown_empty_le(jig_name, plan_pb_matching.pref_putdown_empty_delay[jig]))),
                )
            )

    # # #

    num_used_swaps_in_ref_plan = plan_pb_matching.struct_vars_plan_assignments[beluga_model.num_used_swaps]

    if f"ref_plan_pref_sat_num_used_swaps_leq_{num_used_swaps_in_ref_plan}" in beluga_model.pb.task_network._variables:
        ref_plan_pref_sat_num_used_swaps_leq = beluga_model.pb.task_network.parameter(f"ref_plan_pref_sat_num_used_swaps_leq_{num_used_swaps_in_ref_plan}")
    else:
        ref_plan_pref_sat_num_used_swaps_leq = beluga_model.pb.task_network.add_variable(f"ref_plan_pref_sat_num_used_swaps_leq_{num_used_swaps_in_ref_plan}", up.BoolType())

        beluga_model.pb.task_network.add_constraint(
            up.Or(
                up.And(ref_plan_pref_sat_num_used_swaps_leq,
                        up.LE(beluga_model.num_used_swaps, num_used_swaps_in_ref_plan)),
                up.And(up.Not(ref_plan_pref_sat_num_used_swaps_leq),
                        up.GT(beluga_model.num_used_swaps, num_used_swaps_in_ref_plan)),
            )
        )

    # # #

    return (
        ref_plan_pref_sat_at_least_one_rack_always_empty,
        ref_plan_pref_sat_reify_rack_always_empty,
        ref_plan_pref_sat_jig_always_placed_on_rack_shorter_or_same_size_as,
        ref_plan_pref_sat_max_delay_putdown_full,
        ref_plan_pref_sat_max_delay_putdown_empty,
        ref_plan_pref_sat_num_used_swaps_leq,
    )
 """
