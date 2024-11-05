

from dataclasses import dataclass
import json
from types import SimpleNamespace
from types import *



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
    schedule: list[str]

@dataclass
class Flight:
    name: str
    incoming: list[str]  # jigs
    outgoing: list[str]  # jig types

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


def parse(d) -> BelugaProblemDef:
    p = BelugaProblemDef(
        trailers_beluga=[t.name for t in d.trailers_beluga],
        trailers_factory=[t.name for t in d.trailers_factory],
        hangars=[h for h in d.hangars],
        jig_types=[JigType(jt.name, jt.size_empty, jt.size_loaded) for jt in vars(d.jig_types).values()],
        racks=[Rack(r.name, r.size, r.jigs) for r in d.racks],
        jigs=[Jig(r.name, r.type, r.empty) for r in vars(d.jigs).values()],
        production_lines=[ProductionLine(r.name, r.schedule) for r in d.production_lines],
        flights=[Flight(r.name, r.incoming, r.outgoing) for r in d.flights],
    )
    return p

def parse_file(filename: str):
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    return parse(d)



if __name__ == "__main__":
    file = 'instances/problem_j4_r3_oc50_f4_s0_3_.json'
    pb = parse_file(file)
    print(pb)



# data = '{"name": "John Smith", "hometown": {"name": "New York", "id": 123}}'

# # Parse JSON into an object with attributes corresponding to dict keys.
# x = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
# print(x.name, x.hometown.name, x.hometown.id)