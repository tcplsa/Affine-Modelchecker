// Formal wrapper for the unmodified OpenTitan prim_lfsr RTL.
// Parameters are fixed by the build script for each generated AIGER model.
module opentitan_lfsr_transition_formal #(
    parameter integer WIDTH = 8,
    parameter integer ENTROPY_WIDTH = 4,
    parameter [WIDTH-1:0] DEFAULT_SEED = {{(WIDTH-1){1'b0}}, 1'b1},
    parameter [WIDTH-1:0] COEFFS = {WIDTH{1'b0}}
) (
    input wire clk,
    input wire rst_n,
    input wire seed_en,
    input wire enable,
    input wire [WIDTH-1:0] seed,
    input wire [ENTROPY_WIDTH-1:0] entropy,
    output wire bad
);
    wire [WIDTH-1:0] state;

    prim_lfsr #(
        .LfsrType("GAL_XOR"),
        .LfsrDw(WIDTH),
        .EntropyDw(ENTROPY_WIDTH),
        .StateOutDw(WIDTH),
        .DefaultSeed(DEFAULT_SEED),
        .CustomCoeffs(COEFFS),
        .StatePermEn(1'b0),
        .MaxLenSVA(1'b0),
        .LockupSVA(1'b0),
        .ExtSeedSVA(1'b0),
        .NonLinearOut(1'b0)
    ) dut (
        .clk_i(clk),
        .rst_ni(rst_n),
        .seed_en_i(seed_en),
        .seed_i(seed),
        .lfsr_en_i(enable),
        .entropy_i(entropy),
        .state_o(state)
    );

    reg past_valid;
    reg [WIDTH-1:0] past_state;
    reg [WIDTH-1:0] past_seed;
    reg [ENTROPY_WIDTH-1:0] past_entropy;
    reg past_seed_en;
    reg past_enable;

    initial begin
        past_valid = 1'b0;
        past_state = DEFAULT_SEED;
        past_seed = {WIDTH{1'b0}};
        past_entropy = {ENTROPY_WIDTH{1'b0}};
        past_seed_en = 1'b0;
        past_enable = 1'b0;
    end

    wire past_lockup = ~(|past_state);
    wire [WIDTH-1:0] widened_entropy = {{(WIDTH-ENTROPY_WIDTH){1'b0}}, past_entropy};
    wire [WIDTH-1:0] affine_next = widened_entropy
        ^ ({WIDTH{past_state[0]}} & COEFFS)
        ^ (past_state >> 1);
    wire [WIDTH-1:0] expected_state = past_seed_en ? past_seed
        : (past_enable && past_lockup) ? DEFAULT_SEED
        : past_enable ? affine_next
        : past_state;

    assign bad = rst_n && past_valid && (state != expected_state);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            past_valid <= 1'b0;
            past_state <= DEFAULT_SEED;
            past_seed <= {WIDTH{1'b0}};
            past_entropy <= {ENTROPY_WIDTH{1'b0}};
            past_seed_en <= 1'b0;
            past_enable <= 1'b0;
        end else begin
            past_valid <= 1'b1;
            past_state <= state;
            past_seed <= seed;
            past_entropy <= entropy;
            past_seed_en <= seed_en;
            past_enable <= enable;
        end
    end
endmodule
