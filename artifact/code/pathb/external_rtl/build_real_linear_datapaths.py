#!/usr/bin/env python3
"""Build formal AIGER instances from externally maintained linear datapath RTL.

The first family checks a parallel CRC-32 core against a bit-serial golden
reference.  The DUT consumes a complete word on ``start`` while the reference
consumes the captured word one bit per cycle.  This is the common refinement
check used when a serial reference is retained alongside a wide datapath.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
EXTERNAL = ROOT / "test_tools" / "compare" / "external_linear_rtl"
YOSYS = ROOT / "tools" / "yosys-0.40" / "yosys"
OUT = ROOT / "test_tools" / "compare" / "results" / "pathb_real_linear_rtl_v1"


def crc32_step(state: int, bit: int) -> int:
    feedback = ((state >> 31) & 1) ^ bit
    state = ((state << 1) & 0xFFFFFFFF) | feedback
    if feedback:
        state ^= 0x04C11DB6
    return state


def crc32_word(state: int, data: int, width: int) -> int:
    for bit_index in range(width - 1, -1, -1):
        state = crc32_step(state, (data >> bit_index) & 1)
    return state


def crc32_matrix_rows(width: int, output: str, state: str, data: str) -> str:
    """Emit the fixed GF(2) matrix for one CRC-32 word update."""
    masks: list[list[int]] = [[] for _ in range(32)]
    for source_bit in range(32 + width):
        source_state = 1 << source_bit if source_bit < 32 else 0
        source_data = 1 << (source_bit - 32) if source_bit >= 32 else 0
        result = crc32_word(source_state, source_data, width)
        for output_bit in range(32):
            if (result >> output_bit) & 1:
                masks[output_bit].append(source_bit)

    rows = []
    for output_bit, bits in enumerate(masks):
        terms = [
            f"{state}[{source_bit}]" if source_bit < 32
            else f"{data}[{source_bit - 32}]"
            for source_bit in bits
        ]
        rows.append(f"assign {output}[{output_bit}] = " + " ^ ".join(terms) + ";")
    return "\n".join(rows)


def reverse_bits(value: int, width: int) -> int:
    result = 0
    for index in range(width):
        result |= ((value >> index) & 1) << (width - index - 1)
    return result


def lfsr_step(state: int, bit: int, width: int, polynomial: int, config: str) -> tuple[int, int]:
    feedback = ((state >> (width - 1)) & 1) ^ bit
    shifted = ((state << 1) & ((1 << width) - 1)) | feedback
    if config == "FIBONACCI":
        for index in range(1, width):
            if (polynomial >> index) & 1:
                feedback ^= (state >> (index - 1)) & 1
        shifted = ((state << 1) & ((1 << width) - 1)) | feedback
    elif config == "GALOIS":
        for index in range(1, width):
            if (polynomial >> index) & 1:
                shifted ^= feedback << index
    else:
        raise ValueError(config)
    return shifted, feedback


def lfsr_word(
    state: int,
    data: int,
    data_width: int,
    lfsr_width: int,
    polynomial: int,
    config: str,
    reverse: bool,
) -> tuple[int, int]:
    if reverse:
        state = reverse_bits(state, lfsr_width)
        data = reverse_bits(data, data_width)
    output = 0
    for index in range(data_width - 1, -1, -1):
        state, out_bit = lfsr_step(state, (data >> index) & 1, lfsr_width, polynomial, config)
        output |= out_bit << index
    if reverse:
        state = reverse_bits(state, lfsr_width)
        output = reverse_bits(output, data_width)
    return state, output


def parallel_crc32_dut_verilog(width: int) -> str:
    """Emit the fixed-parameter XOR matrix used by the public LFSR core.

    The upstream generic module computes the same matrix using a large
    elaboration-time mask function.  Yosys 0.40 expands all generic branches
    before parameter reduction, so we freeze the configured matrix here.
    """
    return f"""// Fixed configuration of alexforencich/verilog-lfsr lfsr_crc.
// CRC-32, Galois, MSB-first, DATA_WIDTH={width}, LOOP-style XOR matrix.
module external_lfsr_crc32_parallel_fixed(
    input wire clk,
    input wire rst,
    input wire [{width - 1}:0] data_in,
    input wire data_in_valid,
    output wire [31:0] crc_out
);
reg [31:0] state_reg = 32'hffffffff;
reg [31:0] output_reg = 0;
wire [31:0] next_state;
{crc32_matrix_rows(width, 'next_state', 'state_reg', 'data_in')}
assign crc_out = output_reg;
always @(posedge clk) begin
    if (rst) begin
        state_reg <= 32'hffffffff;
        output_reg <= 0;
    end else if (data_in_valid) begin
        state_reg <= next_state;
        output_reg <= ~next_state;
    end
