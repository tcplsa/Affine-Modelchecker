all: modelchecker

CMSAT_ROOT ?= $(if $(wildcard ../PIC3withXors/cryptominisat),../PIC3withXors,../../blif)
CMSAT_DIR ?= $(CMSAT_ROOT)/cryptominisat
CMSAT_LIB ?= $(CMSAT_DIR)/build/lib
CMSAT_WRAPPER_SRC ?= third_party/cmsat_wrapper.cpp
CMSAT_WRAPPER_LIB ?= libcmsat_wrapper.so
LDFLAGS ?= -no-pie

$(CMSAT_WRAPPER_LIB): $(CMSAT_WRAPPER_SRC) $(CMSAT_LIB)/libcryptominisat5.so
	g++ -std=c++17 -O3 -shared -fPIC -o $@ $< \
		-I$(CMSAT_DIR)/build/include/cryptominisat5 \
		-L$(CMSAT_LIB) -lcryptominisat5 \
		-Wl,-rpath,'$$ORIGIN/$(CMSAT_LIB)'

modelchecker: BMC.cpp BMC.hpp PDR.cpp PDR.hpp aig.cpp aig.hpp main.cpp basic.hpp sat_solver.hpp ipasir.h aig2xag.hpp aig2xag.cpp pdr_perturb.hpp pdr_perturb.cpp lemma_exchange.hpp lemma_exchange.cpp libcadical.a minisat/build/dynamic/lib/libminisat.so $(CMSAT_LIB)/libcryptominisat5.so $(CMSAT_WRAPPER_LIB)
	g++ -std=c++0x -O3 -o modelchecker.tmp BMC.cpp PDR.cpp aig.cpp main.cpp aig2xag.cpp pdr_perturb.cpp lemma_exchange.cpp -g \
		$(LDFLAGS) \
		-L. -lcadical -lcmsat_wrapper -L$(CMSAT_LIB) -lcryptominisat5 -Wl,-rpath,'$$ORIGIN' -Wl,-rpath,'$$ORIGIN/$(CMSAT_LIB)' \
		-Iminisat -Iminisat/minisat/simp -Iminisat/minisat/core -Iminisat/minisat/mtl \
		minisat/build/release/lib/libminisat.a \
		-lpthread
	mv modelchecker.tmp modelchecker

clean:
	rm -f modelchecker modelchecker.tmp $(CMSAT_WRAPPER_LIB)
