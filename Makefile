# NOTE: The environment variable MAX_NUM_AVAILABLE_SWAPS in the Dockerfile controls the max number of swaps available.
#       Default: 1

compile_all: compile_docker compile_apptainer

compile_docker:
	docker build -t aries-beluga-docker .

# NOTE: The "latest" tag above is required !!
compile_apptainer:
	apptainer build aries-beluga-apptainer.sif docker-daemon://aries-beluga-docker:latest

PBBASE = ""
PBPROPS = ""

# NOTE: Usage: make run_solve PBBASE="example_problems/test01a_base.json" PBPROPS="example_problems/test01a_props.json"
run_solve:
	apptainer exec aries-beluga-apptainer.sif /usr/src/beluga/beluga.py solve $(PBBASE) $(PBPROPS)

PROPSHARD = "[]" # Should be a list "[propid1, ..., propid2]" of property ids to consider as hard / mandatory

# NOTE: Usage: make run_explain PBBASE="example_problems/test02_base.json" PBPROPS="example_problems/test02_props.json"
run_explain:
	apptainer exec aries-beluga-apptainer.sif /usr/src/beluga/beluga.py explain $(PBBASE) $(PBPROPS) $(PROPSHARD)

