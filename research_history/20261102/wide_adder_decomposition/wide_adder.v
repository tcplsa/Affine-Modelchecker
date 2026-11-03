module add16(
    input  wire [15:0] a,
    input  wire [15:0] b,
    input  wire        cin,
    output wire [15:0] sum,
    output wire        cout
);
    wire [16:0] full;
    assign full = {1'b0, a} + {1'b0, b} + cin;
    assign sum = full[15:0];
    assign cout = full[16];
endmodule

module wide_adder64(
    input  wire        clk,
    input  wire        in_valid,
    input  wire [63:0] a,
    input  wire [63:0] b,
    output reg         out_valid = 1'b0,
    output reg  [63:0] sum = 64'd0,
    output reg         overflow = 1'b0
);
    wire [15:0] s0, s1, s2, s3;
    wire c1, c2, c3, c4;

    add16 u0(a[15:0],  b[15:0],  1'b0, s0, c1);
    add16 u1(a[31:16], b[31:16], c1,   s1, c2);
    add16 u2(a[47:32], b[47:32], c2,   s2, c3);
    add16 u3(a[63:48], b[63:48], c3,   s3, c4);

    always @(posedge clk) begin
        out_valid <= in_valid;
        if (in_valid) begin
            sum <= {s3, s2, s1, s0};
            overflow <= c4;
        end
    end
endmodule

