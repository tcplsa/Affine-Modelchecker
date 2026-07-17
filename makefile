all: modelchecker

modelchecker: BMC.cpp BMC.hpp PDR.cpp PDR.hpp aig.cpp aig.hpp main.cpp basic.hpp sat_solver.hpp ipasir.h aig2xag.hpp aig2xag.cpp pdr_perturb.hpp pdr_perturb.cpp lemma_exchange.hpp lemma_exchange.cpp libcadical.a minisat/build/dynamic/lib/libminisat.so
	g++ -std=c++0x -O3 -o modelchecker.tmp BMC.cpp PDR.cpp aig.cpp main.cpp aig2xag.cpp pdr_perturb.cpp lemma_exchange.cpp -g \
		-L. -lcadical \
		-Iminisat -Iminisat/minisat/simp -Iminisat/minisat/core -Iminisat/minisat/mtl \
		minisat/build/release/lib/libminisat.a \
		-lpthread
	mv modelchecker.tmp modelchecker

clean:
	rm -f modelchecker 
