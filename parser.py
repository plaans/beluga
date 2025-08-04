from dataclasses import dataclass, field
from types import SimpleNamespace

import json

# # # 

@dataclass 
class Trailer:
    name: str
    jig: str | None

@dataclass 
class Hangar:
    name: str
    jig: str | None

@dataclass 
class JigType:
    name: str
    size_empty: int
    size_loaded: int

@dataclass
class Rack:
    name: str
    size: int
    jigs: list[str]

@dataclass
class Jig:
    name: str
    type: str
    empty: bool

@dataclass
class ProductionLine:
    name: str
    schedule: dict[int, str]

@dataclass
class Flight:
    name: str
    incoming: dict[int, str]  # jigs
    outgoing: dict[int, str]  # jig types or individual jigs

# # # 

class PropId(str):
    pass

@dataclass
class BelugaProblemDef:
    trailers_beluga: list[Trailer]
    trailers_factory: list[Trailer]
    hangars: list[Hangar]
    jig_types: list[JigType]
    racks: list[Rack]
    jigs: list[Jig]
    production_lines: list[ProductionLine]
    flights: list[Flight]

    props_unload_beluga: list[tuple[PropId, tuple[str, str, int]]] = field(default_factory=lambda:[])
    props_load_beluga: list[tuple[PropId, tuple[str, str, int]]] = field(default_factory=lambda:[])
    props_deliver_to_production_line: list[tuple[PropId, tuple[str, str, int]]] = field(default_factory=lambda:[])
    
    props_rack_always_empty: list[tuple[PropId, str]] = field(default_factory=lambda:[])
    prop_at_least_one_rack_always_empty: PropId | None = None
    props_jig_always_placed_on_rack_size_leq: list[tuple[PropId, tuple[str, int]]] = field(default_factory=lambda:[])
    props_num_swaps_used_leq: list[tuple[PropId, int]] = field(default_factory=lambda:[])

    props_jig_never_on_rack: list[tuple[PropId, tuple[str, str]]] = field(default_factory=lambda:[])
    props_jig_only_if_ever_on_rack: list[tuple[PropId, tuple[str, str]]] = field(default_factory=lambda:[])
    props_jig_to_production_line_order: list[tuple[PropId, tuple[str, str, str, str]]] = field(default_factory=lambda:[])
    props_jig_to_rack_order: list[tuple[PropId, tuple[str, str, str, str]]] = field(default_factory=lambda:[])
    props_jig_to_production_line_before_flight: list[tuple[PropId, tuple[str, str, str]]] = field(default_factory=lambda:[])

    props_ids_hard_list: list[PropId] = field(default_factory=lambda:[])

    def get_jig_type(self, name: str) -> JigType:
        return next(x for x in self.jig_types if x.name == name)

    def get_jig(self, name: str) -> Jig:
        return next(x for x in self.jigs if x.name == name)

@dataclass 
class BelugaPlanAction:
    name: str
    params: dict[str, str]

class BelugaPlanDef(list[BelugaPlanAction]):
    pass

@dataclass
class BelugaQuestion:
    type_: str
    params: dict[str, str]

# # #

def parse_plan(filename: str) -> BelugaPlanDef | None:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    plan_def = _parse_plan(d)
    return plan_def

def _parse_plan(d_plan) -> BelugaPlanDef:
    plan_def = BelugaPlanDef()
    for a in d_plan:
        name = a.name
        params = { k:v for (k,v) in vars(a).items() if k != 'name' }
        plan_def += [BelugaPlanAction(name, params)]
    return plan_def

# # # 

def parse_problem(filename: str) -> BelugaProblemDef:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    pb_def = _parse_problem_base(d)
    return pb_def

def _parse_problem_base(d) -> BelugaProblemDef:
    pb_def = BelugaProblemDef(
        trailers_beluga=[Trailer(t.name, t.jig if hasattr(t, "jig") and t.jig != "" else None) for t in d.trailers_beluga],
        trailers_factory=[Trailer(t.name, t.jig if hasattr(t, "jig") and t.jig != "" else None) for t in d.trailers_factory],
        hangars=[Hangar(h, None) if isinstance(h, str) else Hangar(h.name, h.jig if hasattr(h, "jig") and h.jig != "" else None) for h in d.hangars],
        jig_types=[JigType(jt.name, jt.size_empty, jt.size_loaded) for jt in vars(d.jig_types).values()],
        racks=[Rack(r.name, r.size, r.jigs) for r in d.racks],
        jigs=[Jig(r.name, r.type, r.empty) for r in vars(d.jigs).values()],
        production_lines=[ProductionLine(r.name, {i:a for (i,a) in enumerate(r.schedule)}) for r in d.production_lines],
        flights=[Flight(r.name, {i:a for (i,a) in enumerate(r.incoming)}, {i:a for (i,a) in enumerate(r.outgoing)}) for r in d.flights],
    )
    return pb_def

