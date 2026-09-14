// Parallel CRC miter.  The implementation side is the explicit HAVEN
// CrcNext logic; the specification side is a bit-serial polynomial update.
module haven_eth_crc_parallel_standard_formal #(
  parameter integer SYMBOL_BITS = 32
) (
  input  wire                   clk,
  input  wire [SYMBOL_BITS-1:0] data,
  input  wire                   enable,
  input  wire                   initialize,
  output wire                   bad
);
  reg [31:0] haven_crc_q;
  reg [31:0] spec_crc_q;
  reg [31:0] haven_next;
  reg [31:0] spec_next;
  integer offset;
  integer bit_index;

  // These equations are a direct transcription of the enabled CrcNext logic
  // in HAVEN/OpenCores eth_crc.v.  They are deliberately not generated from
  // the polynomial specification below.
  function [31:0] haven_step4;
    input [31:0] c;
    input [3:0] d;
    input en;
    reg [31:0] n;
    begin
      n[0]  = en & (d[0] ^ c[28]);
      n[1]  = en & (d[1] ^ d[0] ^ c[28] ^ c[29]);
      n[2]  = en & (d[2] ^ d[1] ^ d[0] ^ c[28] ^ c[29] ^ c[30]);
      n[3]  = en & (d[3] ^ d[2] ^ d[1] ^ c[29] ^ c[30] ^ c[31]);
      n[4]  = (en & (d[3] ^ d[2] ^ d[0] ^ c[28] ^ c[30] ^ c[31])) ^ c[0];
      n[5]  = (en & (d[3] ^ d[1] ^ d[0] ^ c[28] ^ c[29] ^ c[31])) ^ c[1];
      n[6]  = (en & (d[2] ^ d[1] ^ c[29] ^ c[30])) ^ c[2];
      n[7]  = (en & (d[3] ^ d[2] ^ d[0] ^ c[28] ^ c[30] ^ c[31])) ^ c[3];
      n[8]  = (en & (d[3] ^ d[1] ^ d[0] ^ c[28] ^ c[29] ^ c[31])) ^ c[4];
      n[9]  = (en & (d[2] ^ d[1] ^ c[29] ^ c[30])) ^ c[5];
      n[10] = (en & (d[3] ^ d[2] ^ d[0] ^ c[28] ^ c[30] ^ c[31])) ^ c[6];
      n[11] = (en & (d[3] ^ d[1] ^ d[0] ^ c[28] ^ c[29] ^ c[31])) ^ c[7];
      n[12] = (en & (d[2] ^ d[1] ^ d[0] ^ c[28] ^ c[29] ^ c[30])) ^ c[8];
      n[13] = (en & (d[3] ^ d[2] ^ d[1] ^ c[29] ^ c[30] ^ c[31])) ^ c[9];
      n[14] = (en & (d[3] ^ d[2] ^ c[30] ^ c[31])) ^ c[10];
      n[15] = (en & (d[3] ^ c[31])) ^ c[11];
      n[16] = (en & (d[0] ^ c[28])) ^ c[12];
      n[17] = (en & (d[1] ^ c[29])) ^ c[13];
      n[18] = (en & (d[2] ^ c[30])) ^ c[14];
      n[19] = (en & (d[3] ^ c[31])) ^ c[15];
      n[20] = c[16];
      n[21] = c[17];
      n[22] = (en & (d[0] ^ c[28])) ^ c[18];
      n[23] = (en & (d[1] ^ d[0] ^ c[29] ^ c[28])) ^ c[19];
      n[24] = (en & (d[2] ^ d[1] ^ c[30] ^ c[29])) ^ c[20];
      n[25] = (en & (d[3] ^ d[2] ^ c[31] ^ c[30])) ^ c[21];
      n[26] = (en & (d[3] ^ d[0] ^ c[31] ^ c[28])) ^ c[22];
      n[27] = (en & (d[1] ^ c[29])) ^ c[23];
      n[28] = (en & (d[2] ^ c[30])) ^ c[24];
      n[29] = (en & (d[3] ^ c[31])) ^ c[25];
      n[30] = c[26];
      n[31] = c[27];
      haven_step4 = n;
    end
  endfunction

  function [31:0] standard_step1;
    input [31:0] state;
    input input_bit;
    input input_enable;
    reg [31:0] value;
    reg feedback;
    begin
      feedback = input_enable & (state[31] ^ input_bit);
      value = {state[30:0], 1'b0};
      if (feedback)
        value = value ^ 32'h04c11db7;
      standard_step1 = value;
    end
  endfunction

  initial begin
    haven_crc_q = 32'hffffffff;
    spec_crc_q = 32'hffffffff;
  end

  always @* begin
    haven_next = haven_crc_q;
    spec_next = spec_crc_q;
    for (offset = 0; offset < SYMBOL_BITS; offset = offset + 4) begin
      haven_next = haven_step4(haven_next, data[offset +: 4], enable);
      for (bit_index = 3; bit_index >= 0; bit_index = bit_index - 1)
        spec_next = standard_step1(spec_next, data[offset + bit_index], enable);
    end
  end

  always @(posedge clk) begin
    if (initialize) begin
      haven_crc_q <= 32'hffffffff;
      spec_crc_q <= 32'hffffffff;
    end else begin
      haven_crc_q <= haven_next;
      spec_crc_q <= spec_next;
    end
  end

  assign bad = (haven_crc_q != spec_crc_q);
endmodule