end
endmodule
"""


def crc32_staged_pipeline_verilog(word_width: int, stage_width: int) -> str:
    """Build an independent wide-stage CRC implementation against a word matrix.

    This is a fixed-latency transaction pipeline: the staged implementation
    advances one wide CRC segment per clock, while the reference computes the
    same transaction with a single whole-word XOR matrix and delays comparison
    until the staged result is available.  The state persists across accepted
    transactions, as in a streaming CRC datapath.
    """
    if word_width % stage_width:
        raise ValueError("word width must be a multiple of stage width")
    stages = word_width // stage_width
    count_width = max(1, (stages + 1).bit_length())
    chunk_cases = []
    for remaining in range(stages, 0, -1):
        stage_index = stages - remaining
        high = word_width - stage_index * stage_width - 1
        low = high - stage_width + 1
        chunk_cases.append(f"            {remaining}: selected_chunk = saved_data[{high}:{low}];")
    return f"""// Fixed CRC-32 staged datapath derived from alexforencich/verilog-lfsr.
// One side uses a whole-word matrix; the other uses {stages} x {stage_width}-bit stages.
module crc32_staged_pipeline_equivalence_w{word_width}_s{stage_width}(
    input wire clk, input wire rst, input wire start,
    input wire [{word_width - 1}:0] data, output wire bad
);
localparam integer WORD_WIDTH = {word_width};
localparam integer STAGE_WIDTH = {stage_width};
localparam integer STAGES = {stages};
localparam integer COUNT_WIDTH = {count_width};

reg busy = 0;
reg [COUNT_WIDTH-1:0] remaining = 0;
reg [WORD_WIDTH-1:0] saved_data = 0;
reg [31:0] reference_state = 32'hffffffff;
reg [31:0] staged_state = 32'hffffffff;
reg [31:0] expected_crc = 0;
reg [31:0] actual_crc = 0;
reg check_pending = 0;

wire [31:0] whole_next;
wire [STAGE_WIDTH-1:0] current_chunk;
wire [31:0] stage_next;
assign bad = check_pending && (actual_crc != expected_crc);

{crc32_matrix_rows(word_width, 'whole_next', 'reference_state', 'data')}
{crc32_matrix_rows(stage_width, 'stage_next', 'staged_state', 'current_chunk')}

