all: modelchecker

modelchecker: BMC.hpp PDR.hpp aig.hpp basic.hpp sat_solver.hpp ipasir.h aig2xag.hpp aig2xag.cpp pdr_perturb.hpp pdr_perturb.cpp libcadical.a minisat/build/dynamic/lib/libminisat.so
	g++ -std=c++0x -O3 -o modelchecker BMC.cpp PDR.cpp aig.cpp main.cpp aig2xag.cpp pdr_perturb.cpp -g \
		-L. -lcadical \
		-Iminisat -Iminisat/minisat/simp -Iminisat/minisat/core -Iminisat/minisat/mtl \
		minisat/build/release/lib/libminisat.a \
		-lpthread

clean:
	rm -f modelchecker 
