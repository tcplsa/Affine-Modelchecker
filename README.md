# modelchecker
A bit-level parallel model checking solver supporting up to 16 threads, compatible with both BMC and PDR.

## Usage

### **Building Modelchecker**
Run the following commands in the project directory:
```sh
./rebuild.sh
make clean
make -j
```


### **Running Modelchecker**
```sh
./modelchecker [OPTIONS] <AIGER_file>
```


#### **Options:**
- `-findbug [nframes]`  — Run single-threaded BMC for each property up to `nframes` steps. Ignores all other parameters. Default: INT_MAX.
- `-bmc <bmc_thread>`  — Set the number of BMC threads (0-12). Default: 0  
- `-pdr <pdr_thread>`  — Set the number of PDR threads (0-4). Default: 0  
- `-pindex <property_index>`  — Specify the property index for verification. Default: 0  
- `-engine <mode>` — Select single-PDR `forward` or `reverse` mode. Default: `forward`.
- `--forward-aig <count>` — Number of forward AIG PDR lanes.
- `--forward-xag <count>` — Number of forward XAG PDR lanes.
- `--reverse-aig <count>` — Number of reverse AIG PDR lanes.
- `--reverse-xag <count>` — Number of reverse XAG PDR lanes.
- `-witness`  — Output witness if a bug is found. Default: off  
- `-certificate`  — Output certificate if the circuit is safe. Default: off  
- `-uc`  — Enable CPO-Driven UNSAT Core Generation (only for single-threaded PDR)  
- `-pr`  — Enable CPO-Driven Proof Obligation Propagation (only for single-threaded PDR)  
- `-h`  — Show help message and exit  


### **Example Usage**
```sh
./modelchecker -bmc 4 -pdr 2 -pindex 3 -witness example.aig
```
This runs Modelchecker with 4 BMC threads, 2 PDR threads, and checks property index 3 while enabling witness output.

### Directional PDR

```sh
./modelchecker -aig -engine forward example.aig
./modelchecker -aig -engine reverse example.aig
./modelchecker --forward-aig 1 --forward-xag 1 \
  --reverse-aig 1 --reverse-xag 1 example.aig
```

- `forward` is the original IC3/PDR search from `Init` toward `Bad`.
- `reverse` runs IC3/PDR from `Bad` toward `Init` over the transposed transition relation.
- Explicit lane options run the requested forward/reverse AIG/XAG PDR workers
  concurrently and check candidate edges between their over-approximate frames.
  Lanes in the same direction exchange permanent inductive lemmas through an
  explicit latch-variable mapping by default; set `MC_PDR_SHARE=0` to disable
  it. Frame-local lemmas are never exchanged. Missing or all-zero lane options fall back to one
  forward PDR.
  A candidate is reported as a bug only when both directional blocking attempts
  reach their respective source sets. When either engine finishes independently,
  the other engine's active CaDiCaL query is cancelled.

It is a cooperative bidirectional symbolic search, not an exact BDD-style BFS.
See [BIDIRECTIONAL_PDR.md](BIDIRECTIONAL_PDR.md) for the formulas, witness
orientation, controls, and current limitations.


## **Output Explanation**
- **For unsafe circuits**, Modelchecker prints `result: unsafe` along with runtime information. If `-witness` is enabled, it also outputs a witness.  
- **For safe circuits**, Modelchecker prints `result: safe` along with runtime details.  
  - If `-certificate` is enabled, the circuit's proof certificate will be generated in both AIG and AAG formats as `certificate.aig` and `certificate.aag` in the working directory.
