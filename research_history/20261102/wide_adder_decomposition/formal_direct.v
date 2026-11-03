module formal_direct(
    input  wire        clk,
    input  wire        in_valid,
    input  wire [63:0] a,
    input  wire [63:0] b,
    output wire        bad
);
    wire out_valid;
    wire [63:0] sum;
    wire overflow;
    reg [64:0] expected = 65'd0;

    wide_adder64 dut(clk, in_valid, a, b, out_valid, sum, overflow);

    always @(posedge clk) begin
        if (in_valid)
            expected <= {1'b0, a} + {1'b0, b};
    end

    assign bad = out_valid && ({overflow, sum} != expected);
endmodule