# # # 

def parse_problem_and_properties(problem_base_filename: str, problem_properties_filename: str | None):
    production_lines: list[ProductionLine] = []
    flights: list[Flight] = []

    with open(problem_base_filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
        trailers_beluga=[Trailer(t.name, t.jig if hasattr(t, "jig") and t.jig != "" else None) for t in d.trailers_beluga]
        trailers_factory=[Trailer(t.name, t.jig if hasattr(t, "jig") and t.jig != "" else None) for t in d.trailers_factory]
        hangars=[Hangar(h, None) if isinstance(h, str) else Hangar(h.name, h.jig if hasattr(h, "jig") and h.jig != "" else None) for h in d.hangars]
        jig_types=[JigType(jt.name, jt.size_empty, jt.size_loaded) for jt in vars(d.jig_types).values()]
        racks=[Rack(r.name, r.size, r.jigs) for r in d.racks]
        jigs=[Jig(r.name, r.type, r.empty) for r in vars(d.jigs).values()]
        production_lines=[ProductionLine(r.name, {i:a for (i,a) in enumerate(r.schedule)}) for r in d.production_lines]
        flights=[Flight(r.name, {i:a for (i,a) in enumerate(r.incoming)}, {i:a for (i,a) in enumerate(r.outgoing)}) for r in d.flights]

    props_unload_beluga = []
    props_load_beluga = []
    props_deliver_to_production_line = []
    props_rack_always_empty = []
    prop_at_least_one_rack_always_empty = None
    props_jig_always_placed_on_rack_size_leq = []
    props_num_swaps_used_leq = []
    props_jig_never_on_rack = []
    props_jig_only_if_ever_on_rack = []
    props_jig_to_production_line_order = []
    props_jig_to_rack_order = []
    props_jig_to_production_line_before_flight = []

    if problem_properties_filename is not None and problem_properties_filename != "":

        with open(problem_properties_filename) as f:
            d = json.load(f)

            for property_w_id in d:
                
                prop_id = PropId(property_w_id["_id"])
                name, params = property_w_id["definition"]["name"], property_w_id["definition"]["parameters"]
                
                if name == "unload_beluga":
                    jig, flight, i_unloading = params[0], params[1], int(params[2])
                    fl = None
                    for fl_ in flights:
                        if fl_.name == flight:
                            fl = fl_
                            if i_unloading in fl.incoming:
                                fl.incoming = { (k if k < i_unloading else k+1):v for k,v in fl.incoming.items() }
                            assert i_unloading not in fl.incoming
                            fl.incoming[i_unloading] = jig
                            break
                    props_unload_beluga.append((prop_id, (jig, flight, i_unloading)))

                elif name == "load_beluga":
                    jig, flight, i_loading = params[0], params[1], int(params[2])
                    fl = None
                    for fl_ in flights:
                        if fl_.name == flight:
                            fl = fl_
                            if i_loading in fl.outgoing:
                                fl.outgoing = { (k if k < i_loading else k+1):v for k,v in fl.outgoing.items() }
                            assert i_loading not in fl.outgoing
                            fl.outgoing[i_loading] = jig
                            break
                    props_load_beluga.append((prop_id, (jig, flight, i_loading)))

                elif name == "deliver_to_production_line":
                    jig, pl_name, i = params[0], params[1], int(params[2])
                    pl = None
                    for pl_ in production_lines:
                        if pl_.name in pl_name:
                            pl = pl_
                            if i in pl.schedule:
                                pl.schedule = { (k if k < i else k+1):v for k,v in pl.schedule.items() }
                            assert i not in pl.schedule
                            pl.schedule[i] = jig
                            break
                    props_deliver_to_production_line.append((prop_id, (jig, pl_name, i)))

                elif name == "rack_always_empty":
                    rack_name = params[0]
                    props_rack_always_empty.append((prop_id, rack_name))

                elif name == "at_least_one_rack_always_empty":
                    prop_at_least_one_rack_always_empty = prop_id

                elif name == "jig_always_placed_on_rack_size_leq":
                    jig_name, num = params[0], params[1]
                    props_jig_always_placed_on_rack_size_leq.append((prop_id, (jig_name, num)))

                elif name == "num_swaps_used_leq":
                    num = int(params[0])
                    props_num_swaps_used_leq.append((prop_id, num))

                elif name == "jig_never_on_rack":
                    jig, rack = params[0], params[1]
                    props_jig_never_on_rack.append((prop_id, (jig, rack)))

                elif name == "jig_only_if_ever_on_rack":
                    jig, rack = params[0], params[1]
                    props_jig_only_if_ever_on_rack.append((prop_id, (jig, rack)))

                elif name == "jig_to_production_line_order":
                    jig1, pl1, jig2, pl2 = params[0], params[1], params[2], params[3]
                    props_jig_to_production_line_order.append((prop_id, (jig1, pl1, jig2, pl2)))

                elif name == "jig_to_rack_order":
                    jig1, rack1, jig2, rack2 = params[0], params[1], params[2], params[3]
                    props_jig_to_rack_order.append((prop_id, (jig1, rack1, jig2, rack2)))

                elif name == "jig_to_production_line_before_flight":
                    jig, pl, flight = params[0], params[1], params[2]
                    props_jig_to_production_line_before_flight.append((prop_id, (jig, pl, flight)))

                else:
                    print("unsupported spec {}".format(name))

    return BelugaProblemDef(
        trailers_beluga=trailers_beluga,
        trailers_factory=trailers_factory,
        hangars=hangars,
        jig_types=jig_types,
        racks=racks,
        jigs=jigs,
        production_lines=production_lines,
        flights=flights,
        props_unload_beluga=props_unload_beluga,
        props_load_beluga=props_load_beluga,
        props_deliver_to_production_line=props_deliver_to_production_line,
        props_rack_always_empty=props_rack_always_empty,
        prop_at_least_one_rack_always_empty=prop_at_least_one_rack_always_empty,
        props_jig_always_placed_on_rack_size_leq=props_jig_always_placed_on_rack_size_leq,
        props_num_swaps_used_leq=props_num_swaps_used_leq,
        props_jig_never_on_rack=props_jig_never_on_rack,
        props_jig_only_if_ever_on_rack=props_jig_only_if_ever_on_rack,
        props_jig_to_production_line_order=props_jig_to_production_line_order,
        props_jig_to_rack_order=props_jig_to_rack_order,
        props_jig_to_production_line_before_flight=props_jig_to_production_line_before_flight,
    )

def convert_full_problem_props_to_properties(filename: str) -> tuple[str, str]:
    """
    Runs through unloads/loads (flights) and deliveries (production lines) in "legacy" full problem file.
    
    Outputs corresponding "base" and "props" json files.
    """

    with open(filename) as f:
        d = json.load(f)

        base_d = d
        props_d = []

        id_counter = 0
        for pl in d['production_lines']:
            for (i, j) in enumerate(pl['schedule']):
                props_d.append({
                    "_id": "id{}".format(id_counter),
                    "definition": {
                        "name": "deliver_to_production_line",
                        "parameters": [j, pl['name'], i]
                    }
                })
                id_counter += 1
        for fl in d['flights']:
            for (i, j) in enumerate(fl['incoming']):
                props_d.append({
                    "_id": "id{}".format(id_counter),
                    "definition": {
                        "name": "unload_beluga",
                        "parameters": [j, fl['name'], i]
                    }
                })
                id_counter += 1
            for (i, jt) in enumerate(fl['outgoing']):
                props_d.append({
                    "_id": "id{}".format(id_counter),
                    "definition": {
                        "name": "load_beluga",
                        "parameters": [jt, fl['name'], i]
                    }
                })
                id_counter += 1

        for i in range(len(base_d['production_lines'])):
            base_d['production_lines'][i]['schedule'] = []
        for i in range(len(base_d['flights'])):
            base_d['flights'][i]['incoming'] = []
            base_d['flights'][i]['outgoing'] = []

        import os

        (path, ext) = os.path.splitext(filename)
        problem_base_filename = path + "_base" + ext
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(problem_base_filename, "w") as f:
            json.dump(base_d, f, indent=4)

        (path, ext) = os.path.splitext(filename)
        problem_properties_filename = path + "_props" + ext
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(problem_properties_filename, "w") as f:
            json.dump(props_d, f, indent=4)

        return (problem_base_filename, problem_properties_filename)