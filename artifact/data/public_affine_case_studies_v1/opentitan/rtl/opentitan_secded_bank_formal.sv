// Formal wrapper for the unmodified OpenTitan 72/64 Hamming SECDED codec.
// BANKS=8 models a 512-bit cache line; BANKS=32 models a 2048-bit row.
module opentitan_secded_bank_formal #(
  parameter integer BANKS = 8
) (
  input  wire                       clk,
  input  wire [BANKS*64-1:0]        data_i,
  input  wire [BANKS*7-1:0]         error_pos_i,
  output wire                       bad
);
  wire [BANKS-1:0] bank_bad;

  generate
    for (genvar bank = 0; bank < BANKS; bank++) begin : gen_bank
      wire [63:0] fresh_data = data_i[bank*64 +: 64];
      wire [6:0] error_pos = error_pos_i[bank*7 +: 7];
      wire [71:0] fresh_code;
      reg  [63:0] data_q = 64'b0;
      reg  [71:0] code_q = 72'b0;
      wire [71:0] error_mask = 72'b1 << error_pos;
      wire [71:0] damaged_code = code_q ^ error_mask;
      wire [63:0] corrected_data;
      wire [7:0] syndrome;
      wire [1:0] error_kind;

      prim_secded_hamming_72_64_enc i_encoder (
        .data_i (fresh_data),
        .data_o (fresh_code)
      );

      prim_secded_hamming_72_64_dec i_decoder (
        .data_i     (damaged_code),
        .data_o     (corrected_data),
        .syndrome_o (syndrome),
        .err_o      (error_kind)
      );

      always @(posedge clk) begin
        data_q <= fresh_data;
        code_q <= fresh_code;
      end

      // Positions 72..127 produce a zero mask and therefore model no error.
      assign bank_bad[bank] = corrected_data != data_q;
    end
  endgenerate

  assign bad = |bank_bad;
endmodule
