import sys
import os
from unified_planning.grpc.proto_writer import ProtobufWriter

import unified_planning.shortcuts as up

from unified_planning.model.scheduling.scheduling_problem import SchedulingProblem
from unified_planning.model.scheduling.activity import Activity
from unified_planning.plans import Schedule

from parser import *

def serialize_problem(pb: up.Problem, filename: str):
    writer = ProtobufWriter()
    msg = writer.convert(pb)
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "wb") as file:
        file.write(msg.SerializeToString())

def solve_problem(pb: SchedulingProblem, timeout:float|None) -> Schedule: # type: ignore
    with up.OneshotPlanner(name="aries") as planner:
        result = planner.solve( # type: ignore
            pb,
            timeout=timeout,
            output_stream=sys.stdout,
        )
        plan = result.plan
    return plan

class BelugaModelOptSched:

    def __init__(
        self,
        pb_def: BelugaProblemDef,
        name: str,
        num_available_swaps_margin: int,
        ref_plan_def: BelugaPlanDef | None,
    ):
        # # #

        self.pb: SchedulingProblem
        self._activities_uid_counter: int = 0

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

        self.num_flights: int

        self.all_proceeds_to_next_flight: list[tuple[str, Activity]] = []
        self.all_unloads_w_putdowns: dict[tuple[str, str, int], tuple[Activity, Activity]] = {}
        self.all_loads_w_pickups: dict[tuple[str, str, int], tuple[Activity, Activity]] = {}
        self.all_delivers_w_pickups: dict[tuple[str, str, int], tuple[Activity, Activity]] = {}
        self.all_gets_w_putdowns: dict[str, tuple[Activity, Activity]] = {}
        self.all_swap_pickups_n_putdowns: dict[int, tuple[Activity, Activity]] = {}

        self.all_putdowns: list[Activity] = []
        self.all_pickups: list[Activity] = []

        # # #

        self.num_used_swaps: up.Parameter

        # # #

        self.properties: dict[PropId, up.Parameter] = {}

        # # #

        self.pb_def = pb_def
        self.num_flights = len(pb_def.flights)

        self.num_available_swaps = num_available_swaps_margin

        self.pb = SchedulingProblem(name)
        
        self._make_types_and_fluents_and_initial_values()

        # # #

        self._add_proceeds()

        self._add_flights_unloads_w_opt_putdowns()
        self._add_flights_loads_w_pickups()
        self._add_pls_deliveries_w_pickups_and_retrievals_w_opt_putdowns()

        # if ref_plan_def is not None:
        #     # num_swaps_used_in_ref_plan = self._get_number_of_swaps_in_reference_plan(ref_plan_def)
        #     # self.num_available_swaps = num_swaps_used_in_ref_plan + num_available_swaps_margin
        self._add_swaps()

        self._add_trailers_initial_jigs_opt_putdowns()
        self._add_hangars_initial_jigs_retrievals_w_opt_putdowns()
        self._add_opt_pickup_for_each_jig_last_non_swap()
        # # #

        for (j_name, flight_name, i), (unload_a, _) in self.all_unloads_w_putdowns.items():
            pres_val = up.TRUE()
            for prop_id, (jj, bb, ii) in self.pb_def.props_unload_beluga:
                if (j_name == jj and flight_name == bb and i == ii):
                    self.properties[prop_id] = self.pb.add_variable(f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_unload_{j_name}_{flight_name}_{i}", up.BoolType())
                    pres_val = self.properties[prop_id]
                    break
            self.pb.add_constraint(up.Iff(unload_a.present, pres_val))

        for (j_or_j_type_name, flight_name, i), (load_a, _) in self.all_loads_w_pickups.items():
            pres_val = up.TRUE()
            for prop_id, (jj, bb, ii) in self.pb_def.props_load_beluga:
                if (j_or_j_type_name == jj and flight_name == bb and i == ii):
                    self.properties[prop_id] = self.pb.add_variable(f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_load_{j_or_j_type_name}_{flight_name}_{i}", up.BoolType())
                    pres_val = self.properties[prop_id]
                    break
            self.pb.add_constraint(up.Iff(load_a.present, pres_val))

        for (j_name, pl_name, i), (deliver_a, _) in self.all_delivers_w_pickups.items():
            pres_val = up.TRUE()
            for prop_id, (jj, pl, ii) in self.pb_def.props_deliver_to_production_line:
                if (j_name == jj and pl_name == pl and i == ii):
                    self.properties[prop_id] = self.pb.add_variable(f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_deliver_{j_name}_{pl_name}_{i}", up.BoolType())
                    pres_val = self.properties[prop_id]
                    break
            self.pb.add_constraint(up.Iff(deliver_a.present, pres_val))

        assert all(prop_id in self.properties for (prop_id, _) in self.pb_def.props_unload_beluga)
        assert all(prop_id in self.properties for (prop_id, _) in self.pb_def.props_load_beluga)
        assert all(prop_id in self.properties for (prop_id, _) in self.pb_def.props_deliver_to_production_line)

        for (prop_id, rack_name) in self.pb_def.props_rack_always_empty:
            self._reify_prop_rack_always_empty(rack_name, prop_id)

        if self.pb_def.prop_at_least_one_rack_always_empty is not None:
            self._reify_prop_at_least_one_rack_always_empty(self.pb_def.prop_at_least_one_rack_always_empty)

        for (prop_id, (jig_name, rs)) in self.pb_def.props_jig_always_placed_on_rack_size_leq:
            self._reify_prop_jig_always_placed_on_rack_shorter_or_same_size_as(jig_name, rs, prop_id)

        for (prop_id, ns) in self.pb_def.props_num_swaps_used_leq:
            self._reify_prop_num_swaps_used_leq_val(ns, prop_id)

        for (prop_id, (jig_name, rack_name)) in self.pb_def.props_jig_never_on_rack:
            self._reify_prop_jig_never_on_rack(jig_name, rack_name, prop_id)

        for (prop_id, (jig_name, rack_name)) in self.pb_def.props_jig_only_if_ever_on_rack:
            self._reify_prop_jig_only_if_ever_on_rack(jig_name, rack_name, prop_id)

        for (prop_id, (jig1_name, pl1_name, jig2_name, pl2_name)) in self.pb_def.props_jig_to_production_line_order:
            self._reify_prop_jig_to_production_line_order(jig1_name, pl1_name, jig2_name, pl2_name, prop_id)

        for (prop_id, (jig1_name, rack1_name, jig2_name, rack2_name)) in self.pb_def.props_jig_to_rack_order:
            self._reify_prop_jig_to_rack_order(jig1_name, rack1_name, jig2_name, rack2_name, prop_id)

        for (prop_id, (jig_name, pl_name, flight_name)) in self.pb_def.props_jig_to_production_line_before_flight:
            self._reify_prop_jig_to_production_line_before_flight(jig_name, pl_name, flight_name, prop_id)

        for v in self.pb.base_variables:
            if v.name.startswith("hard_prop_"):
                self.pb.add_constraint(v)

    def solve_with_properties(
        self,
        prop_ids: list[PropId],
        num_swaps_to_use: int | None=None,
        timeout:float|None=None,
    ) -> tuple[Schedule, list[dict[str, str]]]:
        
        pb = self.pb.clone()

        if num_swaps_to_use is not None:
            pb.add_constraint(up.Equals(self.num_used_swaps, num_swaps_to_use)) # or also GE ? LE ? -> All have different pros/cons (depending on the situation, too...!..?)

        for prop_id in prop_ids:
            pb.add_constraint(self.properties[prop_id])

##        prop_ids_yes = ["id00","id01","id02","id03","id04","id05","id06","id07","id08","id09","id10"]
#        prop_ids_yes = ["id00","id01","id02","id03","id04","id06","id07","id08","id10"]
#        prop_ids_no = ["id05","id09"]
##        prop_ids_yes = ["id01","id02","id03","id04","id05","id06","id07"]
##        prop_ids_no = ["id00"]
#        for prop_id in prop_ids_yes:
#            pb.add_constraint(self.properties[prop_id])
#        for prop_id in prop_ids_no:
#            pb.add_constraint(up.Not(self.properties[prop_id]))

        pl = solve_problem(pb, timeout)

        pl_as_json = []

        if pl is not None:
            for a in pl.activities:
                if a.name.startswith("unload_beluga"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
                        "j": pl.assignment[a.get_parameter("j")].object().name,
                        "b": pl.assignment[a.get_parameter("b")].object().name,
                        "t": pl.assignment[a.get_parameter("t")].object().name,
                    }
                elif a.name.startswith("load_beluga"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
                        "j": pl.assignment[a.get_parameter("j")].object().name,
                        "b": pl.assignment[a.get_parameter("b")].object().name,
                        "t": pl.assignment[a.get_parameter("t")].object().name,
                    }
                elif a.name.startswith("put_down_rack"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
                        "j": pl.assignment[a.get_parameter("j")].object().name,
                        "t": pl.assignment[a.get_parameter("t")].object().name,
                        "r": pl.assignment[a.get_parameter("r")].object().name,
                        "s": pl.assignment[a.get_parameter("s")].object().name,
                    }
                elif a.name.startswith("pick_up_rack"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
                        "j": pl.assignment[a.get_parameter("j")].object().name,
                        "t": pl.assignment[a.get_parameter("t")].object().name,
                        "r": pl.assignment[a.get_parameter("r")].object().name,
                        "s": pl.assignment[a.get_parameter("s")].object().name,
                    }
                elif a.name.startswith("deliver_to_hangar"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
                        "j": pl.assignment[a.get_parameter("j")].object().name,
                        "h": pl.assignment[a.get_parameter("h")].object().name,
                        "t": pl.assignment[a.get_parameter("t")].object().name,
                        "pl": pl.assignment[a.get_parameter("pl")].object().name,
                    }
                elif a.name.startswith("get_from_hangar"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
                        "j": pl.assignment[a.get_parameter("j")].object().name,
                        "h": pl.assignment[a.get_parameter("h")].object().name,
                        "t": pl.assignment[a.get_parameter("t")].object().name,
                    }
                elif a.name.startswith("switch_to_next_beluga"):
                    aa = { 
                        "name": a.name[:a.name.find(self._get_activity_uid_prefix())],
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
        for hangar in self.pb_def.hangars:
            hangar_obj = self.pb.add_object(hangar.name, self.hangar_type)
            self.pb.set_initial_value(self.hangar_free(hangar_obj), True)
            self.hangar_objects[hangar.name] = hangar_obj
            if hangar.jig is not None:
                jig = self.pb_def.get_jig(hangar.jig)
                jig_obj = self.jig_objects[hangar.jig]
                self.pb.set_initial_value(self.at(jig_obj), hangar_obj)

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

        for trailer in self.pb_def.trailers_beluga:
            trailer_obj = self.pb.add_object(trailer.name, self.trailer_type)
            self.pb.set_initial_value(self.trailer_side(trailer_obj), self.side_beluga)
            self.trailer_objects[trailer.name] = trailer_obj
            if trailer.jig is not None:
                jig = self.pb_def.get_jig(trailer.jig)
                jig_obj = self.jig_objects[trailer.jig]
                self.pb.set_initial_value(self.at(jig_obj), trailer_obj)
        for trailer in self.pb_def.trailers_factory:
            trailer_obj = self.pb.add_object(trailer.name, self.trailer_type)
            self.pb.set_initial_value(self.trailer_side(trailer_obj), self.side_production)
            self.trailer_objects[trailer.name] = trailer_obj
            if trailer.jig is not None:
                jig = self.pb_def.get_jig(trailer.jig)
                jig_obj = self.jig_objects[trailer.jig]
                self.pb.set_initial_value(self.at(jig_obj), trailer_obj)

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

    def _load_to_trailer(self, a: Activity, jig, trailer, side):
        a.add_condition(up.StartTiming(), up.Equals(self.trailer_side(trailer), side))
        a.add_condition(up.StartTiming(), self.trailer_available(trailer))
        a.add_effect(up.EndTiming(), self.trailer_available(trailer), False)
        a.add_effect(up.EndTiming(), self.at(jig), trailer)

    def _unload_from_trailer(self, a: Activity, jig, trailer, side):
        a.add_condition(up.StartTiming(), up.Equals(self.trailer_side(trailer), side))
        a.add_condition(up.StartTiming(), up.Not(self.trailer_available(trailer))) # actually not needed ?
        a.add_effect(up.EndTiming(), self.trailer_available(trailer), True)
        a.add_condition(up.StartTiming(), up.Equals(self.at(jig), trailer))

    def _to_rack(self, a: Activity, jig, rack, side, oside):
        a.add_decrease_effect(up.EndTiming(), self.rack_free_space(rack), self.jig_size(jig))
        a.add_decrease_effect(up.EndTiming(), self.next_(rack, side), 1)
        a.add_effect(up.EndTiming(), self.pos(jig, side), self.next_(rack, side)-1)
        a.add_effect(up.EndTiming(), self.pos(jig, oside), -self.next_(rack, side)+1)
        a.add_effect(up.EndTiming(), self.at(jig), rack)
        a.add_condition(up.StartTiming(), up.Equals(oside, self.side_opposite(side)))

    def _from_rack(self, a: Activity, jig, rack, side, oside):
        a.add_increase_effect(up.EndTiming(), self.rack_free_space(rack), self.jig_size(jig))
        a.add_condition(up.StartTiming(), up.Equals(self.next_(rack, side), self.pos(jig, side)))
        a.add_increase_effect(up.EndTiming(), self.next_(rack, side), 1)
        a.add_condition(up.StartTiming(), up.Equals(self.at(jig), rack))
        a.add_condition(up.StartTiming(), up.Equals(oside, self.side_opposite(side)))

    def _get_activity_uid_prefix(self) -> str:
        return "_uid"

    def _new_activity_uid(self) -> str:
        res = "_uid"+str(self._activities_uid_counter)
        self._activities_uid_counter += 1
        return res

    def _make_new_unload_activity(self) -> Activity:
       
        unload_jig_from_beluga_to_trailer = self.pb.add_activity("unload_beluga"+self._new_activity_uid(), optional=True)
        unload_jig_from_beluga_to_trailer.add_parameter("j", self.jig_type)
        unload_jig_from_beluga_to_trailer.add_parameter("b", self.beluga_type)
        unload_jig_from_beluga_to_trailer.add_parameter("t", self.trailer_type)

        self._load_to_trailer(
            unload_jig_from_beluga_to_trailer,
            unload_jig_from_beluga_to_trailer.j,
            unload_jig_from_beluga_to_trailer.t,
            self.side_beluga,
        )
        unload_jig_from_beluga_to_trailer.add_condition(
            up.StartTiming(),
            up.Equals(
                self.at(unload_jig_from_beluga_to_trailer.j),
                unload_jig_from_beluga_to_trailer.b,
            ),
        )
        return unload_jig_from_beluga_to_trailer

    def _make_new_load_activity(self) -> Activity:

        load_jig_from_trailer_to_beluga = self.pb.add_activity("load_beluga"+self._new_activity_uid(), optional=True)
        load_jig_from_trailer_to_beluga.add_parameter("j", self.jig_type)
        load_jig_from_trailer_to_beluga.add_parameter("b", self.beluga_type)
        load_jig_from_trailer_to_beluga.add_parameter("t", self.trailer_type)

        self._unload_from_trailer(
            load_jig_from_trailer_to_beluga,
            load_jig_from_trailer_to_beluga.j,
            load_jig_from_trailer_to_beluga.t,
            self.side_beluga,
        )
        load_jig_from_trailer_to_beluga.add_effect(
            up.EndTiming(),
            self.at(load_jig_from_trailer_to_beluga.j),
            load_jig_from_trailer_to_beluga.b,
        )
        load_jig_from_trailer_to_beluga.add_condition(
            up.StartTiming(),
            self.jig_is_empty(load_jig_from_trailer_to_beluga.j),
        )
        return load_jig_from_trailer_to_beluga

    def _make_new_put_down_activity(self) -> Activity:
        putdown_jig_on_rack = self.pb.add_activity("put_down_rack"+self._new_activity_uid(), optional=True)
        putdown_jig_on_rack.add_parameter("j", self.jig_type)
        putdown_jig_on_rack.add_parameter("t", self.trailer_type)
        putdown_jig_on_rack.add_parameter("r", self.rack_type)
        putdown_jig_on_rack.add_parameter("s", self.side_type)
        putdown_jig_on_rack.add_parameter("os", self.side_type)
        putdown_jig_on_rack.add_parameter("rs", up.IntType(0, 1000))
        putdown_jig_on_rack.add_parameter("d", up.IntType(0, 1000))

        self._unload_from_trailer(
            putdown_jig_on_rack,
            putdown_jig_on_rack.j,
            putdown_jig_on_rack.t,
            putdown_jig_on_rack.s,
        )
        self._to_rack(
            putdown_jig_on_rack,
            putdown_jig_on_rack.j,
            putdown_jig_on_rack.r,
            putdown_jig_on_rack.s,
            putdown_jig_on_rack.os,
        )
        putdown_jig_on_rack.add_condition(
            up.StartTiming(),
            up.Equals(self.rack_size(putdown_jig_on_rack.r), putdown_jig_on_rack.rs),
        )
        return putdown_jig_on_rack

    def _make_new_pick_up_activity(self) -> Activity:
        pickup_jig_from_rack = self.pb.add_activity("pick_up_rack"+self._new_activity_uid(), optional=True)
        pickup_jig_from_rack.add_parameter("j", self.jig_type)
        pickup_jig_from_rack.add_parameter("t", self.trailer_type)
        pickup_jig_from_rack.add_parameter("r", self.rack_type)
        pickup_jig_from_rack.add_parameter("s", self.side_type)
        pickup_jig_from_rack.add_parameter("os", self.side_type)

        self._from_rack(
            pickup_jig_from_rack,
            pickup_jig_from_rack.j,
            pickup_jig_from_rack.r,
            pickup_jig_from_rack.s,
            pickup_jig_from_rack.os,
        )
        self._load_to_trailer(
            pickup_jig_from_rack,
            pickup_jig_from_rack.j,
            pickup_jig_from_rack.t,
            pickup_jig_from_rack.s,
        )
        return pickup_jig_from_rack

    def _make_new_deliver_jig_to_hangar_activity(self) -> Activity:
        deliver_jig_to_hangar = self.pb.add_activity("deliver_to_hangar"+self._new_activity_uid(), optional=True)
        deliver_jig_to_hangar.add_parameter("j", self.jig_type)
        deliver_jig_to_hangar.add_parameter("h", self.hangar_type)
        deliver_jig_to_hangar.add_parameter("t", self.trailer_type) 
        deliver_jig_to_hangar.add_parameter("pl", self.production_line_type)

        self._unload_from_trailer(
            deliver_jig_to_hangar,
            deliver_jig_to_hangar.j,
            deliver_jig_to_hangar.t,
            self.side_production,
        )
        deliver_jig_to_hangar.add_condition(up.StartTiming(), self.hangar_free(deliver_jig_to_hangar.h))
        deliver_jig_to_hangar.add_effect(up.EndTiming(), self.hangar_free(deliver_jig_to_hangar.h), False)
        deliver_jig_to_hangar.add_effect(
            up.EndTiming(),
            self.at(deliver_jig_to_hangar.j),
            deliver_jig_to_hangar.h,
        )
        deliver_jig_to_hangar.add_effect(
            up.EndTiming(),
            self.jig_size(deliver_jig_to_hangar.j),
            self.jig_size_empty(deliver_jig_to_hangar.j),
        )
        deliver_jig_to_hangar.add_effect(
            up.EndTiming(),
            self.jig_is_empty(deliver_jig_to_hangar.j),
            up.TRUE(),
        )
        return deliver_jig_to_hangar

    def _make_new_get_jig_from_hangar_activity(self) -> Activity:
        get_jig_from_hangar = self.pb.add_activity("get_from_hangar"+self._new_activity_uid(), optional=True)
        get_jig_from_hangar.add_parameter("j", self.jig_type)
        get_jig_from_hangar.add_parameter("h", self.hangar_type)
        get_jig_from_hangar.add_parameter("t", self.trailer_type)

        self._load_to_trailer(
            get_jig_from_hangar,
            get_jig_from_hangar.j,
            get_jig_from_hangar.t,
            self.side_production
        )
        get_jig_from_hangar.add_effect(up.EndTiming(), self.hangar_free(get_jig_from_hangar.h), True)
        get_jig_from_hangar.add_condition(
            up.StartTiming(),
            up.Equals(self.at(get_jig_from_hangar.j), get_jig_from_hangar.h),
        )
        return get_jig_from_hangar

    def _make_new_proceed_to_next_flight_activity(self) -> Activity:
        # proceed_to_next_flight = self.pb.add_activity("switch_to_next_beluga"+self._new_activity_uid(), optional=True)
        proceed_to_next_flight = self.pb.add_activity("switch_to_next_beluga"+self._new_activity_uid(), optional=False)
        proceed_to_next_flight.add_parameter("b", self.beluga_type)
        proceed_to_next_flight.add_condition(
            up.StartTiming(),
            up.Equals(self.beluga_next(self.beluga_current()), proceed_to_next_flight.b)
        )
        proceed_to_next_flight.add_effect(up.EndTiming(), self.beluga_current(), proceed_to_next_flight.b)
        return proceed_to_next_flight

    def _make_new_swap_subactivities(self) -> tuple[Activity, Activity]:
        pickup = self._make_new_pick_up_activity()
        putdown = self._make_new_put_down_activity()

        self.pb.add_constraint(up.Equals(pickup.j, putdown.j), scope=[pickup.present, putdown.present])
        self.pb.add_constraint(up.Equals(pickup.t, putdown.t), scope=[pickup.present, putdown.present])
        self.pb.add_constraint(up.Equals(pickup.s, putdown.s), scope=[pickup.present, putdown.present])
        self.pb.add_constraint(up.Equals(pickup.os, putdown.os), scope=[pickup.present, putdown.present])

        self.pb.add_constraint(up.LT(pickup.end, putdown.start), scope=[pickup.present, putdown.present])

        self.pb.add_constraint(up.Implies(putdown.present, pickup.present))

        return (pickup, putdown)

    def _add_proceeds(self):

        for flight in self.pb_def.flights[1:]:
            proceed_a = self._make_new_proceed_to_next_flight_activity()
            proceed_a.add_constraint(up.Equals(proceed_a.b, self.beluga_objects[flight.name]))
            # self.pb.add_constraint(proceed_a.present)
            for (_, earlier_proceed_a) in self.all_proceeds_to_next_flight:
                self.pb.add_constraint(up.LT(earlier_proceed_a.end, proceed_a.start), scope=[earlier_proceed_a.present, proceed_a.present])
            self.all_proceeds_to_next_flight.append((flight.name, proceed_a))

    def _add_flights_unloads_w_opt_putdowns(self):

        for flight_index in range(self.num_flights):

            earlier_unloads = [] # Put outside of loop ? *A priori*, see no difference in the model's "behavior" / conflicts computed ...
            beluga_name = self.pb_def.flights[flight_index].name
            incoming_jigs = self.pb_def.flights[flight_index].incoming

            for i, jig_name in sorted(incoming_jigs.items()):

                unload_a = self._make_new_unload_activity()
                unload_a.add_constraint(up.Equals(unload_a.j, self.jig_objects[jig_name]))
                unload_a.add_constraint(up.Equals(unload_a.b, self.beluga_objects[beluga_name]))

                putdown_a = self._make_new_put_down_activity()
                putdown_a.add_constraint(up.Equals(putdown_a.j, self.jig_objects[jig_name]))
                putdown_a.add_constraint(up.Equals(putdown_a.s, self.side_beluga))

#                self.pb.add_constraint(up.Iff(unload_a.present, putdown_a.present))
                self.pb.add_constraint(up.Implies(putdown_a.present, unload_a.present)) # "helper" constraint

#                self.pb.add_constraint(up.And(putdown_a.present, up.LT(unload_a.end, putdown_a.start)), scope=[unload_a.present])
                self.pb.add_constraint(up.LT(unload_a.end, putdown_a.start), scope=[unload_a.present, putdown_a.present])

                if flight_index > 0:
                    (_, prev_proceed) = self.all_proceeds_to_next_flight[flight_index-1]
                    self.pb.add_constraint(up.LT(prev_proceed.end, unload_a.start), scope=[unload_a.present, prev_proceed.present])

                if flight_index < self.num_flights-1:
                    (_, next_proceed) = self.all_proceeds_to_next_flight[flight_index]
                    self.pb.add_constraint(up.LT(unload_a.end, next_proceed.start), scope=[unload_a.present, next_proceed.present])

                for earlier_unload_a in earlier_unloads:
                    self.pb.add_constraint(up.LT(earlier_unload_a.end, unload_a.start), scope=[unload_a.present, earlier_unload_a.present])
#                    self.pb.add_constraint(up.And(earlier_unload_a.present, up.LT(earlier_unload_a.end, unload_a.start)), scope=[unload_a.present])

                self.all_unloads_w_putdowns[(jig_name, beluga_name, i)] = (unload_a, putdown_a)
                self.all_putdowns.append(putdown_a)

                earlier_unloads.append(unload_a)

    def _add_flights_loads_w_pickups(self):

        for flight_index in range(self.num_flights):

            earlier_loads = [] # Put outside of loop ? *A priori*, see no difference in the model's "behavior" / conflicts computed ...
            beluga_name = self.pb_def.flights[flight_index].name
            outgoing_jigs = self.pb_def.flights[flight_index].outgoing

            for i, jig_or_jig_type_name in sorted(outgoing_jigs.items()):

                pickup_a = self._make_new_pick_up_activity()

                if jig_or_jig_type_name.startswith("jig"):
                    concrete_jig = jig_or_jig_type_name
                    aux_jig_var_or_obj = self.jig_objects[concrete_jig]
                else:
                    concrete_jig = None
                    assert jig_or_jig_type_name.startswith("type")
                    aux_jig_var_or_obj = self.pb.add_variable(f"_aux_jig_{pickup_a.name}", self.jig_subtypes[jig_or_jig_type_name])

                pickup_a.add_constraint(up.Equals(pickup_a.j, aux_jig_var_or_obj))
                pickup_a.add_constraint(up.Equals(pickup_a.s, self.side_beluga))

                load_a = self._make_new_load_activity()
                load_a.add_constraint(up.Equals(load_a.j, aux_jig_var_or_obj))
                load_a.add_constraint(up.Equals(load_a.b, self.beluga_objects[beluga_name]))

                self.pb.add_constraint(up.Iff(load_a.present, pickup_a.present))
#                self.pb.add_constraint(up.Implies(load_a.present, pickup_a.present))

#                self.pb.add_constraint(up.And(pickup_a.present, up.LT(pickup_a.end, load_a.start)), scope=[load_a.present])
                self.pb.add_constraint(up.LT(pickup_a.end, load_a.start), scope=[load_a.present, pickup_a.present])

                if flight_index > 0:
                    (_, prev_proceed) = self.all_proceeds_to_next_flight[flight_index-1]
#                    self.pb.add_constraint(up.And(prev_proceed.present, up.LT(prev_proceed.end, load_a.start)), scope=[load_a.present])
                    self.pb.add_constraint(up.LT(prev_proceed.end, load_a.start), scope=[load_a.present, prev_proceed.present])

                if flight_index < self.num_flights-1:
                    (_, next_proceed) = self.all_proceeds_to_next_flight[flight_index]
                    self.pb.add_constraint(up.LT(load_a.end, next_proceed.start), scope=[load_a.present, next_proceed.present])

                for earlier_load_a in earlier_loads:
                    self.pb.add_constraint(up.LT(earlier_load_a.end, load_a.start), scope=[load_a.present, earlier_load_a.present])
#                    self.pb.add_constraint(up.And(earlier_load_a.present, up.LT(earlier_load_a.end, load_a.start)), scope=[load_a.present])

                self.all_loads_w_pickups[(jig_or_jig_type_name, beluga_name, i)] = (load_a, pickup_a)
                self.all_pickups.append(pickup_a)

                earlier_loads.append(load_a)

    def _add_pls_deliveries_w_pickups_and_retrievals_w_opt_putdowns(self):

        for production_line in self.pb_def.production_lines:

            earlier_delivers = []

            for i, jig_name in sorted(production_line.schedule.items()):

                # pickup + deliver

                pickup_a = self._make_new_pick_up_activity()
                pickup_a.add_constraint(up.Equals(pickup_a.j, self.jig_objects[jig_name]))
                pickup_a.add_constraint(up.Equals(pickup_a.s, self.side_production))

                deliver_a = self._make_new_deliver_jig_to_hangar_activity()
                deliver_a.add_constraint(up.Equals(deliver_a.j, self.jig_objects[jig_name]))
                deliver_a.add_constraint(up.Equals(deliver_a.pl, self.production_line_objects[production_line.name]))

#                self.pb.add_constraint(up.Iff(deliver_a.present, pickup_a.present))
                self.pb.add_constraint(up.Implies(deliver_a.present, pickup_a.present))

#                self.pb.add_constraint(up.And(pickup_a.present, up.LT(pickup_a.end, deliver_a.start)), scope=[deliver_a.present])
                self.pb.add_constraint(up.LT(pickup_a.end, deliver_a.start), scope=[deliver_a.present, pickup_a.present])

                for earlier_deliver_a in earlier_delivers:
                    self.pb.add_constraint(up.LT(earlier_deliver_a.end, deliver_a.start), scope=[earlier_deliver_a.present, deliver_a.present])
#                    self.pb.add_constraint(up.And(earlier_deliver_a.present, up.LT(earlier_deliver_a.end, deliver_a.start)), scope=[deliver_a.present])

                self.all_delivers_w_pickups[(jig_name, production_line.name, i)] = (deliver_a, pickup_a)
                self.all_pickups.append(pickup_a)

                earlier_delivers.append(deliver_a)

                # get + putdown

                get_a = self._make_new_get_jig_from_hangar_activity()
                get_a.add_constraint(up.Equals(get_a.j, self.jig_objects[jig_name]))
                self.pb.add_constraint(up.Equals(get_a.h, deliver_a.h), scope=[get_a.present, deliver_a.present])

                self.pb.add_constraint(up.LT(deliver_a.end, get_a.start), scope=[deliver_a.present, get_a.present])

                putdown_a = self._make_new_put_down_activity()
                putdown_a.add_constraint(up.Equals(putdown_a.j, self.jig_objects[jig_name]))
                putdown_a.add_constraint(up.Equals(putdown_a.s, self.side_production))

                self.pb.add_constraint(up.LT(get_a.end, putdown_a.start), scope=[get_a.present, putdown_a.present])

                self.pb.add_constraint(up.Implies(putdown_a.present, get_a.present))

                self.all_gets_w_putdowns[jig_name] = (get_a, putdown_a)
                self.all_putdowns.append(putdown_a)

    def _add_swaps(self):
        """Adding a limited number of allowed swaps to the task network. Uniquely identifiable because of their ids' ordering"""

        self.num_used_swaps = self.pb.add_variable("num_used_swaps", up.IntType(0, self.num_available_swaps))

        prev_pickup_a = None
        for i in range(self.num_available_swaps):
            pickup_a, putdown_a = self._make_new_swap_subactivities()

            self.pb.add_constraint(up.Iff(up.LT(i, self.num_used_swaps), pickup_a.present))
            # self.pb.add_constraint(up.Implies(putdown_a.present, pickup_a.present))
            self.pb.add_constraint(up.Iff(putdown_a.present, pickup_a.present))

            if prev_pickup_a is not None:
                self.pb.add_constraint(up.LT(prev_pickup_a.start, pickup_a.start), scope=[prev_pickup_a.present, pickup_a.present])
                self.pb.add_constraint(up.Implies(pickup_a.present, prev_pickup_a.present))
            prev_pickup_a = pickup_a

            self.all_swap_pickups_n_putdowns[i] = (pickup_a, putdown_a)
            self.all_putdowns.append(putdown_a)

    def _add_trailers_initial_jigs_opt_putdowns(self):
        # TODO: force these to be before all actions on these jigs (for performance)

        for trailer_b in self.pb_def.trailers_beluga:
            if trailer_b.jig is None:
                continue
            putdown_a = self._make_new_put_down_activity()
            putdown_a.add_constraint(up.Equals(putdown_a.j, self.jig_objects[trailer_b.jig]))
            putdown_a.add_constraint(up.Equals(putdown_a.s, self.side_beluga))

            self.all_putdowns.append(putdown_a)

        for trailer_f in self.pb_def.trailers_factory:
            if trailer_f.jig is None:
                continue
            putdown_a = self._make_new_put_down_activity()
            putdown_a.add_constraint(up.Equals(putdown_a.j, self.jig_objects[trailer_f.jig]))
            putdown_a.add_constraint(up.Equals(putdown_a.s, self.side_production))

            self.all_putdowns.append(putdown_a)

    def _add_hangars_initial_jigs_retrievals_w_opt_putdowns(self):
        # TODO: force these to be before all actions on these jigs (for performance)

        for hangar in self.pb_def.hangars:
            if hangar.jig is None:
                continue

            get_a = self._make_new_get_jig_from_hangar_activity()
            get_a.add_constraint(up.Equals(get_a.j, self.jig_objects[hangar.jig]))
            get_a.add_constraint(up.Equals(get_a.h, self.hangar_objects[hangar.name]))

            putdown_a = self._make_new_put_down_activity()
            putdown_a.add_constraint(up.Equals(putdown_a.j, self.jig_objects[hangar.jig]))
            putdown_a.add_constraint(up.Equals(putdown_a.s, self.side_production))

            self.pb.add_constraint(up.LT(get_a.end, putdown_a.start), scope=[get_a.present, putdown_a.present])

            self.pb.add_constraint(up.Implies(putdown_a.present, get_a.present))

            self.all_putdowns.append(putdown_a)

    def _add_opt_pickup_for_each_jig_last_non_swap(self):

        for _, jig_obj in self.jig_objects.items():
            pickup_a = self._make_new_pick_up_activity()
            pickup_a.add_constraint(up.Equals(pickup_a.j, jig_obj))

            self.all_pickups.append(pickup_a)

    def _reify_prop_rack_always_empty(
        self,
        rack_name: str,
        prop_id: PropId | None,
    ) -> up.Parameter:

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_{rack_name}_always_empty" if prop_id is not None else f"{rack_name}_always_empty"

        if self.pb.has_name(reif_name):
            r_always_empty = self.pb.get_variable(reif_name)
        else:
            r_always_empty = self.pb.add_variable(reif_name, up.BoolType())

            terms = []

            rack_initially_empty = up.Bool(
                self.pb.explicit_initial_values[self.rack_free_space(self.rack_objects[rack_name])]
                == self.pb.explicit_initial_values[self.rack_size(self.rack_objects[rack_name])]
            )
            terms += [rack_initially_empty]
            #terms += [up.Implies(putdown.present, up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name])))
            #          for (_, putdown) in self.all_unloads_w_putdowns.values()]
            #terms += [up.Implies(putdown.present, up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name])))
            #          for (_, putdown) in self.all_gets_w_putdowns.values()]
            #terms += [up.Implies(putdown.present, up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name])))
            #          for (_, putdown) in self.all_swap_pickups_n_putdowns.values()]
            terms += [up.Implies(putdown.present, up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name])))
                      for putdown in self.all_putdowns]

            self.pb.add_constraint(up.Iff(r_always_empty, up.And(terms)))

        return r_always_empty

    def _reify_prop_at_least_one_rack_always_empty(
        self,
        prop_id: PropId | None,
    ) -> up.Parameter:
        """
        Ideally (for performance) this should be called after all `_reify_prop_rack_always_empty` have been called.

        Note that this property concerns *all* racks, not just the ones specified in "rack always empty" properties !
        """

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_at_least_one_rack_always_empty" if prop_id is not None else f"at_least_one_rack_always_empty"

        if self.pb.has_name(reif_name):
            at_least_one_rack_always_empty = self.pb.get_variable(reif_name)
        else:
            at_least_one_rack_always_empty = self.pb.add_variable(reif_name, up.BoolType())

            terms = []

            for _r in self.pb_def.racks:
                rack_name = _r.name

                found_among_props_rack_always_empty = False
                for (pid, rn) in self.pb_def.props_rack_always_empty:
                    if rn == rack_name:
                        terms += [self._reify_prop_rack_always_empty(rack_name, pid)]
                        found_among_props_rack_always_empty = True
                        break
                if not found_among_props_rack_always_empty:
                    terms += [self._reify_prop_rack_always_empty(rack_name, None)]

            self.pb.add_constraint(up.Iff(at_least_one_rack_always_empty, up.Or(terms)))

        return at_least_one_rack_always_empty

    def _reify_prop_jig_always_placed_on_rack_shorter_or_same_size_as(
        self,
        jig_name: str,
        max_allowed_rack_size: int,
        prop_id: PropId | None,
    ) -> up.Parameter:

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_{jig_name}_always_placed_on_rack_shorter_or_same_size_as" if prop_id is not None else f"{jig_name}_always_placed_on_rack_shorter_or_same_size_as"

        if self.pb.has_name(reif_name):
            jig_always_placed_on_rack_shorter_or_same_size_as = self.pb.get_variable(reif_name)
        else:
            jig_always_placed_on_rack_shorter_or_same_size_as = self.pb.add_variable(reif_name, up.BoolType())

            terms = []

            _temp = self.pb.explicit_initial_values.get(self.at(self.jig_objects[jig_name]), None)
            if _temp is not None and _temp.object() in self.rack_objects.values(): # (if initially at a rack, and not a beluga for example)
                rack_jig_is_initially_at = _temp.object()
            else:
                rack_jig_is_initially_at = None

            if rack_jig_is_initially_at is not None:
                assert self.rack_size(rack_jig_is_initially_at) in self.pb.explicit_initial_values
                terms += [up.LE(self.pb.explicit_initial_values[self.rack_size(rack_jig_is_initially_at)], max_allowed_rack_size)]

            #terms += [up.Implies(putdown.present, up.LE(putdown.get_parameter("rs"), max_allowed_rack_size))
            #          for (_, putdown) in self.all_unloads_w_putdowns.values()]
            #terms += [up.Implies(putdown.present, up.LE(putdown.get_parameter("rs"), max_allowed_rack_size))
            #          for (_, putdown) in self.all_gets_w_putdowns.values()]
            #terms += [up.Implies(putdown.present, up.LE(putdown.get_parameter("rs"), max_allowed_rack_size))
            #          for (_, putdown) in self.all_swap_pickups_n_putdowns.values()]
            terms += [up.Implies(putdown.present, up.LE(putdown.get_parameter("rs"), max_allowed_rack_size))
                      for putdown in self.all_putdowns]

            self.pb.add_constraint(up.Iff(jig_always_placed_on_rack_shorter_or_same_size_as, up.And(terms)))

        return jig_always_placed_on_rack_shorter_or_same_size_as

    def _reify_prop_num_swaps_used_leq_val(
        self,
        val: int,
        prop_id: PropId | None,
    ) -> up.Parameter:

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_num_swaps_used_leq_{val}" if prop_id is not None else f"num_swaps_used_leq_{val}"

        if self.pb.has_name(reif_name):
            num_swaps_used_leq_val = self.pb.get_variable(reif_name)
        else:
            num_swaps_used_leq_val = self.pb.add_variable(reif_name, up.BoolType())

            self.pb.add_constraint(up.Iff(num_swaps_used_leq_val, up.LE(self.num_used_swaps, val)))

        return num_swaps_used_leq_val

    def _reify_prop_jig_never_on_rack(
        self,
        jig_name: str,
        rack_name: str,
        prop_id: PropId | None,
    ) -> up.Parameter:

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_{jig_name}_never_on_{rack_name}"

        if self.pb.has_name(reif_name):
            jig_never_on_rack = self.pb.get_variable(reif_name)
        else:
            jig_never_on_rack = self.pb.add_variable(reif_name, up.BoolType())

            terms = []

            _temp = self.pb.explicit_initial_values.get(self.at(self.jig_objects[jig_name]), None)
            if _temp is not None and _temp.object() in self.rack_objects.values(): # (if initially at a rack, and not a beluga for example)
                rack_jig_is_initially_at = _temp.object()
            else:
                rack_jig_is_initially_at = None

            if rack_jig_is_initially_at is not None:
                terms += [up.Not(up.Equals(rack_jig_is_initially_at, self.rack_objects[rack_name]))]

            #terms += [up.Implies(putdown.present,
            #                     up.Implies(up.Equals(putdown.get_parameter("j"), self.jig_objects[jig_name]),
            #                                up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name]))))
            #          for (_, putdown) in self.all_unloads_w_putdowns.values()]
            #terms += [up.Implies(putdown.present,
            #                     up.Implies(up.Equals(putdown.get_parameter("j"), self.jig_objects[jig_name]),
            #                                up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name]))))
            #          for (_, putdown) in self.all_gets_w_putdowns.values()]
            #terms += [up.Implies(putdown.present,
            #                     up.Implies(up.Equals(putdown.get_parameter("j"), self.jig_objects[jig_name]),
            #                                up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name]))))
            #          for (_, putdown) in self.all_swap_pickups_n_putdowns.values()]
            
            terms += [up.Implies(putdown.present,
                                 up.Implies(up.Equals(putdown.get_parameter("j"), self.jig_objects[jig_name]),
                                            up.Not(up.Equals(putdown.get_parameter("r"), self.rack_objects[rack_name]))))
                      for putdown in self.all_putdowns]

            self.pb.add_constraint(up.Iff(jig_never_on_rack, up.And(terms)))

        return jig_never_on_rack

    def _reify_prop_jig_only_if_ever_on_rack(
        self,
        jig_name: str,
        rack_name: str,
        prop_id: PropId | None,
    ) -> up.Parameter:
        """
        Ideally (for performance) this should be called after all `_reify_prop_jig_never_on_rack` have been called.
        """

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_{jig_name}_only_if_ever_on_{rack_name}"

        if self.pb.has_name(reif_name):
            jig_only_if_ever_on_rack = self.pb.get_variable(reif_name)
        else:
            jig_only_if_ever_on_rack = self.pb.add_variable(reif_name, up.BoolType())

            terms = []
            for _r in self.pb_def.racks:
                if rack_name == _r.name:
                    continue

                found_among_props_jig_never_on_rack = False
                for (pid, (jn, rn)) in self.pb_def.props_jig_never_on_rack:
                    if jn == jig_name and rn == _r.name:
                        terms += [self._reify_prop_jig_never_on_rack(jig_name, _r.name, pid)]
                        found_among_props_jig_never_on_rack = True
                        break
                if not found_among_props_jig_never_on_rack:
                    terms += [self._reify_prop_jig_never_on_rack(jig_name, _r.name, None)]

            # "jig only if ever on rack" encoded as "jig never on any other racks"
            self.pb.add_constraint(up.Iff(jig_only_if_ever_on_rack, up.And(terms)))

        return jig_only_if_ever_on_rack

    def _reify_prop_jig_to_production_line_order(
        self,
        jig1_name: str,
        pl1_name: str,
        jig2_name: str,
        pl2_name: str,
        prop_id: PropId | None,
    ) -> up.Parameter:
        
        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_jig_to_production_line_order_{jig1_name}_{pl1_name}_{jig2_name}_{pl2_name}"

        if self.pb.has_name(reif_name):
            j1_delivered_to_pl1_before_j2_delivered_to_pl2 = self.pb.get_variable(reif_name)
        else:
            j1_delivered_to_pl1_before_j2_delivered_to_pl2 = self.pb.add_variable(reif_name, up.BoolType())

            deliver1_a = None
            deliver2_a = None
            for (jn, pln, _), (deliver_a, _) in self.all_delivers_w_pickups.items():
                if jn == jig1_name and pln == pl1_name:
                    deliver1_a = deliver_a
                if jn == jig2_name and pln == pl2_name:
                    deliver2_a = deliver_a

            self.pb.add_constraint(
                up.Iff(
                    j1_delivered_to_pl1_before_j2_delivered_to_pl2,
                    up.And(
                        deliver1_a.present if deliver1_a is not None else up.FALSE(),
                        deliver2_a.present if deliver2_a is not None else up.FALSE(),
                        up.LE(deliver1_a.end, deliver2_a.start) if deliver1_a is not None and deliver2_a is not None else up.FALSE()
                    ),
                )
            )

        return j1_delivered_to_pl1_before_j2_delivered_to_pl2

    def _reify_prop_jig_to_rack_order(
        self,
        jig1_name: str,
        rack1_name: str,
        jig2_name: str,
        rack2_name: str,
        prop_id: PropId | None,
    ) -> up.Parameter:

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_reify_prop_jig_to_rack_order_{jig1_name}_{rack1_name}_{jig2_name}_{rack2_name}"

        if self.pb.has_name(reif_name):
            jig1_putdown_on_rack1_before_jig2_putdown_on_rack2 = self.pb.get_variable(reif_name)
        else:
            jig1_putdown_on_rack1_before_jig2_putdown_on_rack2 = self.pb.add_variable(reif_name, up.BoolType())

            all_putdowns = []
            #all_putdowns += [putdown_a for _, putdown_a in self.all_unloads_w_putdowns.values()]
            #all_putdowns += [putdown_a for _, putdown_a in self.all_gets_w_putdowns.values()]
            #all_putdowns += [putdown_a for _, putdown_a in self.all_swap_pickups_n_putdowns.values()]
            all_putdowns = self.all_putdowns

            self.pb.add_constraint(
                up.Iff(
                    jig1_putdown_on_rack1_before_jig2_putdown_on_rack2,
                    up.Or(
                        up.And(
                            up.Equals(putdown1_a.get_parameter("j"), self.rack_objects[jig1_name]),
                            up.Equals(putdown1_a.get_parameter("r"), self.rack_objects[rack1_name]),
                            up.Equals(putdown2_a.get_parameter("j"), self.rack_objects[jig2_name]),
                            up.Equals(putdown2_a.get_parameter("r"), self.rack_objects[rack2_name]),
                            up.LT(putdown1_a.end, putdown2_a.start),
                        )
                        for putdown1_a in all_putdowns for putdown2_a in all_putdowns
                    )
                )
            )

        return jig1_putdown_on_rack1_before_jig2_putdown_on_rack2

    def _reify_prop_jig_to_production_line_before_flight(
        self,
        jig_name: str,
        pl_name: str,
        beluga_name: str,
        prop_id: PropId | None,
    ) -> up.Parameter:

        reif_name = f"{'hard_' if prop_id in self.pb_def.props_ids_hard_list else ''}prop_{prop_id}_reify_prop_jig_to_production_line_before_flight_{jig_name}_{pl_name}_{beluga_name}"

        if self.pb.has_name(reif_name):
            jig_delivered_to_pl_before_flight = self.pb.get_variable(reif_name)
        else:
            jig_delivered_to_pl_before_flight = self.pb.add_variable(reif_name, up.BoolType())

            deliver_a = None
            for (jn, pln, _), (_deliver_a, _) in self.all_delivers_w_pickups.items():
                if jn == jig_name and pln == pl_name:
                    deliver_a = _deliver_a
                    break
            proceed_a = None # FIXME TODO !!! what if the 1st flight is selected ? nothing can be before it and there is no corresponding "proceed" action... 
            for bn, _proceed_a in self.all_proceeds_to_next_flight:
                if bn == beluga_name:
                    proceed_a = _proceed_a
                    break

            self.pb.add_constraint(
                up.Iff(
                    jig_delivered_to_pl_before_flight,
                    up.And(
                        deliver_a.present if deliver_a is not None else up.FALSE(),
                        proceed_a.present if proceed_a is not None else up.FALSE(),
                        up.LE(deliver_a.end, proceed_a.start) if deliver_a is not None and proceed_a is not None else up.FALSE()
                    ),
                )
            )

        return jig_delivered_to_pl_before_flight