from dataclasses import dataclass, field
from types import SimpleNamespace

import json

# # # 

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
    outgoing: dict[int, str]  # jig types # FIXME/TODO: and individual jigs too ?

# # # 

@dataclass
class BelugaProblemDef:
    trailers_beluga: list[str]
    trailers_factory: list[str]
    hangars: list[str]
    jig_types: list[JigType]
    racks: list[Rack]
    jigs: list[Jig]
    production_lines: list[ProductionLine]
    flights: list[Flight]

    rack_always_empty: list[str] = field(default_factory=lambda:[])
    use_at_least_one_rack_always_empty: bool = False
    jig_always_placed_on_rack_size_leq: list[tuple[str, int]] = field(default_factory=lambda:[])
    val_num_swaps_used_leq: int | None = None

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

# def parse_problem_and_plan_and_question(filename: str) -> tuple[BelugaProblemDef, BelugaPlanDef | None, BelugaQuestion]:
#     with open(filename) as f:
#         d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
#     pb_def = _parse_problem(d.instance)
#     plan_def = _parse_plan(d.plan) if hasattr(d, 'plan') and d.plan != ['UNSAT'] else None
#     question = _parse_question(d.question)
#     return (pb_def, plan_def, question)

# # # 

# def _parse_question(d_qst) -> BelugaQuestion:
#     return BelugaQuestion(type_=d_qst.type, params=d_qst.parameters.__dict__ if hasattr(d_qst, "parameters") else {})

# # # 

def parse_plan(filename: str) -> list[BelugaPlanAction] | None:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    # plan_def = _parse_plan(d.plan) if hasattr(d, 'plan') and d.plan != ['UNSAT'] else None
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

def parse_problem_full(filename: str) -> BelugaProblemDef:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    pb_def = _parse_problem(d)
    return pb_def

def _parse_problem(d) -> BelugaProblemDef:
    pb_def = BelugaProblemDef(
        trailers_beluga=[t.name for t in d.trailers_beluga],
        trailers_factory=[t.name for t in d.trailers_factory],
        hangars=[h for h in d.hangars],
        jig_types=[JigType(jt.name, jt.size_empty, jt.size_loaded) for jt in vars(d.jig_types).values()],
        racks=[Rack(r.name, r.size, r.jigs) for r in d.racks],
        jigs=[Jig(r.name, r.type, r.empty) for r in vars(d.jigs).values()],
        production_lines=[ProductionLine(r.name, {i:a for (i,a) in enumerate(r.schedule)}) for r in d.production_lines],
        flights=[Flight(r.name, {i:a for (i,a) in enumerate(r.incoming)}, {i:a for (i,a) in enumerate(r.outgoing)}) for r in d.flights],
    )
    return pb_def

# # # 