// Kept as an explicit case rather than an indexed part-select so the AIG
// preserves the stage topology rather than introducing a decoder mux.
reg [STAGE_WIDTH-1:0] selected_chunk;
always @* begin
    selected_chunk = {{STAGE_WIDTH{{1'b0}}}};
    case (remaining)
{chr(10).join(chunk_cases)}
        default: selected_chunk = {{STAGE_WIDTH{{1'b0}}}};
    endcase
end
assign current_chunk = selected_chunk;

always @(posedge clk) begin
    if (rst) begin
        busy <= 0;
        remaining <= 0;
        saved_data <= 0;
        reference_state <= 32'hffffffff;
        staged_state <= 32'hffffffff;
        expected_crc <= 0;
        actual_crc <= 0;
        check_pending <= 0;
    end else begin
        if (check_pending) check_pending <= 0;
        if (!busy) begin
            if (start) begin
                busy <= 1;
                remaining <= STAGES;
                saved_data <= data;
                expected_crc <= whole_next;
            end
        end else begin
            staged_state <= stage_next;
            remaining <= remaining - 1'b1;
            if (remaining == 1) begin
                reference_state <= expected_crc;
                actual_crc <= stage_next;
                busy <= 0;
                check_pending <= 1;
            end
        end
    end
end
endmodule
"""


def crc32_refinement_verilog(width: int) -> str:
    count_width = max(1, (width + 1).bit_length())
    select_cases = "\n".join(
        f"            {index + 1}: selected_bit = value[{index}];"
        for index in range(width)
    )
    return f"""// Generated formal refinement wrapper.  Source DUT: alexforencich/verilog-lfsr.
module crc32_parallel_serial_refinement(
    input wire clk,
    input wire rst,
    input wire start,
    input wire [{width - 1}:0] data,
    output wire bad
);
localparam integer DATA_WIDTH = {width};
localparam integer COUNT_WIDTH = {count_width};
localparam [31:0] CRC_POLY = 32'h04c11db7;

wire accept = start && !busy;
wire [31:0] dut_crc;
reg busy = 1'b0;
reg [COUNT_WIDTH-1:0] remaining = 0;
reg [{width - 1}:0] saved_data = 0;
reg [31:0] serial_state = 32'hffffffff;
reg [31:0] serial_work = 32'hffffffff;
reg [31:0] expected_crc = 0;
reg check_pending = 1'b0;
assign bad = check_pending && (dut_crc != expected_crc);

// The fixed DUT is a parameter-specialized form of the public implementation.
external_lfsr_crc32_parallel_fixed dut (
    .clk(clk),
    .rst(rst),
    .data_in(data),
    .data_in_valid(accept),
    .crc_out(dut_crc)
);

function [31:0] serial_step;
    input [31:0] state;
    input bit_in;
    reg feedback;
    reg [31:0] next_state;
    begin
        feedback = state[31] ^ bit_in;
        next_state = {{state[30:0], feedback}};
        if (feedback)
            // Bit zero already contains the feedback bit after the shift.
            next_state = next_state ^ 32'h04c11db6;
        serial_step = next_state;
    end
endfunction

function selected_bit;
    input [DATA_WIDTH-1:0] value;
    input [COUNT_WIDTH-1:0] index;
    begin
        selected_bit = 1'b0;
        case (index)
{select_cases}
            default: selected_bit = 1'b0;
        endcase
    end
endfunction

always @(posedge clk) begin
    if (rst) begin
        busy <= 1'b0;
        remaining <= 0;
        saved_data <= 0;
        serial_state <= 32'hffffffff;
        serial_work <= 32'hffffffff;
        expected_crc <= 0;
        check_pending <= 1'b0;
    end else begin
        if (check_pending) begin
            check_pending <= 1'b0;
        end

        if (!busy) begin
            if (start) begin
                busy <= 1'b1;
                remaining <= DATA_WIDTH;
                saved_data <= data;
                serial_work <= serial_state;
            end
        end else begin
            serial_work <= serial_step(serial_work, selected_bit(saved_data, remaining));
            remaining <= remaining - 1'b1;
            if (remaining == 1) begin
                serial_state <= serial_step(serial_work, saved_data[0]);
                expected_crc <= ~serial_step(serial_work, saved_data[0]);
                busy <= 1'b0;
                check_pending <= 1'b1;
            end
        end
    end
end
endmodule
"""


def parallel_scrambler_dut_verilog(
    name: str,
    data_width: int,
    lfsr_width: int,
    polynomial: int,
    config: str,
    reverse: bool,
) -> str:
    state_masks: list[list[int]] = [[] for _ in range(lfsr_width)]
    output_masks: list[list[int]] = [[] for _ in range(data_width)]
    for source_bit in range(lfsr_width + data_width):
        state = (1 << source_bit) if source_bit < lfsr_width else 0
        data = (1 << (source_bit - lfsr_width)) if source_bit >= lfsr_width else 0
        next_state, output = lfsr_word(
            state, data, data_width, lfsr_width, polynomial, config, reverse
        )
        for output_bit in range(lfsr_width):
            if (next_state >> output_bit) & 1:
                state_masks[output_bit].append(source_bit)
        for output_bit in range(data_width):
            if (output >> output_bit) & 1:
                output_masks[output_bit].append(source_bit)

    def rows(prefix: str, masks: list[list[int]]) -> str:
        result = []
        for output_bit, bits in enumerate(masks):
            terms = [
                f"state_reg[{source_bit}]" if source_bit < lfsr_width
                else f"data_in[{source_bit - lfsr_width}]"
                for source_bit in bits
            ]
            result.append(f"assign {prefix}[{output_bit}] = " + " ^ ".join(terms) + ";")
        return "\n".join(result)

    return f"""// Fixed configuration of alexforencich/verilog-lfsr lfsr_scramble.
module {name}_dut(
    input wire clk, input wire rst,
    input wire [{data_width - 1}:0] data_in, input wire data_in_valid,
    output wire [{data_width - 1}:0] data_out
);
reg [{lfsr_width - 1}:0] state_reg = {{{lfsr_width}{{1'b1}}}};
reg [{data_width - 1}:0] output_reg = 0;
wire [{lfsr_width - 1}:0] next_state;
wire [{data_width - 1}:0] next_output;
{rows('next_state', state_masks)}
{rows('next_output', output_masks)}
assign data_out = output_reg;
always @(posedge clk) begin
    if (rst) begin
        state_reg <= {{{lfsr_width}{{1'b1}}}};
        output_reg <= 0;
    end else if (data_in_valid) begin
        state_reg <= next_state;
        output_reg <= next_output;
    end
end
endmodule
"""


def scrambler_refinement_verilog(
    name: str,
    data_width: int,
    lfsr_width: int,
    polynomial: int,
    config: str,
    reverse: bool,
) -> str:
    count_width = max(1, (data_width + 1).bit_length())
    if reverse:
        select_cases = "\n".join(
            f"            {data_width - index}: selected_bit = value[{index}];"
            for index in range(data_width)
        )
        output_cases = "\n".join(
            f"                {data_width - index}: serial_output[{index}] <= step_out;"
            for index in range(data_width)
        )
        final_output = "{step_out, serial_output[DATA_WIDTH-2:0]}"
    else:
        select_cases = "\n".join(
            f"            {index + 1}: selected_bit = value[{index}];"
            for index in range(data_width)
        )
        output_cases = "\n".join(
            f"                {index + 1}: serial_output[{index}] <= step_out;"
            for index in range(data_width)
        )
        final_output = "{serial_output[DATA_WIDTH-1:1], step_out}"
    config_code = "1'b1" if config == "FIBONACCI" else "1'b0"
    return f"""module {name}_refinement(
    input wire clk, input wire rst, input wire start,
    input wire [{data_width - 1}:0] data, output wire bad
);
localparam integer DATA_WIDTH = {data_width};
localparam integer LFSR_WIDTH = {lfsr_width};
localparam integer COUNT_WIDTH = {count_width};
localparam [LFSR_WIDTH-1:0] LFSR_POLY = {lfsr_width}'h{polynomial:x};
localparam FIBONACCI = {config_code};
localparam REVERSE = {int(reverse)};
reg busy = 0;
reg [COUNT_WIDTH-1:0] remaining = 0;
reg [DATA_WIDTH-1:0] saved_data = 0;
reg [LFSR_WIDTH-1:0] serial_state = {{LFSR_WIDTH{{1'b1}}}};
reg [DATA_WIDTH-1:0] serial_output = 0;
reg [DATA_WIDTH-1:0] expected_output = 0;
reg check_pending = 0;
wire [{data_width - 1}:0] dut_output;
assign bad = check_pending && (dut_output != expected_output);

{name}_dut dut (.clk(clk), .rst(rst), .data_in(data),
    .data_in_valid(start && !busy), .data_out(dut_output));

function selected_bit;
    input [DATA_WIDTH-1:0] value;
    input [COUNT_WIDTH-1:0] index;
    begin
        selected_bit = 1'b0;
        case (index)
{select_cases}
            default: selected_bit = 1'b0;
        endcase
    end
endfunction

function [LFSR_WIDTH:0] serial_step;
    input [LFSR_WIDTH-1:0] state;
    input bit_in;
    reg [LFSR_WIDTH-1:0] work;
    reg [LFSR_WIDTH-1:0] next_work;
    reg feedback;
    integer i;
    begin
        if (REVERSE) begin
            for (i = 0; i < LFSR_WIDTH; i = i + 1)
                work[i] = state[LFSR_WIDTH-i-1];
        end else begin
            work = state;
        end
        feedback = work[LFSR_WIDTH-1] ^ bit_in;
        next_work = {{work[LFSR_WIDTH-2:0], feedback}};
        if (FIBONACCI) begin
            for (i = 1; i < LFSR_WIDTH; i = i + 1)
                if (LFSR_POLY[i]) feedback = feedback ^ work[i-1];
            next_work = {{work[LFSR_WIDTH-2:0], feedback}};
        end else begin
            for (i = 1; i < LFSR_WIDTH; i = i + 1)
                if (LFSR_POLY[i]) next_work[i] = next_work[i] ^ feedback;
        end
        if (REVERSE) begin
            for (i = 0; i < LFSR_WIDTH; i = i + 1)
                work[i] = next_work[LFSR_WIDTH-i-1];
            serial_step = {{feedback, work}};
        end else begin
            serial_step = {{feedback, next_work}};
        end
    end
endfunction

wire [LFSR_WIDTH:0] serial_step_value = serial_step(serial_state, selected_bit(saved_data, remaining));
wire step_out = serial_step_value[LFSR_WIDTH];
wire [LFSR_WIDTH-1:0] step_state = serial_step_value[LFSR_WIDTH-1:0];
always @(posedge clk) begin
    if (rst) begin
        busy <= 0;
        remaining <= 0;
        saved_data <= 0;
        serial_state <= {{LFSR_WIDTH{{1'b1}}}};
        serial_output <= 0;
        expected_output <= 0;
        check_pending <= 0;
    end else begin
        if (check_pending) check_pending <= 0;
        if (!busy) begin
            if (start) begin
                busy <= 1;
                remaining <= DATA_WIDTH;
                saved_data <= data;
                serial_output <= 0;
            end
        end else begin
            serial_state <= step_state;
            case (remaining)
{output_cases}
                default: serial_output <= serial_output;
            endcase
            remaining <= remaining - 1'b1;
            if (remaining == 1) begin
                expected_output <= {final_output};
                busy <= 0;
                check_pending <= 1;
            end
        end
    end
end
endmodule
"""


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(str(item) for item in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def build_crc(width: int, output: Path) -> None:
    source = output.with_suffix(".v")
    source.write_text(
        parallel_crc32_dut_verilog(width) + "\n" + crc32_refinement_verilog(width),
        encoding="ascii",
    )
    script = "; ".join([
        f"read_verilog -formal {source}",
        "prep -top crc32_parallel_serial_refinement",
        "dffunmap",
        "flatten",
        "opt -noff",
        "techmap -map +/dff2ff.v",
        "simplemap",
        "opt -noff",
        "pmuxtree",
        "aigmap",
        "opt_clean",
        "setundef -zero",
        f"write_aiger -ascii -miter -symbols {output}",
    ])
    run([str(YOSYS), "-Q", "-p", script], ROOT)


def build_crc_staged_pipeline(word_width: int, stage_width: int) -> None:
    name = f"crc32_staged_pipeline_equivalence_w{word_width}_s{stage_width}"
    output = OUT / f"{name}.aag"
    source = output.with_suffix(".v")
    source.write_text(
        crc32_staged_pipeline_verilog(word_width, stage_width), encoding="ascii"
    )
    script = "; ".join([
        f"read_verilog -formal {source}",
        f"prep -top {name}",
        "dffunmap",
        "flatten",
        "opt -noff",
        "techmap -map +/dff2ff.v",
        "simplemap",
        "opt -noff",
        "pmuxtree",
        "aigmap",
        "opt_clean",
        "setundef -zero",
        f"write_aiger -ascii -miter -symbols {output}",
    ])
    run([str(YOSYS), "-Q", "-p", script], ROOT)


def build_scrambler(
    name: str,
    data_width: int,
    lfsr_width: int,
    polynomial: int,
    config: str,
    reverse: bool,
) -> None:
    output = OUT / f"{name}_parallel_serial_refinement_w{data_width}.aag"
    source = output.with_suffix(".v")
    source.write_text(
        parallel_scrambler_dut_verilog(
            name, data_width, lfsr_width, polynomial, config, reverse
        )
        + "\n"
        + scrambler_refinement_verilog(
            name, data_width, lfsr_width, polynomial, config, reverse
        ),
        encoding="ascii",
    )
    script = "; ".join([
        f"read_verilog -formal {source}",
        f"prep -top {name}_refinement",
        "dffunmap",
        "flatten",
        "opt -noff",
        "techmap -map +/dff2ff.v",
        "simplemap",
        "opt -noff",
        "pmuxtree",
        "aigmap",
        "opt_clean",
        "setundef -zero",
        f"write_aiger -ascii -miter -symbols {output}",
    ])
    run([str(YOSYS), "-Q", "-p", script], ROOT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--widths", default="32,64,128,256")
    parser.add_argument("--families", default="crc,64b66b,pcie")
    parser.add_argument("--pipeline-configs", default="256:32,512:64")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if not YOSYS.is_file():
        raise SystemExit(f"Yosys is missing: {YOSYS}")
    if args.clean and OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    families = {item.strip() for item in args.families.split(",")}
    if "crc" in families:
        for raw_width in args.widths.split(","):
            width = int(raw_width)
            build_crc(width, OUT / f"crc32_parallel_serial_refinement_w{width}.aag")
    if "pipe" in families:
        for raw_config in args.pipeline_configs.split(","):
            word_width, stage_width = (int(item) for item in raw_config.split(":"))
            build_crc_staged_pipeline(word_width, stage_width)
    if "64b66b" in families:
        build_scrambler("scrambler_64b66b", 64, 58, 0x8000000001, "FIBONACCI", True)
    if "pcie" in families:
        build_scrambler("scrambler_pcie_gen3", 32, 23, 0x210125, "GALOIS", True)


if __name__ == "__main__":
    main()
