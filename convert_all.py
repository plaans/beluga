from up import *
import glob
import os
from pathlib import Path

dir = "/home/abitmonnot/tmp/beluga-challenge/scalability/deterministic/sample_instances/json"

files = glob.glob(f"{dir}/*.json")

print(files)

for file in files:
    name = Path(file).stem
    print(name)
    pb = parse_file(file)
    up = convert(pb, name)
    print(up)
    serialize(up, f"upp/{name}.upp")