def parse_problem_specs_and_init_state(initial_state_filename: str, specifications_filename: str):
    with open(initial_state_filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
        trailers_beluga=[t.name for t in d.trailers_beluga]
        trailers_factory=[t.name for t in d.trailers_factory]
        hangars=[h for h in d.hangars]
        jig_types=[JigType(jt.name, jt.size_empty, jt.size_loaded) for jt in vars(d.jig_types).values()]
        racks=[Rack(r.name, r.size, r.jigs) for r in d.racks]
        jigs=[Jig(r.name, r.type, r.empty) for r in vars(d.jigs).values()]
        #production_lines=[ProductionLine(r.name, {i:a for (i,a) in enumerate(r.schedule)}) for r in d.production_lines],
        #flights=[Flight(r.name, {i:a for (i,a) in enumerate(r.incoming)}, {i:a for (i,a) in enumerate(r.outgoing)}) for r in d.flights],

    production_lines: list[ProductionLine] = []
    flights: list[Flight] = []
    _flights: list[tuple[int, Flight]] = []
    rack_always_empty: list[str] = []
    use_at_least_one_rack_always_empty: bool = False
    jig_always_placed_on_rack_size_leq: list[tuple[str, int]] = []
    num_swaps_used_leq: int | None = None

    def beluga_name(i):
        return "beluga"+str(i+1)

    with open(specifications_filename) as f:
        d = json.load(f)

        for property_w_id in d:
            
            # property_id = property_w_id["_id"]
            name, params = property_w_id["definition"]["name"], property_w_id["definition"]["parameters"]
            
            if name == "unload_beluga":
                jig, i_beluga, i_unloading = params[0], params[1], params[2]
                fl = None
                #for fl_ in flights:
                #    if fl_.name == beluga:
                #        fl = fl_
                #        assert i_unloading not in fl.incoming
                #        fl.incoming[i_unloading] = jig
                #        break
                #if fl is None:
                #    fl = Flight(name=beluga, incoming={i_unloading: jig}, outgoing=dict())
                #    flights.append(fl)
                #flights = sorted(flights, key=lambda f: f.name) # Ensure flights / belugas are ordered by name (beluga1, beluga2...)
                for (ii, fl_) in _flights:
                    if ii == i_beluga:
                        fl = fl_
                        assert i_unloading not in fl.incoming
                        fl.incoming[i_unloading] = jig
                        break
                if fl is None:
                    fl = Flight(name=beluga_name(i_beluga), incoming={i_unloading: jig}, outgoing=dict())
                    _flights.append((i_beluga, fl))
                _flights = sorted(_flights, key=lambda e: e[0])
                flights = [fl for (_, fl) in _flights]

            elif name == "load_beluga":
                # !! TODO FIXME !! Allow individual jig object, not just jig type ? (for loading)
                jig, i_beluga, i_loading = params[0], params[1], params[2]
                fl = None
                #for fl_ in flights:
                #    if fl_.name == beluga:
                #        fl = fl_
                #        assert i_loading not in fl.outgoing
                #        fl.outgoing[i_loading] = jig
                #        break
                #if fl is None:
                #    fl = Flight(name=beluga, incoming=dict(), outgoing={i_loading: jig})
                #    flights.append(fl)
                #flights = sorted(flights, key=lambda f: f.name) # Ensure flights / belugas are ordered by name (beluga1, beluga2...)
                for (ii, fl_) in _flights:
                    if ii == i_beluga:
                        fl = fl_
                        assert i_loading not in fl.outgoing
                        fl.outgoing[i_loading] = jig
                        break
                if fl is None:
                    fl = Flight(name=beluga_name(i_beluga), incoming=dict(), outgoing={i_loading: jig})
                    _flights.append((i_beluga, fl))
                _flights = sorted(_flights, key=lambda e: e[0])
                flights = [fl for (_, fl) in _flights]

            elif name == "deliver_to_production_line":
                jig, pl_name, i = params[0], params[1], params[2]
                pl = None
                for pl_ in production_lines:
                    if pl_.name in pl_name:
                        pl = pl_
                        pl.schedule[i] = jig
                        break
                if pl is None:
                    pl = ProductionLine(name=pl_name, schedule={i: jig})
                    production_lines.append(pl)

            elif name == "rack_always_empty":
                rack_name = params[0]
                rack_always_empty.append(rack_name)

            elif name == "at_least_one_rack_always_empty":
                use_at_least_one_rack_always_empty = True

            elif name == "jig_always_placed_on_rack_size_leq":
                jig_name, num = params[0], params[1]
                jig_always_placed_on_rack_size_leq.append((jig_name, num))

            elif name == "num_swaps_used_leq":
                num_swaps_used_leq = params[0]

            else:
                print("unsupported spec {} (for now?)".format(name))

    return BelugaProblemDef(
        trailers_beluga=trailers_beluga,
        trailers_factory=trailers_factory,
        hangars=hangars,
        jig_types=jig_types,
        racks=racks,
        jigs=jigs,
        production_lines=production_lines,
        flights=flights,
        rack_always_empty=rack_always_empty,
        use_at_least_one_rack_always_empty=use_at_least_one_rack_always_empty,
        jig_always_placed_on_rack_size_leq=jig_always_placed_on_rack_size_leq,
        val_num_swaps_used_leq=num_swaps_used_leq,
    )