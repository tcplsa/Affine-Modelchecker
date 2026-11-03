module formal_split(
    input  wire [63:0] a,
    input  wire [63:0] b,
    output wire [3:0]  local_bad
);
    wire [15:0] s0, s1, s2, s3;
    wire c1, c2, c3, c4;
    wire [16:0] ref0, ref1, ref2, ref3;

    add16 u0(a[15:0],  b[15:0],  1'b0, s0, c1);
    add16 u1(a[31:16], b[31:16], c1,   s1, c2);
    add16 u2(a[47:32], b[47:32], c2,   s2, c3);
    add16 u3(a[63:48], b[63:48], c3,   s3, c4);

    assign ref0 = {1'b0, a[15:0]}  + {1'b0, b[15:0]};
    assign ref1 = {1'b0, a[31:16]} + {1'b0, b[31:16]} + c1;
    assign ref2 = {1'b0, a[47:32]} + {1'b0, b[47:32]} + c2;
    assign ref3 = {1'b0, a[63:48]} + {1'b0, b[63:48]} + c3;

    assign local_bad[0] = {c1, s0} != ref0;
    assign local_bad[1] = {c2, s1} != ref1;
    assign local_bad[2] = {c3, s2} != ref2;
    assign local_bad[3] = {c4, s3} != ref3;
endmodule

