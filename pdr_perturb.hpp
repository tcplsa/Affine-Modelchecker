#pragma once

#include <string>

class Aiger;

void apply_pdr_perturbations(Aiger *aiger, const std::string &modes = "", unsigned seed = 0);
