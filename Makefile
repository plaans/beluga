compile_all: compile_docker compile_apptainer

compile_docker:
	docker build -t aries-beluga-docker .

# NOTE: The "latest" tag above is required !!
compile_apptainer:
	apptainer build aries-beluga-apptainer.sif docker-daemon://aries-beluga-docker:latest

MAXSWAPS = ""
PBBASE = ""
PBPROPS = ""

# NOTE: Usage: make run_solve MAXSWAPS=5 PBBASE="example_problems/test01a_base.json" PBPROPS="example_problems/test01a_props.json"
run_solve:
	apptainer exec aries-beluga-apptainer.sif /usr/src/beluga/beluga.py solve $(MAXSWAPS) $(PBBASE) $(PBPROPS)

PROPSHARD = "[]" # Should be a list "[propid1, ..., propid2]" of property ids to consider as hard / mandatory

# NOTE: Usage: make run_explain MAXSWAPS=2 PBBASE="example_problems/test02_base.json" PBPROPS="example_problems/test02_props.json"
run_explain:
	apptainer exec aries-beluga-apptainer.sif /usr/src/beluga/beluga.py explain $(MAXSWAPS) $(PBBASE) $(PBPROPS) $(PROPSHARD)
